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
BLENDER_DISCOVERY_IGNORED_DIRECTORIES = frozenset({
    ".cache",
    ".git",
    "__pycache__",
    "assets",
    "backups",
    "blend_backups",
    "cache",
    "exports",
    "library",
    "node_modules",
    "output",
    "outputs",
    "records",
    "render",
    "renders",
    "roundtrip",
    "temp",
    "tmp",
    "unityexports",
})
BLENDER_DISCOVERY_BACKUP_PATTERN = re.compile(
    r"(?:^|[._-])(?:backup|backups|before[-_]?migration)(?:[._-]|$)",
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


def filter_blender_discovery_directories(names) -> list[str]:
    return [
        name for name in names
        if name.casefold() not in BLENDER_DISCOVERY_IGNORED_DIRECTORIES
        and not name.startswith(".")
    ]


def is_blender_discovery_file(path, root=None) -> bool:
    target = Path(path)
    if target.suffix.casefold() != ".blend":
        return False
    relative = target
    if root is not None:
        try:
            relative = target.relative_to(Path(root))
        except ValueError:
            pass
    if any(part.casefold() in BLENDER_DISCOVERY_IGNORED_DIRECTORIES for part in relative.parts[:-1]):
        return False
    stem = target.stem.casefold()
    return ".codex-" not in stem and not BLENDER_DISCOVERY_BACKUP_PATTERN.search(stem)


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
    def __init__(
        self,
        config_file,
        project_roots=(),
        catalog_file=None,
        live_selection_file=None,
        live_selection_max_age=20,
    ):
        self.config_file = Path(config_file)
        self.project_roots = [Path(item).expanduser() for item in project_roots]
        self.catalog_file = Path(catalog_file) if catalog_file else None
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
            project_order = payload.get("projectOrder")
            if not isinstance(project_order, list):
                project_order = []
            if not project_order:
                project_order = [
                    record.get("blendFile")
                    for record in projects.values()
                    if isinstance(record, dict) and record.get("blendFile")
                ]
            cleaned_project_order = []
            seen_projects = set()
            for item in project_order:
                path = _safe_text(item, 1000)
                key = os.path.normcase(path).casefold()
                if not path or key in seen_projects:
                    continue
                seen_projects.add(key)
                cleaned_project_order.append(path)

            raw_file_order = payload.get("fileOrder")
            file_order = {}
            if isinstance(raw_file_order, dict):
                for root_key, items in raw_file_order.items():
                    if not isinstance(items, list):
                        continue
                    cleaned = []
                    seen_files = set()
                    for item in items:
                        path = _safe_text(item, 1000)
                        key = os.path.normcase(path).casefold()
                        if not path or key in seen_files:
                            continue
                        seen_files.add(key)
                        cleaned.append(path)
                    if cleaned:
                        file_order[_safe_text(root_key, 1200)] = cleaned
            raw_repository_order = payload.get("repositoryOrder")
            repository_order = []
            seen_repositories = set()
            if isinstance(raw_repository_order, list):
                for item in raw_repository_order:
                    url = _repository_web_url(item)
                    slug = _repository_slug(url)
                    if not slug or slug in seen_repositories:
                        continue
                    seen_repositories.add(slug)
                    repository_order.append(url)

            repository_paths = {}
            raw_repository_paths = payload.get("repositoryPaths")
            if isinstance(raw_repository_paths, dict):
                for repository, path_value in raw_repository_paths.items():
                    slug = _repository_slug(repository)
                    path = _safe_text(path_value, 1000)
                    if slug and path:
                        repository_paths[slug] = path

            return {
                "version": 3,
                "lastProject": _safe_text(payload.get("lastProject"), 1000),
                "lastRepository": _repository_web_url(payload.get("lastRepository")),
                "projectOrder": cleaned_project_order,
                "repositoryOrder": repository_order,
                "repositoryPaths": repository_paths,
                "fileOrder": file_order,
                "projects": projects,
            }

    def _read_catalog(self) -> list[dict]:
        if not self.catalog_file:
            return []
        try:
            payload = json.loads(self.catalog_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        records = payload.get("repositories") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            return []

        repositories = []
        seen = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                repository_url = _normalize_repository_url(record.get("repositoryUrl"))
            except ValueError:
                continue
            repository_web_url = _repository_web_url(repository_url)
            slug = _repository_slug(repository_url)
            if not slug or slug in seen:
                continue
            seen.add(slug)
            repositories.append({
                "name": _safe_text(record.get("name"), 120) or repository_web_url.rsplit("/", 1)[-1],
                "file": _safe_text(record.get("blendFile"), 260),
                "path": "",
                "directory": "",
                "repositoryUrl": repository_web_url,
                "remoteUrl": repository_url,
                "version": _safe_text(record.get("version"), 48),
                "state": "cloud",
                "defaultBranch": _safe_text(record.get("defaultBranch"), 120) or "main",
                "visibility": "public" if record.get("visibility") == "public" else "private",
                "downloaded": False,
                "catalog": True,
            })
        return repositories

    def _write_store(self, payload: dict) -> None:
        with self._config_lock:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.config_file)

    def _pin_in_store(self, store: dict, blend_file: Path) -> None:
        blend_file = blend_file.resolve()
        root_key = _path_key(blend_file.parent)
        order = list(store.get("projectOrder") or [])
        for index, item in enumerate(order):
            try:
                if _path_key(Path(item).expanduser().resolve().parent) == root_key:
                    order[index] = str(blend_file)
                    break
            except OSError:
                continue
        else:
            order.append(str(blend_file))
        store["projectOrder"] = order

    def _pin_repository_in_store(self, store: dict, repository_url: str, blend_file: Path | None = None) -> None:
        web_url = _repository_web_url(repository_url)
        slug = _repository_slug(web_url)
        if not slug:
            return
        order = list(store.get("repositoryOrder") or [])
        if all(_repository_slug(item) != slug for item in order):
            order.append(web_url)
        store["repositoryOrder"] = order
        store["lastRepository"] = web_url
        if blend_file:
            paths = dict(store.get("repositoryPaths") or {})
            paths[slug] = str(blend_file.resolve())
            store["repositoryPaths"] = paths

    def _pin_project(self, blend_file: Path, *, select=True) -> None:
        with self._config_lock:
            store = self._read_store()
            self._pin_in_store(store, blend_file)
            if select:
                store["lastProject"] = str(blend_file.resolve())
            self._write_store(store)

    def _ordered_blend_files(self, root: Path) -> list[Path]:
        files = self._blend_files(root, recursive=False)
        order = self._read_store().get("fileOrder", {}).get(_path_key(root), [])
        ranks = {
            os.path.normcase(str(Path(item).expanduser().resolve())).casefold(): index
            for index, item in enumerate(order)
        }
        original_rank = {_path_key(path): index for index, path in enumerate(files)}
        return sorted(
            files,
            key=lambda path: (
                ranks.get(_path_key(path), len(ranks) + original_rank[_path_key(path)]),
                original_rank[_path_key(path)],
            ),
        )

    def _local_project_collection(
        self,
        selected_file: Path | None = None,
        selected_config: dict | None = None,
        selected_git: dict | None = None,
    ) -> list[dict]:
        store = self._read_store()
        selected_root_key = _path_key(selected_file.parent) if selected_file else ""
        projects = []
        seen_roots = set()
        seen_repositories = set()
        for item in store.get("projectOrder", []):
            try:
                candidate = Path(item).expanduser().resolve()
                root = candidate.parent if candidate.is_file() else candidate
                if not root.is_dir():
                    continue
                root_key = _path_key(root)
                if root_key in seen_roots:
                    continue
                blend_files = self._ordered_blend_files(root)
                if not blend_files:
                    continue
                if root_key == selected_root_key and selected_file in blend_files:
                    representative = selected_file
                else:
                    representative = candidate if candidate in blend_files else blend_files[0]
                selected = bool(
                    selected_file
                    and selected_config is not None
                    and selected_git is not None
                    and representative == selected_file
                )
                config = selected_config if selected else self._stored_config(representative)
                git = selected_git if selected else self._git_status(root, representative)
                repository_url = git.get("repositoryWebUrl") or _repository_web_url(config.get("repositoryUrl"))
                repository_key = repository_url.casefold()
                if not git.get("initialized") or not git.get("hasCommit") or not repository_key:
                    continue
                if repository_key in seen_repositories:
                    continue
                seen_roots.add(root_key)
                seen_repositories.add(repository_key)
                projects.append({
                    "name": repository_url.rstrip("/").rsplit("/", 1)[-1] or root.name,
                    "file": representative.name,
                    "path": str(representative),
                    "directory": str(root),
                    "repositoryUrl": repository_url,
                    "remoteUrl": git.get("remoteUrl", ""),
                    "version": git.get("lastTag") or config.get("version") or "",
                    "state": git.get("state") or "initialized",
                    "defaultBranch": git.get("branch") or "main",
                    "visibility": config.get("visibility") or "private",
                    "downloaded": True,
                    "catalog": False,
                })
            except OSError:
                continue
        return projects

    def _project_collection(
        self,
        selected_file: Path | None = None,
        selected_config: dict | None = None,
        selected_git: dict | None = None,
    ) -> list[dict]:
        local_projects = self._local_project_collection(selected_file, selected_config, selected_git)
        local_by_repository = {
            _repository_slug(item.get("repositoryUrl")): item
            for item in local_projects
            if _repository_slug(item.get("repositoryUrl"))
        }
        projects = []
        seen = set()

        for catalog_entry in self._read_catalog():
            slug = _repository_slug(catalog_entry["repositoryUrl"])
            local = local_by_repository.pop(slug, None)
            if local:
                merged = dict(catalog_entry)
                merged.update(local)
                merged["name"] = catalog_entry["name"]
                merged["file"] = local.get("file") or catalog_entry.get("file", "")
                merged["version"] = local.get("version") or catalog_entry.get("version", "")
                merged["defaultBranch"] = local.get("defaultBranch") or catalog_entry.get("defaultBranch", "main")
                merged["catalog"] = True
                projects.append(merged)
            else:
                projects.append(dict(catalog_entry))
            seen.add(slug)

        for local in local_projects:
            slug = _repository_slug(local.get("repositoryUrl"))
            if not slug or slug in seen:
                continue
            seen.add(slug)
            projects.append(local)

        order = self._read_store().get("repositoryOrder", [])
        if order:
            ranks = {_repository_slug(url): index for index, url in enumerate(order)}
            original = {_repository_slug(item["repositoryUrl"]): index for index, item in enumerate(projects)}
            projects.sort(key=lambda item: (
                ranks.get(_repository_slug(item["repositoryUrl"]), len(ranks) + original[_repository_slug(item["repositoryUrl"])]),
                original[_repository_slug(item["repositoryUrl"])],
            ))
        return projects

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
        for root in self.project_roots:
            if not root.exists() or not root.is_dir():
                continue
            try:
                root_depth = len(root.resolve().parts)
                for current, directories, files in os.walk(root):
                    current_path = Path(current)
                    if len(current_path.resolve().parts) - root_depth >= 8:
                        directories[:] = []
                    directories[:] = filter_blender_discovery_directories(directories)
                    for name in files:
                        path = current_path / name
                        if not is_blender_discovery_file(path, root):
                            continue
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
            direct = [
                item.resolve() for item in root.glob("*.blend")
                if item.is_file() and is_blender_discovery_file(item, root)
            ]
        except OSError:
            direct = []
        if direct or not recursive:
            return sorted(direct, key=lambda item: item.stat().st_mtime, reverse=True)

        matches = []
        root_depth = len(root.resolve().parts)
        for current, directories, files in os.walk(root):
            current_path = Path(current)
            if len(current_path.resolve().parts) - root_depth >= 5:
                directories[:] = []
            directories[:] = filter_blender_discovery_directories(directories)
            for name in files:
                path = current_path / name
                if is_blender_discovery_file(path, root):
                    matches.append(path.resolve())
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
            self._pin_in_store(store, blend_file)
            self._pin_repository_in_store(store, config.get("repositoryUrl", ""), blend_file)
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

    def _refresh_remote(self, root: Path) -> dict:
        result = {
            "attempted": False,
            "ok": None,
            "error": "",
        }
        if not self._tool_state().get("gitAvailable"):
            return result
        probe = self._git_command(root, ["rev-parse", "--is-inside-work-tree"], check=False)
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return result
        if not self._git_output(root, ["remote", "get-url", "origin"]):
            return result

        result["attempted"] = True
        completed = self._git_command(
            root,
            ["fetch", "--quiet", "--prune", "origin"],
            timeout=25,
            check=False,
        )
        result["ok"] = completed.returncode == 0
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "Could not reach GitHub").strip()
            result["error"] = "\n".join(details.splitlines()[-3:])[:600]
        return result

    def _github_desktop_cli(self) -> Path | None:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            Path(shutil.which("github") or ""),
            local_app_data / "GitHubDesktop" / "bin" / "github.exe",
            local_app_data / "GitHubDesktop" / "bin" / "github.bat",
            local_app_data / "GitHubDesktop" / "bin" / "github.cmd",
        ]
        return next((item for item in candidates if str(item) and item.is_file()), None)

    def _github_desktop_app(self) -> Path | None:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        desktop_root = local_app_data / "GitHubDesktop"
        candidates = []
        if desktop_root.is_dir():
            candidates.extend(sorted(desktop_root.glob("app-*/GitHubDesktop.exe"), reverse=True))
            candidates.append(desktop_root / "GitHubDesktop.exe")
        return next((item for item in candidates if item.is_file()), None)

    def _launch_desktop_command(self, command, cwd="") -> None:
        launch_options = _hidden_subprocess_kwargs()
        if cwd:
            launch_options["cwd"] = str(cwd)
        subprocess.Popen([str(item) for item in command], **launch_options)

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
            "githubDesktopAvailable": bool(self._github_desktop_cli() or self._github_desktop_app()),
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

    def _collection_project(self, value, collection: list[dict]) -> dict | None:
        raw = _safe_text(value, 1000)
        slug = _repository_slug(raw)
        if slug:
            return next(
                (item for item in collection if _repository_slug(item.get("repositoryUrl")) == slug),
                None,
            )
        if not raw:
            return None
        try:
            path_key = _path_key(Path(raw).expanduser())
        except (OSError, RuntimeError):
            path_key = os.path.normcase(raw).casefold()
        for item in collection:
            for candidate in (item.get("path"), item.get("directory")):
                if not candidate:
                    continue
                try:
                    candidate_key = _path_key(Path(candidate))
                except (OSError, RuntimeError):
                    candidate_key = os.path.normcase(str(candidate)).casefold()
                if candidate_key == path_key:
                    return item
        return None

    def _status_defaults(self) -> dict:
        return {
            "ignorePatterns": list(DEFAULT_IGNORE_PATTERNS),
            "includePatterns": list(DEFAULT_INCLUDE_PATTERNS),
            "excludePatterns": list(DEFAULT_EXCLUDE_PATTERNS),
        }

    def _local_status(
        self,
        root: Path,
        blend_file: Path,
        source: str,
        collection: list[dict] | None = None,
        refresh_remote=False,
    ) -> dict:
        config = self._stored_config(blend_file)
        remote_check = self._refresh_remote(root) if refresh_remote else {
            "attempted": False,
            "ok": None,
            "error": "",
        }
        git = self._git_status(root, blend_file)
        git["remoteCheck"] = remote_check
        if not config["repositoryUrl"] and git["remoteUrl"]:
            config["repositoryUrl"] = git["remoteUrl"]
        blend_files = self._ordered_blend_files(root)
        collection = collection if collection is not None else self._project_collection(
            blend_file,
            selected_config=config,
            selected_git=git,
        )
        repository_url = git.get("repositoryWebUrl") or _repository_web_url(config.get("repositoryUrl"))
        repository = self._collection_project(repository_url or str(blend_file), collection)
        return {
            "ok": True,
            "collection": {
                "projects": collection,
            },
            "project": {
                "name": repository.get("name") if repository else blend_file.stem,
                "rootName": root.name,
                "path": str(blend_file),
                "directory": str(root),
                "repositoryUrl": repository_url,
                "downloaded": True,
                "detectedBy": source,
                "blendFiles": [str(item) for item in blend_files[:40]],
            },
            "config": config,
            "git": git,
            "tools": self._tool_state(),
            "defaults": self._status_defaults(),
        }

    def _cloud_status(self, repository: dict, collection: list[dict]) -> dict:
        config = self._default_config()
        config.update({
            "repositoryUrl": repository.get("remoteUrl") or repository["repositoryUrl"],
            "visibility": repository.get("visibility") or "private",
            "version": repository.get("version") or "v0.1.0",
        })
        git = {
            "initialized": False,
            "state": "cloud",
            "branch": repository.get("defaultBranch") or "main",
            "remoteUrl": repository.get("remoteUrl") or repository["repositoryUrl"],
            "repositoryWebUrl": repository["repositoryUrl"],
            "upstream": "",
            "ahead": 0,
            "behind": 0,
            "dirty": False,
            "hasCommit": True,
            "changes": [],
            "changedCount": 0,
            "stagedCount": 0,
            "lastCommit": None,
            "lastTag": repository.get("version") or "",
            "lfsTracked": True,
            "remoteCheck": {
                "attempted": False,
                "ok": None,
                "error": "",
            },
        }
        return {
            "ok": True,
            "collection": {"projects": collection},
            "project": {
                "name": repository["name"],
                "rootName": repository["name"],
                "path": "",
                "directory": "",
                "repositoryUrl": repository["repositoryUrl"],
                "downloaded": False,
                "detectedBy": "catalog",
                "blendFiles": [],
            },
            "config": config,
            "git": git,
            "tools": self._tool_state(),
            "defaults": self._status_defaults(),
        }

    def _stored_repository_project(self, repository_url: str) -> tuple[Path, Path] | None:
        slug = _repository_slug(repository_url)
        if not slug:
            return None
        store = self._read_store()
        candidates = []
        bound_path = store.get("repositoryPaths", {}).get(slug)
        if bound_path:
            candidates.append(bound_path)
        for record in store.get("projects", {}).values():
            if not isinstance(record, dict) or _repository_slug(record.get("repositoryUrl")) != slug:
                continue
            if record.get("blendFile"):
                candidates.append(record["blendFile"])

        seen = set()
        for candidate in candidates:
            path = _safe_text(candidate, 1000)
            if not path or os.path.normcase(path).casefold() in seen:
                continue
            seen.add(os.path.normcase(path).casefold())
            try:
                root, blend_file, _ = self._resolve_project(path)
            except (OSError, ValueError):
                continue
            remote_url = self._git_output(root, ["remote", "get-url", "origin"])
            if _repository_slug(remote_url) == slug:
                return root, blend_file
        return None

    def status(self, project="", refresh_remote=False) -> dict:
        raw = _safe_text(project, 1000)

        if raw and not _github_match(raw):
            root, blend_file, source = self._resolve_project(raw)
            return self._local_status(root, blend_file, source, refresh_remote=refresh_remote)

        store = self._read_store()
        selected_repository_url = _repository_web_url(raw) if raw else store.get("lastRepository", "")
        local_project = self._stored_repository_project(selected_repository_url)
        if local_project:
            return self._local_status(
                local_project[0],
                local_project[1],
                "repository",
                refresh_remote=refresh_remote,
            )

        collection = self._project_collection()
        repository = self._collection_project(selected_repository_url, collection)
        if not repository:
            repository = self._collection_project(store.get("lastProject"), collection)
        if not repository and collection:
            repository = collection[0]
        if repository:
            if not repository.get("downloaded"):
                return self._cloud_status(repository, collection)
            return self._local_status(
                Path(repository["directory"]),
                Path(repository["path"]),
                "saved",
                collection,
                refresh_remote=refresh_remote,
            )

        root, blend_file, source = self._resolve_project("")
        return self._local_status(root, blend_file, source, refresh_remote=refresh_remote)

    def _select_blend_file(self) -> str:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as error:
            raise ValueError("The Blender project picker is unavailable") from error

        store = self._read_store()
        saved = Path(store.get("lastProject") or "").expanduser()
        initial_directory = saved.parent if saved.is_file() else None
        if not initial_directory or not initial_directory.is_dir():
            initial_directory = next((root for root in self.project_roots if root.is_dir()), Path.home())

        window = tk.Tk()
        try:
            window.withdraw()
            window.wm_attributes("-topmost", 1)
            window.update_idletasks()
            return filedialog.askopenfilename(
                parent=window,
                title="Add Blender project",
                initialdir=str(initial_directory),
                filetypes=(("Blender project", "*.blend"), ("All files", "*.*")),
            ) or ""
        finally:
            window.destroy()

    def add_project(self, payload: dict) -> dict:
        project = _safe_text(payload.get("project"), 1000) or self._select_blend_file()
        if not project:
            return {"ok": True, "cancelled": True}
        root, blend_file, _ = self._resolve_project(project)
        git = self._git_status(root, blend_file)
        if not git.get("repositoryWebUrl") or not git.get("hasCommit"):
            raise ValueError("Publish this Blender project to GitHub before adding it to GitHub Coop")
        with self._config_lock:
            store = self._read_store()
            self._pin_in_store(store, blend_file)
            self._pin_repository_in_store(store, git["repositoryWebUrl"], blend_file)
            store["lastProject"] = str(blend_file)
            self._write_store(store)
        result = self.status(str(blend_file))
        result["message"] = "GitHub repository added"
        return result

    def reorder_projects(self, payload: dict) -> dict:
        selected = _safe_text(payload.get("project"), 1000)
        available = self._project_collection()
        requested = payload.get("order")
        if not isinstance(requested, list):
            raise ValueError("GitHub repository order must be a list")

        available_by_slug = {
            _repository_slug(item["repositoryUrl"]): item
            for item in available
            if _repository_slug(item.get("repositoryUrl"))
        }
        available_by_path = {
            _path_key(Path(item["path"])): item
            for item in available
            if item.get("path")
        }
        ordered = []
        seen = set()
        for item in requested:
            raw = _safe_text(item, 1000)
            slug = _repository_slug(raw)
            repository = available_by_slug.get(slug) if slug else None
            if not repository and raw:
                try:
                    repository = available_by_path.get(_path_key(Path(raw).expanduser()))
                except (OSError, RuntimeError):
                    repository = None
            if not repository:
                continue
            slug = _repository_slug(repository["repositoryUrl"])
            if slug in seen:
                continue
            seen.add(slug)
            ordered.append(repository)
        ordered.extend(
            item for item in available
            if _repository_slug(item["repositoryUrl"]) not in seen
        )

        with self._config_lock:
            store = self._read_store()
            store["repositoryOrder"] = [item["repositoryUrl"] for item in ordered]
            store["projectOrder"] = [item["path"] for item in ordered if item.get("downloaded") and item.get("path")]
            selected_repository = self._collection_project(selected, ordered) or (ordered[0] if ordered else None)
            if selected_repository:
                store["lastRepository"] = selected_repository["repositoryUrl"]
                if selected_repository.get("path"):
                    store["lastProject"] = selected_repository["path"]
            self._write_store(store)
        result = self.status(selected_repository["repositoryUrl"] if selected_repository else "")
        result["message"] = "GitHub repository order saved"
        return result

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

    def _repository_selection(self, payload: dict) -> dict:
        raw_repository = _safe_text(payload.get("repositoryUrl"), 500)
        raw_project = _safe_text(payload.get("project"), 1000)
        if raw_project and not raw_repository and not _github_match(raw_project):
            root, blend_file, _ = self._resolve_project(raw_project)
            config = self._stored_config(blend_file)
            git = self._git_status(root, blend_file)
            return {
                "name": blend_file.stem,
                "file": blend_file.name,
                "path": str(blend_file),
                "directory": str(root),
                "repositoryUrl": git.get("repositoryWebUrl") or _repository_web_url(config.get("repositoryUrl")),
                "remoteUrl": git.get("remoteUrl") or config.get("repositoryUrl", ""),
                "version": git.get("lastTag") or config.get("version", ""),
                "state": git.get("state") or "uninitialized",
                "defaultBranch": git.get("branch") or "main",
                "visibility": config.get("visibility") or "private",
                "downloaded": True,
                "catalog": False,
            }

        collection = self._project_collection()
        store = self._read_store()
        repository = (
            self._collection_project(raw_repository, collection)
            or self._collection_project(raw_project, collection)
        )
        if not repository and not raw_repository and not raw_project:
            repository = self._collection_project(store.get("lastRepository"), collection)
        if repository:
            return repository

        remote_url = raw_repository or (raw_project if _github_match(raw_project) else "")
        if remote_url:
            web_url = _repository_web_url(remote_url)
            return {
                "name": web_url.rsplit("/", 1)[-1],
                "file": "",
                "path": "",
                "directory": "",
                "repositoryUrl": web_url,
                "remoteUrl": _normalize_repository_url(remote_url),
                "version": "",
                "state": "cloud",
                "defaultBranch": "main",
                "visibility": "private",
                "downloaded": False,
                "catalog": False,
            }

        root, blend_file, _ = self._resolve_project(raw_project)
        config = self._stored_config(blend_file)
        git = self._git_status(root, blend_file)
        return {
            "name": blend_file.stem,
            "file": blend_file.name,
            "path": str(blend_file),
            "directory": str(root),
            "repositoryUrl": git.get("repositoryWebUrl") or _repository_web_url(config.get("repositoryUrl")),
            "remoteUrl": git.get("remoteUrl") or config.get("repositoryUrl", ""),
            "version": git.get("lastTag") or config.get("version", ""),
            "state": git.get("state") or "uninitialized",
            "defaultBranch": git.get("branch") or "main",
            "visibility": config.get("visibility") or "private",
            "downloaded": True,
            "catalog": False,
        }

    def _remember_repository(self, repository: dict) -> None:
        with self._config_lock:
            store = self._read_store()
            blend_file = Path(repository["path"]) if repository.get("path") else None
            self._pin_repository_in_store(store, repository.get("repositoryUrl", ""), blend_file)
            if repository.get("path"):
                store["lastProject"] = repository["path"]
            self._write_store(store)

    def open_repository(self, payload: dict) -> dict:
        repository = self._repository_selection(payload)
        url = repository.get("repositoryUrl") or "https://github.com/new"
        self._remember_repository(repository)
        webbrowser.open(url)
        return {
            "ok": True,
            "url": url,
            "project": repository.get("path", ""),
            "repositoryUrl": repository.get("repositoryUrl", ""),
            "downloaded": bool(repository.get("downloaded")),
        }

    def open_folder(self, payload: dict) -> dict:
        repository = self._repository_selection(payload)
        if not repository.get("downloaded") or not repository.get("directory"):
            raise ValueError("Clone this repository with GitHub Desktop before opening its files")
        root = Path(repository["directory"])
        blend_file = Path(repository["path"])
        self._remember_repository(repository)
        if sys.platform == "win32":
            os.startfile(str(root))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(root)], **_hidden_subprocess_kwargs())
        else:
            subprocess.Popen(["xdg-open", str(root)], **_hidden_subprocess_kwargs())
        return {"ok": True, "path": str(root), "project": str(blend_file)}

    def open_desktop(self, payload: dict) -> dict:
        repository = self._repository_selection(payload)
        downloaded = bool(repository.get("downloaded") and repository.get("directory"))
        repository_url = repository.get("repositoryUrl") or _repository_web_url(repository.get("remoteUrl"))
        if not downloaded and not repository_url:
            raise ValueError("A GitHub repository URL is required before cloning")
        action = "open" if downloaded else "clone"
        target = repository["directory"] if downloaded else repository_url
        self._remember_repository(repository)

        cli = self._github_desktop_cli()
        if cli:
            arguments = [action, target]
            if cli.suffix.casefold() in {".bat", ".cmd"}:
                command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(cli), *arguments]
            else:
                command = [str(cli), *arguments]
            self._launch_desktop_command(command, repository["directory"] if downloaded else "")
            return {
                "ok": True,
                "path": repository.get("directory", ""),
                "project": repository.get("path", ""),
                "repositoryUrl": repository_url,
                "downloaded": downloaded,
                "action": action,
                "fallback": False,
            }

        app = self._github_desktop_app()
        if app:
            switch = f"--cli-open={target}" if downloaded else f"--cli-clone={target}"
            self._launch_desktop_command(
                [str(app), switch],
                repository["directory"] if downloaded else "",
            )
            return {
                "ok": True,
                "path": repository.get("directory", ""),
                "project": repository.get("path", ""),
                "repositoryUrl": repository_url,
                "downloaded": downloaded,
                "action": action,
                "fallback": False,
            }

        url = repository_url or "https://desktop.github.com/"
        webbrowser.open(url)
        return {
            "ok": True,
            "url": url,
            "project": repository.get("path", ""),
            "repositoryUrl": repository_url,
            "downloaded": downloaded,
            "action": action,
            "fallback": True,
        }
