from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser


DEFAULT_IGNORE_PATTERNS = (
    "*.blend1",
    "*.blend2",
    "__pycache__/",
    ".cache/",
    "cache/",
    "temp/",
    "tmp/",
    "render/",
    "renders/",
    "output/",
    "outputs/",
    "*.tmp",
    "Thumbs.db",
    ".DS_Store",
)
DEFAULT_INCLUDE_PATTERNS = ("*.blend", "textures/**", "references/**")
DEFAULT_EXCLUDE_PATTERNS = DEFAULT_IGNORE_PATTERNS
LFS_ATTRIBUTE = "*.blend filter=lfs diff=lfs merge=lfs -text"
VERSION_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
GITHUB_HTTPS_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
GITHUB_SCP_PATTERN = re.compile(
    r"^git@github\.com:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$",
    re.IGNORECASE,
)
GITHUB_SSH_PATTERN = re.compile(
    r"^ssh://git@github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def _hidden_subprocess_kwargs():
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve())).casefold()


def _is_path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_text(value, limit=500) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _split_patterns(value, defaults=()) -> list[str]:
    if value is None:
        items = list(defaults)
    elif isinstance(value, str):
        items = value.replace("\r", "").split("\n")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []

    cleaned = []
    for item in items:
        pattern = _safe_text(item, 180).replace("\\", "/").lstrip("/")
        if not pattern or pattern.startswith(":"):
            continue
        if any(part == ".." for part in pattern.split("/")):
            raise ValueError("Share patterns cannot point outside the Blender project")
        if pattern not in cleaned:
            cleaned.append(pattern)
        if len(cleaned) >= 80:
            break
    return cleaned


def _normalize_version(value) -> str:
    version = _safe_text(value, 48) or "v0.1.0"
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Version must look like v0.1.0")
    return version if version.startswith("v") else f"v{version}"


def _github_match(value):
    raw = _safe_text(value, 500)
    for pattern in (GITHUB_HTTPS_PATTERN, GITHUB_SCP_PATTERN, GITHUB_SSH_PATTERN):
        match = pattern.fullmatch(raw)
        if match:
            return match
    return None


def _normalize_repository_url(value) -> str:
    raw = _safe_text(value, 500)
    if not raw:
        return ""
    if not _github_match(raw):
        raise ValueError("Repository URL must be a GitHub HTTPS or SSH repository URL")
    return raw.rstrip("/")


def _repository_slug(value) -> str:
    match = _github_match(value)
    if not match:
        return ""
    return f"{match.group('owner')}/{match.group('repo').removesuffix('.git')}".casefold()


def _repository_web_url(value) -> str:
    match = _github_match(value)
    if not match:
        return ""
    return f"https://github.com/{match.group('owner')}/{match.group('repo').removesuffix('.git')}"


