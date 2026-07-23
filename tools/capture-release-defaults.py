#!/usr/bin/env python3
"""Capture the publisher's current music and module layout for new installs."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "release-defaults.json"
PUBLIC_MUSIC_DIR = PROJECT_ROOT / "public-music"
VALID_TIERS = {"first", "second", "third"}
MODULE_KEYS = ("order", "archive", "deepArchive", "deleted", "lastModule")


def read_json(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_json(url, timeout):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected a JSON object from {url}")
    return payload


def clean_path(value):
    return str(value or "").replace("\\", "/").lstrip("/").strip()


def unique_strings(value):
    result = []
    for item in value if isinstance(value, list) else []:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def packaged_music_files():
    return sorted(PUBLIC_MUSIC_DIR.glob("*.mp3"), key=lambda path: path.name.casefold())


def capture_music(payload, previous):
    tracks = payload.get("tracks") if isinstance(payload.get("tracks"), list) else []
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    packaged = packaged_music_files()
    packaged_by_name = {path.stem.casefold(): path.name for path in packaged}

    active_to_packaged = {}
    for track in tracks:
        if not isinstance(track, dict):
            continue
        active_path = clean_path(track.get("path"))
        packaged_name = packaged_by_name.get(str(track.get("name") or "").strip().casefold())
        if active_path and packaged_name:
            active_to_packaged[active_path.casefold()] = packaged_name

    def map_path(value):
        clean = clean_path(value)
        if not clean:
            return ""
        mapped = active_to_packaged.get(clean.casefold())
        if mapped:
            return mapped
        return next((path.name for path in packaged if path.name.casefold() == Path(clean).name.casefold()), "")

    tiers = {}
    raw_tiers = state.get("tiers") if isinstance(state.get("tiers"), dict) else {}
    for active_path, tier in raw_tiers.items():
        packaged_name = map_path(active_path)
        clean_tier = str(tier or "").strip().lower()
        if packaged_name and clean_tier in VALID_TIERS:
            tiers[packaged_name] = clean_tier

    order = []
    for active_path in state.get("order") if isinstance(state.get("order"), list) else []:
        packaged_name = map_path(active_path)
        if packaged_name and packaged_name not in order:
            order.append(packaged_name)

    previous_order = previous.get("order") if isinstance(previous.get("order"), list) else []
    for name in [*previous_order, *(path.name for path in packaged)]:
        packaged_name = map_path(name)
        if packaged_name and packaged_name not in order:
            order.append(packaged_name)

    if len(order) != len(packaged):
        raise RuntimeError(f"Captured {len(order)} of {len(packaged)} packaged music tracks")

    return {
        "tiers": {name: tiers[name] for name in order if name in tiers},
        "order": order,
        "promotedLibraryTracks": {},
    }


def capture_modules(payload, previous):
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    if not isinstance(state.get("order"), list):
        return previous

    result = {}
    for key in MODULE_KEYS:
        if key == "lastModule":
            result[key] = str(state.get(key) or previous.get(key) or "music").strip().lower()
        else:
            result[key] = unique_strings(state.get(key))
    return result


def write_json_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8898", help="Running Codex Console base URL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Release defaults JSON path")
    parser.add_argument("--timeout", type=float, default=8.0, help="API timeout in seconds")
    args = parser.parse_args(argv)

    previous = read_json(args.output)
    base_url = args.api_url.rstrip("/")
    try:
        music_payload = fetch_json(f"{base_url}/api/music", args.timeout)
        console_payload = fetch_json(f"{base_url}/api/console/state", args.timeout)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as error:
        print(f"Unable to capture release defaults from {base_url}: {error}", file=sys.stderr)
        return 1

    previous_music = previous.get("music") if isinstance(previous.get("music"), dict) else {}
    previous_modules = previous.get("modules") if isinstance(previous.get("modules"), dict) else {}
    music = capture_music(music_payload, previous_music)
    modules = capture_modules(console_payload, previous_modules)
    unchanged = (
        previous.get("schemaVersion") == 1
        and previous.get("music") == music
        and previous.get("modules") == modules
    )
    captured_at = str(previous.get("capturedAt") or "") if unchanged else ""
    if not captured_at:
        captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = {
        "schemaVersion": 1,
        "capturedAt": captured_at,
        "music": music,
        "modules": modules,
    }
    write_json_atomic(args.output, result)
    print(f"Captured {len(result['music']['order'])} songs and {len(result['modules'].get('order', []))} modules")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
