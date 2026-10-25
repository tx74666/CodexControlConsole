"""Size policy and pointer verification around the installed standard Git LFS."""
import json
import re

LARGE_FILE_BYTES = 100_000_000
MAX_POINTER_BYTES = 1024
_OID = re.compile(rb"[0-9a-f]{40,64}\Z")


class LargeFileError(ValueError):
    def __init__(self, message, code="git_lfs"):
        super().__init__(message)
        self.code = code


def candidates(files, *, threshold=None):
    limit = LARGE_FILE_BYTES if threshold is None else threshold
    return [item for item in files if not item.get("deleted") and item.get("bytes", 0) > limit]


def attribute_line(path):
    # Root-anchored literal names, never extension-wide tracking. Quote according
    # to Git's C-style .gitattributes grammar while retaining UTF-8 filenames.
    literal = "/" + "".join({"[": "[[]", "]": "[]]", "*": "[*]", "?": "[?]"}.get(char, char) for char in path)
    return json.dumps(literal, ensure_ascii=False) + " filter=lfs diff=lfs merge=lfs -text\n"


def filters(git, paths, *, index=None):
    if not paths:
        return {}
    raw = git("check-attr", *( ["--cached"] if index is not None else [] ), "-z", "--stdin", "filter",
              data=b"".join(path.encode("utf-8", "surrogateescape") + b"\0" for path in paths), index=index)
    parts = raw.split(b"\0")
    if parts[-1:] != [b""] or (len(parts) - 1) != len(paths) * 3:
        raise LargeFileError("大文件的 Git 属性回执不完整，保留原文件。")
    result = {}
    for offset in range(0, len(parts) - 1, 3):
        name, attribute, value = parts[offset:offset + 3]
        path = name.decode("utf-8", "surrogateescape")
        if path not in paths or path in result or attribute != b"filter":
            raise LargeFileError("大文件的 Git 属性身份无法核对，保留原文件。")
        result[path] = value.decode("utf-8", "surrogateescape")
    return result


def pointer(raw):
    if len(raw) > MAX_POINTER_BYTES:
        return None
    lines = raw.splitlines()
    if not lines or lines[0] != b"version https://git-lfs.github.com/spec/v1":
        return None
    oid = [line[11:] for line in lines[1:] if line.startswith(b"oid sha256:")]
    size = [line[5:] for line in lines[1:] if line.startswith(b"size ")]
    if (len(oid) != 1 or not re.fullmatch(rb"[0-9a-f]{64}", oid[0]) or len(size) != 1
            or not re.fullmatch(rb"(?:0|[1-9][0-9]*)", size[0])
            or any(not line.startswith((b"oid sha256:", b"size ", b"ext-")) for line in lines[1:])):
        return None
    return {"sha256": oid[0].decode("ascii"), "bytes": int(size[0])}


def verify_index(git, files, index):
    large = candidates(files)
    if not large:
        return
    paths = [item["path"] for item in large]
    effective = filters(git, paths, index=index)
    for item in large:
        path = item["path"]
        if effective[path] != "lfs":
            raise LargeFileError("大文件未使用 LFS；请核对嵌套属性或已有过滤器，原文件保留。")
        raw = git("--literal-pathspecs", "ls-files", "--stage", "-z", "--", path, index=index)
        records = [record for record in raw.split(b"\0") if record]
        if len(records) != 1 or b"\t" not in records[0]:
            raise LargeFileError("大文件暂存回执无法核对，尚未创建提交。")
        metadata, name = records[0].split(b"\t", 1)
        fields = metadata.split()
        if (len(fields) != 3 or fields[0] not in {b"100644", b"100755"} or fields[2] != b"0"
                or not _OID.fullmatch(fields[1]) or name != path.encode("utf-8", "surrogateescape")):
            raise LargeFileError("大文件暂存身份无法核对，尚未创建提交。")
        oid = fields[1].decode("ascii")
        size = git("cat-file", "-s", oid).strip()
        if not size.isdigit() or int(size) > MAX_POINTER_BYTES:
            raise LargeFileError("大文件仍以普通 Git 内容暂存，已停止提交；原文件保留。")
        actual = pointer(git("cat-file", "blob", oid))
        if actual != {"bytes": item["bytes"], "sha256": item["sha256"]}:
            raise LargeFileError("LFS 指针与已核对原文件的大小或 SHA-256 不符，已停止提交。")


def inspect_outgoing(git, head, remote):
    """Inspect only outgoing objects, without reading any large blob body."""
    raw = git("rev-list", "--objects", "--no-object-names", head, *(["^" + remote] if remote else []))
    oids = list(dict.fromkeys(raw.splitlines()))
    if any(not _OID.fullmatch(oid) for oid in oids):
        raise LargeFileError("待推送对象回执无法核对。")
    small = []
    large = 0
    for offset in range(0, len(oids), 1000):
        batch = oids[offset:offset + 1000]
        rows = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", data=b"\n".join(batch) + b"\n").splitlines()
        if len(rows) != len(batch):
            raise LargeFileError("待推送对象大小回执不完整。")
        for expected, row in zip(batch, rows):
            fields = row.split()
            if len(fields) != 3 or fields[0] != expected or not fields[2].isdigit():
                raise LargeFileError("待推送对象大小无法核对。")
            if fields[1] == b"blob":
                size = int(fields[2])
                large += size > LARGE_FILE_BYTES
                if 100 <= size <= MAX_POINTER_BYTES:
                    small.append(expected)
    if large:
        raise LargeFileError("待推送历史仍含超过 100 MB 的普通 Git 文件（" + str(large) + " 个对象）。仅添加 LFS 跟踪不能修复旧提交；请先核对未发布历史的迁移，原提交与远端历史保留。", "git_large_history")
    for offset in range(0, len(small), 500):
        batch = small[offset:offset + 500]
        raw = git("cat-file", "--batch", data=b"\n".join(batch) + b"\n")
        position = 0
        for expected in batch:
            end = raw.find(b"\n", position)
            fields = raw[position:end].split() if end >= 0 else []
            if len(fields) != 3 or fields[0] != expected or fields[1] != b"blob" or not fields[2].isdigit():
                raise LargeFileError("LFS 历史指针回执不完整。")
            size = int(fields[2]); position = end + 1
            if size > MAX_POINTER_BYTES or position + size >= len(raw) or raw[position + size:position + size + 1] != b"\n":
                raise LargeFileError("LFS 历史指针内容无法核对。")
            if pointer(raw[position:position + size]):
                return True
            position += size + 1
    return False
