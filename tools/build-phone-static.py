"""Build a public, static phone app without the user's private runtime data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
PHONE_ASSETS = ("index.html", "styles.css", "app.js", "store.js", "sw.js", "manifest.webmanifest")
ICONS = ("phone-icon-180.png", "phone-icon-192.png", "phone-icon-512.png")
PUBLIC_TRACKS = (
    "Airborne.mp3", "Around the World.mp3", "Dancin.mp3", "Final Step.mp3", "Fire Inside.mp3",
    "Get Lucky.mp3", "House of Memories.mp3", "Liquid Roller.mp3", "Luminescence.mp3",
    "Ma rose éternelle.mp3", "Never Be Alone.mp3", "Never Slow Me Down.mp3", "Outrun.mp3",
    "Redline.mp3", "Stasis.mp3", "Toxic.mp3",
)
PUBLIC_LYRICS = frozenset((
    "Around the World.lrc", "Dancin.lrc", "Get Lucky.lrc", "House of Memories.lrc",
    "Never Be Alone.lrc", "Toxic.lrc", "Ma rose éternelle.lrc",
    "Ma rose éternelle.en.lrc", "Ma rose éternelle.zh.lrc",
))
LANGUAGES = {"en": "English", "zh": "中文", "fr": "Français"}
SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|[\dA-Za-z-]*[A-Za-z-][\dA-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[\dA-Za-z-]*[A-Za-z-][\dA-Za-z-]*))*)?"
    r"(?:\+[\dA-Za-z-]+(?:\.[\dA-Za-z-]+)*)?",
    flags=re.ASCII,
)


def _source_file(directory, name):
    directory = Path(directory).resolve()
    source = directory / name
    if source.is_symlink() or not source.is_file() or source.resolve().parent != directory:
        raise ValueError(f"Missing or linked outside the public source directory: {name}")
    return source


def _build_version(project, phone_dir, override=None):
    if override is not None:
        version, label = override, "--version"
    else:
        source = phone_dir / "version.json"
        if source.is_symlink():
            raise ValueError("phone/version.json must not be a linked file.")
        if source.exists():
            source, label = _source_file(phone_dir, "version.json"), "phone/version.json"
        else:
            source, label = _source_file(project, "app-manifest.json"), "app-manifest.json"
        try:
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"Invalid {label} version.") from error
        version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError(f"Invalid {label} version.")
    return version


def _public_music_defaults(project):
    source = project / "release-defaults.json"
    if source.is_symlink():
        raise ValueError("release-defaults.json must not be a linked file.")
    payload = {}
    if source.exists():
        source = _source_file(project, "release-defaults.json")
        try:
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as error:
            raise ValueError("Invalid public release-defaults.json.") from error
        if not isinstance(payload, dict):
            raise ValueError("Invalid public release-defaults.json.")
    music = payload.get("music") or {}
    if not isinstance(music, dict):
        raise ValueError("Invalid public music defaults.")
    order = []
    for name in music.get("order") if isinstance(music.get("order"), list) else []:
        if isinstance(name, str) and name in PUBLIC_TRACKS and name not in order:
            order.append(name)
    order.extend(name for name in PUBLIC_TRACKS if name not in order)
    raw_tiers = music.get("tiers") if isinstance(music.get("tiers"), dict) else {}
    tiers = {name: tier for name, tier in raw_tiers.items()
             if name in PUBLIC_TRACKS and tier in ("first", "second", "third")}
    # Only the already published title-only filenames cross into the phone
    # catalog; private cache paths and unrelated release defaults are ignored.
    return {"order": order, "tiers": tiers}


def _language(source):
    with source.open("rb") as stream:
        data = stream.read(256 * 1024 + 1)
    if len(data) > 256 * 1024:
        raise ValueError(f"Public lyrics exceed 256 KiB: {source.name}")
    text = data.decode("utf-8-sig")
    for line in text.splitlines()[:12]:
        match = re.fullmatch(r"\s*\[(?:lang|language):([^\]]+)\]\s*", line, flags=re.IGNORECASE)
        if match and match[1].strip().lower() in LANGUAGES:
            return match[1].strip().lower()
    return ""


def _output_is_safe(output, allowed):
    if not output.exists():
        return
    if not output.is_dir() or output.is_symlink() or getattr(output, "is_junction", lambda: False)():
        raise ValueError("The output directory must be a normal directory.")
    # The build has only two flat levels. Never recurse into an unknown folder,
    # delete it, or silently include files left by another kind of build.
    for child in output.iterdir():
        if child.is_symlink() or getattr(child, "is_junction", lambda: False)():
            raise ValueError("The output directory contains a linked path.")
        if child.name == "music" and child.is_dir():
            for item in child.iterdir():
                relative = "music/" + item.name
                if not item.is_file() or item.is_symlink() or relative not in allowed:
                    raise ValueError("The output directory contains unknown files; use a clean output directory.")
        elif not child.is_file() or child.name not in allowed:
            raise ValueError("The output directory contains unknown files; use a clean output directory.")


def _normal_output_directory(output_dir):
    output = Path(output_dir)
    if output.drive and not output.root:
        raise ValueError("Use an absolute output path instead of a drive-relative path.")
    if not output.is_absolute():
        output = Path.cwd() / output
    # Inspect the original components before resolving: an existing link in an
    # ancestor (including one followed by '..') must never become a write route.
    for component in (output, *output.parents):
        if component.is_symlink() or getattr(component, "is_junction", lambda: False)():
            raise ValueError("The output directory must not be a linked path.")
    # Windows short names are aliases for ordinary directories, not links.
    # Normalize them before comparing destinations or rebuilding an existing app.
    return output.resolve()


def _check_relative_assets(name, text):
    if name.endswith(".html"):
        references = re.findall(r"(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
    elif name.endswith(".webmanifest"):
        manifest = json.loads(text)
        references = [manifest.get("start_url", ""), manifest.get("scope", "")]
        references += [item.get("src", "") for item in manifest.get("icons", [])]
    else:
        return
    if any(not isinstance(value, str) or value.startswith("/") for value in references):
        raise ValueError(f"Static phone assets need relative URLs for project subdirectories: {name}")


def build_static(project_dir, output_dir, make_zip=False, version=None):
    project = Path(project_dir).resolve()
    output = _normal_output_directory(output_dir)
    phone_dir, music_dir = project / "phone", project / "public-music"
    if (phone_dir.is_symlink() or music_dir.is_symlink()
            or getattr(phone_dir, "is_junction", lambda: False)() or getattr(music_dir, "is_junction", lambda: False)()
            or phone_dir.resolve().parent != project or music_dir.resolve().parent != project):
        raise ValueError("Public source directories must not point outside the project.")
    version = _build_version(project, phone_dir, version)
    music_defaults = _public_music_defaults(project)
    assets = {name: _source_file(phone_dir, name) for name in PHONE_ASSETS}
    # Include all small code assets, not the large public audio files. A rebuilt
    # shell can then refresh even when a maintenance build keeps its app version.
    build_digest = hashlib.sha256(version.encode("utf-8"))
    build_digest.update(b"\0music-defaults\0")
    build_digest.update(json.dumps(music_defaults, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8"))
    phone_text = {}
    for name in PHONE_ASSETS:
        source_bytes = assets[name].read_bytes()
        phone_text[name] = source_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        _check_relative_assets(name, phone_text[name])
        build_digest.update(b"\0" + name.encode("utf-8") + b"\0")
        build_digest.update(source_bytes)
    for name in ICONS:
        icon = _source_file(phone_dir, name)
        build_digest.update(b"\0" + name.encode("utf-8") + b"\0")
        build_digest.update(icon.read_bytes())
        assets[name] = icon
    build_id = build_digest.hexdigest()[:16]
    tracks = []
    for name in music_defaults["order"]:
        source = _source_file(music_dir, name)
        relative = "music/" + name
        assets[relative] = source
        stem = source.stem
        default = music_dir / (stem + ".lrc")
        variants = []
        default_source, default_language = "", ""
        if default.name in PUBLIC_LYRICS and default.is_file():
            default = _source_file(music_dir, default.name)
            default_source, default_language = "music/" + default.name, _language(default)
            assets[default_source] = default
            if default_language:
                variants.append({"code": default_language, "label": LANGUAGES[default_language], "source": default_source})
        for code, label in LANGUAGES.items():
            sidecar = music_dir / f"{stem}.{code}.lrc"
            if sidecar.name not in PUBLIC_LYRICS or not sidecar.is_file():
                continue
            sidecar = _source_file(music_dir, sidecar.name)
            _language(sidecar)  # Validate bounded UTF-8 even without a header.
            sidecar_source = "music/" + sidecar.name
            assets[sidecar_source] = sidecar
            variants = [item for item in variants if item["code"] != code]
            variants.append({"code": code, "label": label, "source": sidecar_source})
        if not default_source and variants:
            default_source, default_language = variants[0]["source"], variants[0]["code"]
        tracks.append({"path": "builtin/" + name, "name": stem, "type": "mp3", "size": source.stat().st_size,
                       "source": relative, "lyrics": bool(default_source), "lyricsSource": default_source,
                       "lyricsLanguage": default_language, "lyricsLanguages": variants})
        if name in music_defaults["tiers"]:
            tracks[-1]["tier"] = music_defaults["tiers"][name]
    generated = {"music-catalog.json", "version.json"}
    allowed = set(assets) | generated
    _output_is_safe(output, allowed)
    # Output may be in a separate backup directory, but never inside the source
    # app or public media directories where the build could overwrite originals.
    resolved_output = output.resolve()
    if resolved_output == project or resolved_output.is_relative_to(phone_dir.resolve()) or resolved_output.is_relative_to(music_dir.resolve()):
        raise ValueError("Choose an output directory separate from source files.")
    output.mkdir(parents=True, exist_ok=True)
    for relative, source in assets.items():
        target = output / relative
        if target.exists() and target.resolve() != target:
            raise ValueError("A build destination is a linked path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative in PHONE_ASSETS:
            text = (phone_text[relative].replace("__CONSOLE_PHONE_VERSION__", version)
                    .replace("__CONSOLE_PHONE_BUILD__", build_id))
            target.write_text(text, encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(source, target)
    (output / "music-catalog.json").write_text(json.dumps({"version": 1, "tracks": tracks}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "version.json").write_text(json.dumps({"version": version, "buildId": build_id, "offlineFirst": True,
        "builtAt": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    result = {"outputDirectory": str(output), "version": version, "buildId": build_id, "assetCount": len(allowed),
              "musicTracks": len(tracks), "musicBytes": sum(item["size"] for item in tracks)}
    if make_zip:
        archive = output.parent / f"CodexConsole-iPhone-{version}.zip"
        if archive.exists() and (not archive.is_file() or archive.is_symlink()):
            raise ValueError("The archive destination is not a normal file.")
        # Audio is already compressed; ZIP_STORED avoids a large extra CPU job.
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
            for relative in sorted(allowed):
                bundle.write(output / relative, relative)
        result["archive"] = str(archive)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=str(PROJECT))
    parser.add_argument("--output-dir", default=str(PROJECT / "dist-phone"))
    parser.add_argument("--version", help="Override the independent phone version for this build.")
    parser.add_argument("--zip", action="store_true", help="Also write a versioned static ZIP beside the output directory.")
    args = parser.parse_args()
    print(json.dumps(build_static(args.project_dir, args.output_dir, args.zip, args.version), ensure_ascii=False))


if __name__ == "__main__":
    main()