class BlenderGithubShareService:
    def __init__(self, config_file, project_roots=(), live_selection_file=None, live_selection_max_age=20):
        self.config_file = Path(config_file)
        self.project_roots = [Path(item).expanduser() for item in project_roots]
        self.live_selection_file = Path(live_selection_file) if live_selection_file else None
        self.live_selection_max_age = max(1.0, float(live_selection_max_age or 20))
        self._config_lock = threading.RLock()
        self._tool_cache = None
        self._tool_cache_time = 0.0

    def _read_store(self) -> dict:
        with self._config_lock:
            try:
                payload = json.loads(self.config_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            projects = payload.get("projects")
            if not isinstance(projects, dict):
                projects = {}
            return {
                "version": 1,
                "lastProject": _safe_text(payload.get("lastProject"), 1000),
                "projects": projects,
            }

    def _write_store(self, payload: dict) -> None:
        with self._config_lock:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.config_file)

    def _live_project(self) -> str:
        if not self.live_selection_file:
            return ""
        try:
            payload = json.loads(self.live_selection_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ""
        if not isinstance(payload, dict):
            return ""
        updated = float(payload.get("updatedTimestamp") or 0)
        if updated and time.time() - updated > self.live_selection_max_age:
            return ""
        return _safe_text(payload.get("project"), 1000)

    def _discover_latest_project(self) -> str:
        candidates = []
        ignored_dirs = {".git", "__pycache__", "cache", "temp", "tmp", "library", "node_modules"}
        for root in self.project_roots:
            if not root.exists() or not root.is_dir():
                continue
            try:
                root_depth = len(root.resolve().parts)
                for current, directories, files in os.walk(root):
                    current_path = Path(current)
                    if len(current_path.resolve().parts) - root_depth >= 8:
                        directories[:] = []
                    directories[:] = [name for name in directories if name.casefold() not in ignored_dirs]
                    for name in files:
                        if Path(name).suffix.casefold() != ".blend":
                            continue
                        path = current_path / name
                        try:
                            candidates.append((path.stat().st_mtime, path))
                        except OSError:
                            continue
            except OSError:
                continue
        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0], reverse=True)
        return str(candidates[0][1])

    def _blend_files(self, root: Path, recursive=False) -> list[Path]:
        try:
            direct = [item.resolve() for item in root.glob("*.blend") if item.is_file()]
        except OSError:
            direct = []
        if direct or not recursive:
            return sorted(direct, key=lambda item: item.stat().st_mtime, reverse=True)

        matches = []
        root_depth = len(root.resolve().parts)
        ignored_dirs = {".git", "__pycache__", "cache", "temp", "tmp", "library", "node_modules"}
        for current, directories, files in os.walk(root):
            current_path = Path(current)
            if len(current_path.resolve().parts) - root_depth >= 5:
                directories[:] = []
            directories[:] = [name for name in directories if name.casefold() not in ignored_dirs]
            for name in files:
                if Path(name).suffix.casefold() == ".blend":
                    matches.append((current_path / name).resolve())
        return sorted(matches, key=lambda item: item.stat().st_mtime, reverse=True)

    def _resolve_project(self, value="") -> tuple[Path, Path, str]:
        raw = _safe_text(value, 1000)
        source = "selected"
        if not raw:
            raw = self._live_project()
            source = "blender"
        if not raw:
            raw = self._read_store().get("lastProject", "")
            source = "saved"
        if not raw:
            raw = self._discover_latest_project()
            source = "recent"
        if not raw:
            raise ValueError("No Blender project could be detected")

        path = Path(raw).expanduser().resolve()
        if path.is_file():
            if path.suffix.casefold() != ".blend":
                raise ValueError("Selected project is not a .blend file")
            blend_file = path
            root = path.parent
        elif path.is_dir():
            blend_files = self._blend_files(path, recursive=True)
            if not blend_files:
                raise ValueError("Selected folder does not contain a .blend file")
            root = path
            blend_file = blend_files[0]
        else:
            raise ValueError("Blender project path was not found")

        if not _is_path_inside(blend_file, root):
            raise ValueError("Blender file is outside the selected project folder")
        return root, blend_file, source

    def _default_config(self) -> dict:
        return {
            "repositoryUrl": "",
            "visibility": "private",
            "scope": "current",
            "includePatterns": list(DEFAULT_INCLUDE_PATTERNS),
            "excludePatterns": list(DEFAULT_EXCLUDE_PATTERNS),
            "version": "v0.1.0",
            "message": "",
        }

    def _stored_config(self, blend_file: Path) -> dict:
        store = self._read_store()
        raw = store["projects"].get(_path_key(blend_file), {})
        config = self._default_config()
        if isinstance(raw, dict):
            config.update({key: raw.get(key, config[key]) for key in config})
        config["repositoryUrl"] = _safe_text(config.get("repositoryUrl"), 500)
        config["visibility"] = "public" if config.get("visibility") == "public" else "private"
        config["scope"] = config.get("scope") if config.get("scope") in {"current", "project", "custom"} else "current"
        config["includePatterns"] = _split_patterns(config.get("includePatterns"), DEFAULT_INCLUDE_PATTERNS)
        config["excludePatterns"] = _split_patterns(config.get("excludePatterns"), DEFAULT_EXCLUDE_PATTERNS)
        config["version"] = _safe_text(config.get("version"), 48) or "v0.1.0"
        config["message"] = _safe_text(config.get("message"), 500)
        return config

    def _config_from_payload(self, payload: dict, existing: dict) -> dict:
        config = dict(existing)
        if "repositoryUrl" in payload:
            config["repositoryUrl"] = _normalize_repository_url(payload.get("repositoryUrl"))
        if "visibility" in payload:
            visibility = _safe_text(payload.get("visibility"), 16).casefold()
            config["visibility"] = "public" if visibility == "public" else "private"
        if "scope" in payload:
            scope = _safe_text(payload.get("scope"), 16).casefold()
            if scope not in {"current", "project", "custom"}:
                raise ValueError("Unknown share scope")
            config["scope"] = scope
        if "includePatterns" in payload:
            config["includePatterns"] = _split_patterns(payload.get("includePatterns"))
        if "excludePatterns" in payload:
            config["excludePatterns"] = _split_patterns(payload.get("excludePatterns"))
        if "version" in payload:
            config["version"] = _safe_text(payload.get("version"), 48) or "v0.1.0"
        if "message" in payload:
            config["message"] = _safe_text(payload.get("message"), 500)
        if config["visibility"] == "public" and existing.get("visibility") != "public" and not payload.get("confirmPublic"):
            raise ValueError("Public repository visibility requires explicit confirmation")
        return config

    def _save_project_config(self, blend_file: Path, root: Path, config: dict) -> None:
        with self._config_lock:
            store = self._read_store()
            record = dict(config)
            record.update({
                "projectRoot": str(root),
                "blendFile": str(blend_file),
                "updated": datetime.now(timezone.utc).isoformat(),
            })
            store["projects"][_path_key(blend_file)] = record
            store["lastProject"] = str(blend_file)
            self._write_store(store)

    def _prepare(self, payload: dict) -> tuple[Path, Path, dict]:
        root, blend_file, _ = self._resolve_project(payload.get("project", ""))
        existing = self._stored_config(blend_file)
        config = self._config_from_payload(payload, existing)
        self._save_project_config(blend_file, root, config)
        return root, blend_file, config

    def _run_process(self, command, cwd=None, timeout=60, check=True, env=None):
        process_env = os.environ.copy()
        process_env.setdefault("GIT_TERMINAL_PROMPT", "0")
        if env:
            process_env.update(env)
        try:
            completed = subprocess.run(
                [str(item) for item in command],
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=process_env,
                **_hidden_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("Git operation timed out") from error
        if check and completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "Command failed").strip()
            details = "\n".join(details.splitlines()[-12:])[:2400]
            raise ValueError(details)
        return completed

    def _git_command(self, root: Path, arguments, timeout=60, check=True):
        executable = shutil.which("git")
        if not executable:
            raise ValueError("Git is not installed or is not available in PATH")
        return self._run_process(
            [executable, "-C", str(root), "-c", f"safe.directory={root.as_posix()}", *arguments],
            timeout=timeout,
            check=check,
        )

    def _git_output(self, root: Path, arguments, default="") -> str:
        completed = self._git_command(root, arguments, check=False)
        return completed.stdout.strip() if completed.returncode == 0 else default

    def _tool_state(self) -> dict:
        now = time.monotonic()
        if self._tool_cache and now - self._tool_cache_time < 30:
            return dict(self._tool_cache)
        git = shutil.which("git")
        gh = shutil.which("gh")
        lfs_available = False
        git_version = ""
        lfs_version = ""
        gh_authenticated = False
        if git:
            result = self._run_process([git, "--version"], check=False)
            git_version = result.stdout.strip()
            result = self._run_process([git, "lfs", "version"], check=False)
            lfs_available = result.returncode == 0
            lfs_version = result.stdout.strip() if lfs_available else ""
        if gh:
            result = self._run_process([gh, "auth", "status", "--hostname", "github.com"], timeout=20, check=False)
            gh_authenticated = result.returncode == 0
        self._tool_cache = {
            "gitAvailable": bool(git),
            "gitVersion": git_version,
            "lfsAvailable": lfs_available,
            "lfsVersion": lfs_version,
            "ghAvailable": bool(gh),
            "ghAuthenticated": gh_authenticated,
        }
        self._tool_cache_time = now
        return dict(self._tool_cache)

    def _git_status(self, root: Path, blend_file: Path) -> dict:
        tools = self._tool_state()
        base = {
            "initialized": False,
            "state": "uninitialized",
            "branch": "",
            "remoteUrl": "",
            "repositoryWebUrl": "",
            "upstream": "",
            "ahead": 0,
            "behind": 0,
            "dirty": False,
            "hasCommit": False,
            "changes": [],
            "changedCount": 0,
            "stagedCount": 0,
            "lastCommit": None,
            "lastTag": "",
            "lfsTracked": False,
        }
        if not tools["gitAvailable"]:
            base["state"] = "gitUnavailable"
            return base

        probe = self._git_command(root, ["rev-parse", "--is-inside-work-tree"], check=False)
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return base

        base["initialized"] = True
        base["branch"] = self._git_output(root, ["branch", "--show-current"])
        base["remoteUrl"] = self._git_output(root, ["remote", "get-url", "origin"])
        base["repositoryWebUrl"] = _repository_web_url(base["remoteUrl"])
        base["hasCommit"] = self._git_command(root, ["rev-parse", "--verify", "HEAD"], check=False).returncode == 0

        status_output = self._git_output(root, ["status", "--porcelain=v1", "--untracked-files=all"])
        changes = []
        staged_count = 0
        for line in status_output.splitlines():
            if len(line) < 3:
                continue
            code = line[:2]
            path = line[3:]
            if code[0] not in {" ", "?"}:
                staged_count += 1
            changes.append({"code": code, "path": path})
        base["changes"] = changes[:100]
        base["changedCount"] = len(changes)
        base["stagedCount"] = staged_count
        base["dirty"] = bool(changes)

        if base["hasCommit"]:
            last_commit = self._git_output(root, ["log", "-1", "--format=%h%x1f%s%x1f%cI"])
            parts = last_commit.split("\x1f", 2)
            if len(parts) == 3:
                base["lastCommit"] = {"hash": parts[0], "subject": parts[1], "date": parts[2]}
            base["lastTag"] = self._git_output(root, ["describe", "--tags", "--abbrev=0"])
            base["upstream"] = self._git_output(
                root,
                ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            )
            if base["upstream"]:
                counts = self._git_output(root, ["rev-list", "--left-right", "--count", f"{base['upstream']}...HEAD"])
                match = re.match(r"^(\d+)\s+(\d+)$", counts)
                if match:
                    base["behind"] = int(match.group(1))
                    base["ahead"] = int(match.group(2))

        relative_blend = blend_file.relative_to(root).as_posix()
        attribute = self._git_output(root, ["check-attr", "filter", "--", relative_blend])
        base["lfsTracked"] = attribute.rstrip().endswith(": lfs")

        if base["dirty"]:
            base["state"] = "dirty"
        elif base["hasCommit"] and base["remoteUrl"] and (not base["upstream"] or base["ahead"] > 0):
            base["state"] = "pendingPush"
        elif base["hasCommit"] and base["remoteUrl"] and base["upstream"] and base["behind"] > 0:
            base["state"] = "behind"
        elif base["hasCommit"] and base["remoteUrl"] and base["upstream"] and base["ahead"] == 0 and base["behind"] == 0:
            base["state"] = "synced"
        elif base["hasCommit"]:
            base["state"] = "committed"
        else:
            base["state"] = "dirty" if base["dirty"] else "initialized"
        return base

    def status(self, project="") -> dict:
        root, blend_file, source = self._resolve_project(project)
        config = self._stored_config(blend_file)
        git = self._git_status(root, blend_file)
        if not config["repositoryUrl"] and git["remoteUrl"]:
            config["repositoryUrl"] = git["remoteUrl"]
        blend_files = self._blend_files(root, recursive=False)
        return {
            "ok": True,
            "project": {
                "name": blend_file.stem,
                "rootName": root.name,
                "path": str(blend_file),
                "directory": str(root),
                "detectedBy": source,
                "blendFiles": [str(item) for item in blend_files[:40]],
            },
            "config": config,
            "git": git,
            "tools": self._tool_state(),
            "defaults": {
                "ignorePatterns": list(DEFAULT_IGNORE_PATTERNS),
                "includePatterns": list(DEFAULT_INCLUDE_PATTERNS),
                "excludePatterns": list(DEFAULT_EXCLUDE_PATTERNS),
            },
        }

    def save(self, payload: dict) -> dict:
        root, blend_file, _ = self._prepare(payload)
        result = self.status(str(blend_file))
        result["message"] = "Project share settings saved"
        return result

    def _append_missing_lines(self, path: Path, lines, heading="") -> list[str]:
        try:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
        except UnicodeDecodeError:
            existing = path.read_text(encoding="utf-8", errors="replace")
        existing_lines = {line.strip() for line in existing.replace("\r", "").split("\n")}
        missing = [line for line in lines if line.strip() not in existing_lines]
        if not missing:
            return []
        content = existing.rstrip()
        additions = []
        if heading and heading not in existing_lines:
            additions.append(heading)
        additions.extend(missing)
        next_content = "\n".join(part for part in (content, "\n".join(additions)) if part).rstrip() + "\n"
        path.write_text(next_content, encoding="utf-8")
        return missing

    def _ensure_repository_files(self, root: Path) -> dict:
        ignored = self._append_missing_lines(
            root / ".gitignore",
            DEFAULT_IGNORE_PATTERNS,
            heading="# Codex Console Blender defaults",
        )
        attributes = self._append_missing_lines(root / ".gitattributes", [LFS_ATTRIBUTE])
        return {"ignoreAdded": ignored, "attributesAdded": attributes}

    def _configure_remote(self, root: Path, repository_url: str, replace=False) -> str:
        current = self._git_output(root, ["remote", "get-url", "origin"])
        if not repository_url:
            return current
        if current and _repository_slug(current) != _repository_slug(repository_url):
            if not replace:
                raise ValueError("Origin already points to another repository; confirm replacement before continuing")
            self._git_command(root, ["remote", "set-url", "origin", repository_url])
        elif not current:
            self._git_command(root, ["remote", "add", "origin", repository_url])
        return repository_url

    def _create_github_repository(self, root: Path, visibility: str) -> str:
        tools = self._tool_state()
        executable = shutil.which("gh")
        if not executable or not tools["ghAuthenticated"]:
            raise ValueError("GitHub CLI is unavailable or not signed in; paste an empty GitHub repository URL instead")
        repository_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name).strip("-.") or "blender-project"
        command = [
            executable,
            "repo",
            "create",
            repository_name,
            "--source",
            str(root),
            "--remote",
            "origin",
            "--public" if visibility == "public" else "--private",
        ]
        self._run_process(command, cwd=root, timeout=120)
        remote = self._git_output(root, ["remote", "get-url", "origin"])
        if not remote:
            raise ValueError("GitHub repository was created but origin could not be detected")
        return remote

    def initialize(self, payload: dict) -> dict:
        root, blend_file, config = self._prepare(payload)
        tools = self._tool_state()
        if not tools["gitAvailable"]:
            raise ValueError("Git is not installed or is not available in PATH")
        if not tools["lfsAvailable"]:
            raise ValueError("Git LFS is required before initializing a Blender repository")

        probe = self._git_command(root, ["rev-parse", "--is-inside-work-tree"], check=False)
        initialized_now = probe.returncode != 0
        if initialized_now:
            result = self._git_command(root, ["init", "-b", "main"], check=False)
            if result.returncode != 0:
                self._git_command(root, ["init"])
                self._git_command(root, ["symbolic-ref", "HEAD", "refs/heads/main"])

        self._git_command(root, ["lfs", "install", "--local"])
        self._git_command(root, ["lfs", "track", "*.blend"])
        file_changes = self._ensure_repository_files(root)

        remote = self._configure_remote(
            root,
            config["repositoryUrl"],
            replace=bool(payload.get("replaceRemote")),
        )
        if not remote and payload.get("createGithub"):
            remote = self._create_github_repository(root, config["visibility"])
        if remote and config["repositoryUrl"] != remote:
            config["repositoryUrl"] = remote
            self._save_project_config(blend_file, root, config)

        result = self.status(str(blend_file))
        result["action"] = {
            "initialized": initialized_now,
            "repositoryFiles": file_changes,
            "remoteConfigured": bool(remote),
        }
        result["message"] = (
            "Repository initialized; add an empty GitHub repository URL before pushing"
            if not remote
            else "Repository and Git LFS are ready"
        )
        return result

    def _scope_pathspecs(self, root: Path, blend_file: Path, config: dict) -> tuple[str, list[str]]:
        metadata = [":(top,literal).gitignore", ":(top,literal).gitattributes"]
        if config["scope"] == "project":
            return "project", ["."]
        if config["scope"] == "current":
            relative = blend_file.relative_to(root).as_posix()
            return "selected", [f":(top,literal){relative}", *metadata]

        includes = config.get("includePatterns") or []
        if not includes:
            raise ValueError("Custom share scope needs at least one include pattern")
        pathspecs = [f":(top,glob){pattern}" for pattern in includes]
        pathspecs.extend(f":(top,exclude,glob){pattern}" for pattern in config.get("excludePatterns") or [])
        pathspecs.extend(metadata)
        return "selected", pathspecs

    def commit(self, payload: dict) -> dict:
        root, blend_file, config = self._prepare(payload)
        git = self._git_status(root, blend_file)
        if not git["initialized"]:
            raise ValueError("Initialize the repository before committing")
        if not self._tool_state()["lfsAvailable"]:
            raise ValueError("Git LFS is required before committing Blender files")

        version = _normalize_version(config.get("version"))
        description = config.get("message") or f"Blender project {version}"
        if self._git_command(root, ["rev-parse", "--verify", f"refs/tags/{version}"], check=False).returncode == 0:
            raise ValueError(f"Version tag {version} already exists")

        self._git_command(root, ["lfs", "install", "--local"])
        self._git_command(root, ["lfs", "track", "*.blend"])
        self._ensure_repository_files(root)
        mode, pathspecs = self._scope_pathspecs(root, blend_file, config)
        if config["scope"] == "current":
            relative = blend_file.relative_to(root).as_posix()
            self._git_command(root, ["add", "-f", "--", relative])
            self._git_command(root, ["add", "-A", "--", ".gitignore", ".gitattributes"])
        else:
            self._git_command(root, ["add", "-A", "--", *pathspecs])

        staged = self._git_output(root, ["diff", "--cached", "--name-only", "--", *pathspecs])
        commit_title = description if version.casefold() in description.casefold() else f"{version}: {description}"
        committed = False
        if staged:
            command = ["commit", "-m", commit_title]
            if mode == "selected":
                command.extend(["--only", "--", *pathspecs])
            self._git_command(root, command, timeout=120)
            committed = True
        elif not git["hasCommit"]:
            raise ValueError("No files matched the selected share scope")

        self._git_command(root, ["tag", "-a", version, "-m", description])
        config["version"] = version
        config["message"] = description
        self._save_project_config(blend_file, root, config)

        result = self.status(str(blend_file))
        result["action"] = {"committed": committed, "tag": version, "files": staged.splitlines()}
        result["message"] = f"Version {version} committed" if committed else f"Version {version} tagged"
        return result

    def push(self, payload: dict) -> dict:
        root, blend_file, config = self._prepare(payload)
        git = self._git_status(root, blend_file)
        if not git["initialized"] or not git["hasCommit"]:
            raise ValueError("Commit a version before pushing")
        remote = self._configure_remote(
            root,
            config["repositoryUrl"],
            replace=bool(payload.get("replaceRemote")),
        )
        if not remote:
            raise ValueError("GitHub repository URL is required before pushing")
        branch = git["branch"] or self._git_output(root, ["branch", "--show-current"])
        if not branch:
            raise ValueError("Cannot push while Git is in detached HEAD state")
        self._git_command(root, ["push", "-u", "origin", branch, "--follow-tags"], timeout=240)
        result = self.status(str(blend_file))
        result["message"] = "Repository pushed to GitHub"
        return result

    def open_repository(self, payload: dict) -> dict:
        root, blend_file, _ = self._resolve_project(payload.get("project", ""))
        config = self._stored_config(blend_file)
        git = self._git_status(root, blend_file)
        url = _repository_web_url(config["repositoryUrl"] or git["remoteUrl"])
        if not url:
            url = "https://github.com/new"
        webbrowser.open(url)
        return {"ok": True, "url": url, "project": str(blend_file)}

    def open_folder(self, payload: dict) -> dict:
        root, blend_file, _ = self._resolve_project(payload.get("project", ""))
        if sys.platform == "win32":
            os.startfile(str(root))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(root)], **_hidden_subprocess_kwargs())
        else:
            subprocess.Popen(["xdg-open", str(root)], **_hidden_subprocess_kwargs())
        return {"ok": True, "path": str(root), "project": str(blend_file)}

    def open_desktop(self, payload: dict) -> dict:
        root, blend_file, _ = self._resolve_project(payload.get("project", ""))
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        cli_candidates = [
            Path(shutil.which("github") or ""),
            local_app_data / "GitHubDesktop" / "bin" / "github.exe",
            local_app_data / "GitHubDesktop" / "bin" / "github.bat",
            local_app_data / "GitHubDesktop" / "bin" / "github.cmd",
        ]
        cli = next((item for item in cli_candidates if str(item) and item.is_file()), None)
        if cli:
            if cli.suffix.casefold() in {".bat", ".cmd"}:
                command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(cli), str(root)]
            else:
                command = [str(cli), str(root)]
            subprocess.Popen(command, cwd=str(root), **_hidden_subprocess_kwargs())
            return {"ok": True, "path": str(root), "project": str(blend_file), "fallback": False}

        app_candidates = []
        desktop_root = local_app_data / "GitHubDesktop"
        if desktop_root.is_dir():
            app_candidates.extend(sorted(desktop_root.glob("app-*/GitHubDesktop.exe"), reverse=True))
            app_candidates.append(desktop_root / "GitHubDesktop.exe")
        app = next((item for item in app_candidates if item.is_file()), None)
        if app:
            subprocess.Popen([str(app), "--open-repo", str(root)], cwd=str(root), **_hidden_subprocess_kwargs())
            return {"ok": True, "path": str(root), "project": str(blend_file), "fallback": False}

        url = "https://desktop.github.com/"
        webbrowser.open(url)
        return {"ok": True, "url": url, "project": str(blend_file), "fallback": True}
