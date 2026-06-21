import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import html
import io
import json
import math
import mimetypes
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.request
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
import zlib


def hidden_subprocess_kwargs():
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


APP_DIR = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8898
WORLD_CACHE = APP_DIR / "cache" / "world.geojson"
TRANSLATION_CACHE = APP_DIR / "cache" / "translations.json"
WALLPAPER_DIR = APP_DIR / "wallpapers"
DEFAULT_MUSIC_DIR = Path(r"D:\MyMP3s") if Path(r"D:\MyMP3s").exists() else APP_DIR / "music"
MUSIC_DIR = Path(os.environ.get("CODEX_CONTROL_MUSIC_DIR", str(DEFAULT_MUSIC_DIR)))
MUSIC_LIBRARY_DIR = MUSIC_DIR / "libraries"
MUSIC_LIBRARY_FILE = APP_DIR / "cache" / "music_libraries.json"
MUSIC_STATE_FILE = APP_DIR / "cache" / "music_state.json"
MUSIC_STATE_BACKUP_FILE = APP_DIR / "cache" / "music_state.previous.json"
CONSOLE_STATE_FILE = APP_DIR / "cache" / "console_state.json"
YOUTUBE_COOKIE_DIR = APP_DIR / "cache" / "cookies"
YOUTUBE_COOKIE_FILE = YOUTUBE_COOKIE_DIR / "youtube.cookies.txt"
MATERIAL_SOURCE_DIR = Path(os.environ.get("CODEX_CONTROL_MATERIAL_SOURCE_DIR", str(Path.home() / "Downloads")))
CODEX_TEMP_DIR = Path(os.environ.get("CODEX_CONTROL_TEMP_DIR", str(APP_DIR.parent / "Temp")))
BUILDER_TEXTURE_DIR = Path(os.environ.get("CODEX_CONTROL_BUILDER_TEXTURE_DIR", r"D:\Unity Projects\RandomRealm2\Assets\Art\Generated\BuildMaterials\Textures"))
BLENDER_REPLACEMENT_TEXTURE_DIR = Path(os.environ.get("CODEX_CONTROL_BLENDER_REPLACEMENT_TEXTURE_DIR", str(BUILDER_TEXTURE_DIR / "_codex_replacements")))
BLENDER_TEXTURE_PACKAGE_DIR = Path(os.environ.get("CODEX_CONTROL_BLENDER_TEXTURE_PACKAGE_DIR", r"D:\Blender\~Import-Export\TexturePackages"))
BLENDER_PROJECT_TEXTURE_PACKAGE_DIRNAME = "_codex_packages"
BLENDER_TEXTURE_PACKAGE_APPLIED_FILENAME = "applied.json"
BLENDER_LIVE_SELECTION_FILE = APP_DIR / "cache" / "blender_live_selection.json"
BLENDER_LIVE_SELECTION_MAX_AGE_SECONDS = 8
NATIVE_FILE_DRAG_SOURCE = APP_DIR / "tools" / "NativeFileDrag.cs"
NATIVE_FILE_DRAG_EXE = APP_DIR / "tools" / "NativeFileDrag.exe"
RANDOMREALM_PROJECT_DIR = Path(os.environ.get("CODEX_CONTROL_RANDOMREALM_PROJECT_DIR", r"D:\Unity Projects\RandomRealm2"))
BLENDER_TO_UNITY_EXPORT_DIR = Path(os.environ.get("CODEX_CONTROL_BLENDER_TO_UNITY_EXPORT_DIR", r"D:\Blender\~Import-Export\BuilderToUnity"))
UNITY_TEMP_BRIDGE_DIR = RANDOMREALM_PROJECT_DIR / "Assets" / "~Temp" / "BlenderBridge"
UNITY_BRIDGE_REQUEST_FILE = RANDOMREALM_PROJECT_DIR / "Temp" / "CodexBlenderToUnity.request.json"
ENABLE_BLENDER_MUTATION_API = os.environ.get("CODEX_CONTROL_ENABLE_BLENDER_MUTATION_API", "").strip().lower() in {"1", "true", "yes", "on"}
BLENDER_MUTATION_API_PATHS = {
    "/api/randomrealm/blender/create-empty-texture",
    "/api/randomrealm/blender/add-texture",
    "/api/randomrealm/blender/remove-textures",
    "/api/randomrealm/blender/remove-texture",
    "/api/randomrealm/blender/replace-texture",
}
STEAMWORK_SDK_TOOLS_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_SDK_TOOLS_DIR", r"D:\Steamwork\Steamwork\sdk\tools"))
RANDOMREALM_PUBLISH_DIR = Path(os.environ.get("CODEX_CONTROL_RANDOMREALM_PUBLISH_DIR", str(STEAMWORK_SDK_TOOLS_DIR / "ContentBuilder")))
STEAMWORK_GAMECONTENT_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_GAMECONTENT_DIR", str(RANDOMREALM_PUBLISH_DIR / "content")))
STEAMWORK_PUBLISH_TOOL_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_PUBLISH_TOOL_DIR", str(STEAMWORK_SDK_TOOLS_DIR / "SteamPipeGUI")))
STEAMWORK_PUBLISH_TOOL_EXE = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_PUBLISH_TOOL_EXE", str(STEAMWORK_PUBLISH_TOOL_DIR / "SteamPipeGUI.exe")))
RANDOMREALM_PROMO_DIR = Path(os.environ.get("CODEX_CONTROL_RANDOMREALM_PROMO_DIR", str(RANDOMREALM_PROJECT_DIR / "Screenshots")))
STEAMWORK_ASSET_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_ASSET_DIR", r"D:\ArtAsset"))
STEAMWORK_STORE_ASSET_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_STORE_ASSET_DIR", str(STEAMWORK_ASSET_DIR / "Game" / "Store Assets")))
STEAMWORK_SCREENSHOT_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_SCREENSHOT_DIR", str(STEAMWORK_ASSET_DIR / "Game" / "ScreenShots Assets")))
STEAMWORK_VIDEO_DIR = Path(os.environ.get("CODEX_CONTROL_STEAMWORK_VIDEO_DIR", str(STEAMWORK_ASSET_DIR / "Game" / "Demo vedio")))
STEAMWORK_THUMB_DIR = APP_DIR / "cache" / "steamwork_thumbs"
DEFAULT_BLENDER_PROJECT_ROOTS = [
    Path(r"D:\Blender\Projects"),
    Path(r"D:\ArtAsset"),
    Path(r"D:\Blender"),
    RANDOMREALM_PROJECT_DIR,
    Path.home() / "Documents",
]
BLENDER_PROJECT_ROOTS = [
    Path(item.strip())
    for item in os.environ.get("CODEX_CONTROL_BLENDER_PROJECT_ROOTS", os.environ.get("CODEX_CONTROL_BLENDER_PROJECT_DIRS", "")).split(";")
    if item.strip()
] or DEFAULT_BLENDER_PROJECT_ROOTS
BLENDER_PROJECT_FILES = [
    Path(item.strip())
    for item in os.environ.get("CODEX_CONTROL_BLENDER_PROJECTS", "").split(";")
    if item.strip()
]
STEAMWORKS_URL = os.environ.get("CODEX_CONTROL_STEAMWORKS_URL", "https://partner.steamgames.com/")
WORLD_CONSOLE_DIR = Path(os.environ.get("CODEX_CONTROL_WORLD_CONSOLE_DIR", str(APP_DIR.parent / "WorldConsole")))
WORLD_CONSOLE_RELEASES_URL = os.environ.get("CODEX_WORLD_CONSOLE_RELEASES_URL", "").strip()
ORIGINAL_WALLPAPER_RECORD = APP_DIR / "cache" / "original_wallpaper.json"
WALLPAPER_ORDER_FILE = APP_DIR / "cache" / "wallpaper_order.json"
STARTUP_SCRIPT_NAME = "Codex-Control-Hotkey.vbs"
HOTKEY_LAUNCHER = APP_DIR / "Start-WorldConsole-Hotkey.vbs"
WALLPAPER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
MATERIAL_PACKAGE_EXTENSIONS = {".zip"}
MATERIAL_TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp", ".webp", ".exr", ".hdr"}
PREVIEWABLE_TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
MATERIAL_CANDIDATE_EXTENSIONS = MATERIAL_PACKAGE_EXTENSIONS | MATERIAL_TEXTURE_EXTENSIONS
BLENDER_PROJECT_EXTENSIONS = {".blend"}
STEAMWORK_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".ico"}
STEAMWORK_VIDEO_EXTENSIONS = {".mp4", ".mov", ".wmv"}
STEAMWORK_ASSET_EXTENSIONS = STEAMWORK_IMAGE_EXTENSIONS | STEAMWORK_VIDEO_EXTENSIONS | {".psd"}
CONSOLE_MODULE_HREFS = {
    "manager": "manager.html",
    "workspace": "workspace.html",
    "blender": "blender.html",
    "unity": "unity.html",
    "steamwork": "steamwork.html",
    "randomrealm": "randomrealm.html",
    "music": "music.html",
    "wallpaper": "index.html",
}
CONSOLE_EDITION_MODULES = {
    "developer": tuple(CONSOLE_MODULE_HREFS.keys()),
    "lite": ("wallpaper", "music"),
}
CONSOLE_PAGE_PATHS = {"", "/", *{f"/{href}" for href in CONSOLE_MODULE_HREFS.values()}}


def sanitize_console_edition(value):
    clean = str(value or "").strip().lower()
    return clean if clean in CONSOLE_EDITION_MODULES else "developer"


CONSOLE_CONFIG = {
    "edition": sanitize_console_edition(os.environ.get("CODEX_CONTROL_EDITION")),
}


def current_console_edition():
    return sanitize_console_edition(CONSOLE_CONFIG.get("edition"))


def console_module_ids(edition=None):
    return CONSOLE_EDITION_MODULES.get(sanitize_console_edition(edition or current_console_edition()), CONSOLE_EDITION_MODULES["developer"])


def console_module_allowed(module_id, edition=None):
    return str(module_id or "") in set(console_module_ids(edition))


def console_module_id_from_href(href):
    clean = str(href or "").strip().lstrip("/")
    for module_id, module_href in CONSOLE_MODULE_HREFS.items():
        if module_href == clean:
            return module_id
    return "wallpaper"


def console_edition_payload():
    edition = current_console_edition()
    module_ids = list(console_module_ids(edition))
    return {
        "edition": edition,
        "modules": module_ids,
        "hrefs": {module_id: CONSOLE_MODULE_HREFS[module_id] for module_id in module_ids if module_id in CONSOLE_MODULE_HREFS},
    }


def console_edition_query(edition=None):
    return "?edition=lite" if sanitize_console_edition(edition or current_console_edition()) == "lite" else ""


def console_lite_redirect_path(parsed):
    if current_console_edition() != "lite":
        return ""
    query = urllib.parse.parse_qs(parsed.query)
    page = parsed.path or "/index.html"
    module_id = console_module_id_from_href(page)
    if console_module_allowed(module_id, "lite") and query.get("edition", [""])[0] == "lite":
        return ""
    href = CONSOLE_MODULE_HREFS[module_id] if console_module_allowed(module_id, "lite") else CONSOLE_MODULE_HREFS["wallpaper"]
    return f"/{href}?edition=lite"

MAX_WALLPAPER_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_MUSIC_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_WORKZONE_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_STEAMWORK_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_COOKIE_UPLOAD_BYTES = 5 * 1024 * 1024
GOOGLE_TRANSLATE_ENDPOINT = "https://translation.googleapis.com/language/translate/v2"
TRANSLATION_TARGET = "zh-TW"
MUSIC_LIBRARY_LOCK = threading.Lock()
BLENDER_MUTATION_LOCK = threading.Lock()
BLENDER_MUTATION_KEYS = {}
BLENDER_MUTATION_TTL_SECONDS = 8

NEWS_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]

WORLD_GEOJSON_URLS = [
    "https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson",
    "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
]

IMPORTANT_TERMS = {
    "war": 2,
    "ceasefire": 2,
    "invasion": 2,
    "strike": 2,
    "missile": 2,
    "summit": 2,
    "election": 2,
    "president": 1,
    "minister": 1,
    "court": 1,
    "sanction": 1,
    "tariff": 1,
    "trade": 1,
    "nuclear": 2,
    "hostage": 2,
    "china": 1,
    "taiwan": 2,
    "russia": 1,
    "ukraine": 2,
    "iran": 2,
    "gaza": 2,
    "israel": 1,
    "trump": 1,
    "xi": 1,
    "putin": 1,
}

NON_EVENT_TITLE_TERMS = [
    "as it happened",
    "comment",
    "commentary",
    "live",
    "podcast",
    "opinion",
    "analysis",
    "explainer",
    "what we know",
    "what to know",
    "your questions answered",
    "travelogue",
    "review",
]

HYPOTHETICAL_TITLE_TERMS = [
    "could",
    "if",
    "may",
    "might",
    "possible",
    "chance",
    "fears",
    "concerns",
]

HYPOTHETICAL_ALLOWED_TERMS = [
    "called off",
    "delays",
    "delayed",
    "pauses",
    "postponed",
]

QUESTION_STARTERS = {
    "can",
    "could",
    "did",
    "does",
    "do",
    "how",
    "is",
    "should",
    "what",
    "when",
    "where",
    "why",
    "will",
    "would",
}

CONCRETE_EVENT_TERMS = [
    "advances",
    "announces",
    "announced",
    "arrives",
    "attack",
    "attacks",
    "blames",
    "called off",
    "ceasefire",
    "conducts",
    "delays",
    "delayed",
    "detains",
    "drone",
    "earthquake",
    "election",
    "expel",
    "fire",
    "flood",
    "imposes",
    "jails",
    "kill",
    "killed",
    "kills",
    "launches",
    "meeting",
    "meet",
    "meets",
    "missile",
    "orders",
    "passes",
    "pauses",
    "postponed",
    "reaches deal",
    "reports",
    "resolution",
    "rises",
    "rules",
    "sanction",
    "sentences",
    "signs deal",
    "strike",
    "strikes",
    "surge",
    "surges",
    "summit",
    "tariff",
    "visit",
    "visits",
    "vote",
    "wins",
]

HARD_EVENT_TERMS = [
    "attack",
    "attacks",
    "ceasefire",
    "conducts",
    "death toll",
    "drone",
    "earthquake",
    "flood",
    "imposes",
    "kill",
    "killed",
    "kills",
    "launches",
    "missile",
    "sanction",
    "strike",
    "strikes",
    "summit",
]

LOCATION_HINTS = [
    ("Taipei", "Taiwan", 25.0330, 121.5654, ["taipei", "taiwan"]),
    ("Beijing", "China", 39.9042, 116.4074, ["beijing", "beijing summit", "trump xi", "xi jinping", "xi", "china"]),
    ("Washington", "United States", 38.9072, -77.0369, ["white house", "washington", "united states", "us"]),
    ("Moscow", "Russia", 55.7558, 37.6173, ["moscow", "putin", "russia", "kremlin"]),
    ("Kyiv", "Ukraine", 50.4501, 30.5234, ["kyiv", "kiev", "ukraine"]),
    ("Gaza", "Palestinian territories", 31.5017, 34.4668, ["gaza", "hamas"]),
    ("Jerusalem", "Israel", 31.7683, 35.2137, ["jerusalem", "israel"]),
    ("Lebanon", "Lebanon", 33.8547, 35.8623, ["lebanon", "hezbollah", "tyre", "deir qanoun"]),
    ("Tehran", "Iran", 35.6892, 51.3890, ["tehran", "iran", "hormuz", "gulf states", "middle east crisis"]),
    ("Abu Dhabi", "United Arab Emirates", 24.4539, 54.3773, ["abu dhabi", "uae", "united arab emirates", "barakah"]),
    ("Doha", "Qatar", 25.2854, 51.5310, ["doha", "qatar"]),
    ("Riga", "Latvia", 56.9496, 24.1052, ["riga", "latvia"]),
    ("Havana", "Cuba", 23.1136, -82.3666, ["havana", "cuba"]),
    ("Caracas", "Venezuela", 10.4806, -66.9036, ["caracas", "venezuela", "maduro"]),
    ("London", "United Kingdom", 51.5072, -0.1276, ["london", "britain", "uk", "united kingdom"]),
    ("Brussels", "Belgium", 50.8503, 4.3517, ["brussels", "eu", "european union", "nato"]),
    ("New York", "United States", 40.7128, -74.0060, ["new york", "united nations", "wall street"]),
    ("Tokyo", "Japan", 35.6762, 139.6503, ["tokyo", "japan"]),
    ("Seoul", "South Korea", 37.5665, 126.9780, ["seoul", "south korea", "north korea"]),
    ("New Delhi", "India", 28.6139, 77.2090, ["new delhi", "india"]),
    ("Islamabad", "Pakistan", 33.6844, 73.0479, ["islamabad", "pakistan"]),
    ("Bangkok", "Thailand", 13.7563, 100.5018, ["bangkok", "thailand"]),
    ("Jakarta", "Indonesia", -6.2088, 106.8456, ["jakarta", "indonesia"]),
    ("Sydney", "Australia", -33.8688, 151.2093, ["sydney", "australia"]),
    ("Sao Paulo", "Brazil", -23.5558, -46.6396, ["sao paulo", "brazil"]),
]

LOCATION_KEY_WEIGHTS = {
    "beijing": 14,
    "beijing summit": 16,
    "trump xi": 18,
    "xi jinping": 16,
    "china": 8,
    "xi": 4,
    "tehran": 16,
    "iran": 14,
    "hormuz": 14,
    "gulf states": 12,
    "middle east crisis": 12,
    "gaza": 16,
    "hamas": 12,
    "jerusalem": 14,
    "israel": 10,
    "lebanon": 16,
    "hezbollah": 12,
    "tyre": 12,
    "deir qanoun": 14,
    "abu dhabi": 16,
    "uae": 14,
    "united arab emirates": 16,
    "barakah": 16,
    "latvia": 14,
    "riga": 14,
    "cuba": 14,
    "havana": 14,
    "venezuela": 16,
    "caracas": 16,
    "maduro": 14,
    "washington": 14,
    "white house": 14,
    "united states": 8,
    "us": 3,
}

FALLBACK_EVENTS = [
    {
        "id": "fallback-trump-xi-beijing",
        "title": "Trump-Xi Beijing summit puts Taiwan, trade and Iran in focus",
        "statement": "Trump-Xi Beijing summit puts Taiwan, trade and Iran in focus",
        "summary": "Recent reporting described the Beijing summit as high-stakes diplomacy with modest deliverables and pointed warnings over Taiwan.",
        "source": "Fallback brief",
        "url": "https://apnews.com/article/75d703648da64e2caaace39e6415dc35",
        "published": "2026-05-16T00:00:00Z",
        "location": "Beijing",
        "country": "China",
        "lat": 39.9042,
        "lon": 116.4074,
        "category": "diplomacy",
        "severity": 5,
    },
    {
        "id": "fallback-putin-china",
        "title": "Putin visit to China follows Trump's Beijing trip",
        "statement": "Putin visit to China follows Trump's Beijing trip",
        "summary": "Russia-China diplomacy remains under watch as Moscow leans heavily on Beijing during continuing pressure over Ukraine.",
        "source": "Fallback brief",
        "url": "https://apnews.com/article/75d703648da64e2caaace39e6415dc35",
        "published": "2026-05-16T00:00:00Z",
        "location": "Beijing",
        "country": "China",
        "lat": 39.9042,
        "lon": 116.4074,
        "category": "diplomacy",
        "severity": 4,
    },
]


class ConsoleHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/wallpapers"):
            wallpapers = list_wallpapers()
            self.send_json({
                "wallpapers": wallpapers,
                "order": [item["path"] for item in wallpapers],
                "directory": str(WALLPAPER_DIR),
                "original": original_wallpaper_state(),
            })
            return
        if parsed.path == "/api/music":
            self.send_json({
                "tracks": list_music(),
                "directory": str(MUSIC_DIR),
                "libraries": list_music_libraries(),
                "cookies": youtube_cookie_state(),
                "state": read_music_state(),
            })
            return
        if parsed.path == "/api/music/libraries":
            self.send_json({
                "libraries": list_music_libraries(),
                "directory": str(MUSIC_LIBRARY_DIR),
            })
            return
        if parsed.path == "/api/material-import/candidates":
            self.send_json({
                "source": str(MATERIAL_SOURCE_DIR),
                "target": str(BUILDER_TEXTURE_DIR),
                "candidates": list_material_candidates(),
            })
            return
        if parsed.path == "/api/randomrealm/blender/projects":
            query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            self.send_json({
                "projects": list_blender_projects(query=query),
                "query": query,
                "roots": [str(path) for path in BLENDER_PROJECT_ROOTS if path.exists()],
                "blender": str(find_blender_executable() or ""),
            })
            return
        if parsed.path == "/api/randomrealm/blender/live-selection":
            query = urllib.parse.parse_qs(parsed.query)
            self.send_json(read_blender_live_selection(query.get("project", [""])[0]))
            return
        if parsed.path == "/api/randomrealm/blender/texture-preview" or parsed.path.startswith("/api/randomrealm/blender/texture-file/"):
            query = urllib.parse.parse_qs(parsed.query)
            try:
                texture_path = blender_texture_preview_path(query.get("path", [""])[0])
                content_type = mimetypes.guess_type(str(texture_path))[0] or "application/octet-stream"
                self.send_file_response(texture_path, content_type, filename=texture_path.name)
            except ValueError as error:
                self.send_json({"error": str(error)}, status=400)
            return
        if parsed.path == "/api/console/state":
            self.send_json({"state": read_console_state()})
            return
        if parsed.path == "/api/console/config":
            self.send_json(console_edition_payload())
            return
        if parsed.path == "/api/workspace/github-downloads":
            self.send_json(github_downloads_state())
            return
        if parsed.path == "/api/steamwork/assets":
            self.send_json(steamwork_assets_state())
            return
        if parsed.path == "/api/steamwork/asset-preview":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                asset_path = steamwork_asset_preview_path(query.get("path", [""])[0])
                content_type = mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
                self.send_file_response(asset_path, content_type, filename=asset_path.name)
            except ValueError as error:
                self.send_json({"error": str(error)}, status=400)
            return
        if parsed.path == "/api/steamwork/asset-thumb":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                thumb_path = steamwork_asset_thumbnail_path(query.get("path", [""])[0])
                self.send_file_response(thumb_path, "image/jpeg", filename=thumb_path.name)
            except ValueError as error:
                self.send_json({"error": str(error)}, status=400)
            return
        if parsed.path == "/api/randomrealm/unity/bridge-status":
            self.send_json(randomrealm_unity_bridge_status())
            return
        if self.path.startswith("/api/events"):
            self.send_json({"events": load_events(), "updated": datetime.now(timezone.utc).isoformat()})
            return
        if self.path.startswith("/api/world"):
            geojson = load_world_geojson()
            if geojson:
                self.send_json(geojson)
            else:
                self.send_json({"error": "world map unavailable"}, status=503)
            return
        if parsed.path.startswith("/music/"):
            self.send_music_file_response(parsed.path[len("/music/"):])
            return
        if parsed.path in CONSOLE_PAGE_PATHS:
            redirect_path = console_lite_redirect_path(parsed)
            if redirect_path:
                self.send_redirect(redirect_path)
                return
            self.send_file_response(APP_DIR / "index.html", "text/html; charset=utf-8")
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/wallpapers/upload":
                self.send_json(upload_wallpapers(self.read_multipart_files()))
                return
            if parsed.path == "/api/music/upload":
                self.send_json(upload_music(self.read_multipart_files(MAX_MUSIC_UPLOAD_BYTES)))
                return
            if parsed.path == "/api/music/cookies":
                self.send_json(upload_youtube_cookies(self.read_multipart_files(MAX_COOKIE_UPLOAD_BYTES)))
                return
            if parsed.path == "/api/workzones/render-textures/upload":
                self.send_json(import_render_textures_upload(self.read_multipart_files(MAX_WORKZONE_UPLOAD_BYTES)))
                return
            if parsed.path == "/api/randomrealm/blender/upload-texture":
                self.send_json(upload_blender_replacement_texture(self.read_multipart_files(MAX_WORKZONE_UPLOAD_BYTES)))
                return
            if parsed.path == "/api/steamwork/gamecontent/upload":
                self.send_json(import_steamwork_files("gameContent", self.read_multipart_files(MAX_STEAMWORK_UPLOAD_BYTES)))
                return
            if parsed.path == "/api/steamwork/publish-tool/upload":
                self.send_json(import_steamwork_files("publishTool", self.read_multipart_files(MAX_STEAMWORK_UPLOAD_BYTES)))
                return
            if parsed.path.startswith("/api/steamwork/assets/stage/"):
                requirement_id = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
                self.send_json(stage_steamwork_asset_files(requirement_id, self.read_multipart_files(MAX_STEAMWORK_UPLOAD_BYTES)))
                return

            payload = self.read_json_body()
            if parsed.path == "/api/wallpapers/apply":
                self.send_json(apply_wallpaper(payload.get("path", "")))
                return
            if parsed.path == "/api/wallpapers/delete":
                self.send_json(delete_wallpaper(payload.get("path", "")))
                return
            if parsed.path == "/api/wallpapers/order":
                self.send_json(write_wallpaper_order(payload))
                return
            if parsed.path == "/api/wallpapers/capture-original":
                self.send_json(capture_original_wallpaper(force=True))
                return
            if parsed.path == "/api/wallpapers/restore-original":
                self.send_json(restore_original_wallpaper())
                return
            if parsed.path == "/api/wallpapers/open-folder":
                self.send_json(open_wallpaper_folder())
                return
            if parsed.path == "/api/music/delete":
                self.send_json(delete_music(payload.get("path", "")))
                return
            if parsed.path == "/api/music/promote":
                self.send_json(promote_library_music(payload.get("path", "")))
                return
            if parsed.path == "/api/music/state":
                self.send_json(write_music_state(payload))
                return
            if parsed.path == "/api/music/import-url":
                self.send_json(import_music_url(payload.get("url", ""), bool(payload.get("useBrowserCookies"))))
                return
            if parsed.path == "/api/music/library/import":
                self.send_json(import_music_library(payload.get("url", ""), payload.get("name", "")))
                return
            if parsed.path == "/api/workspace/open-downloads":
                self.send_json(open_downloads_folder())
                return
            if parsed.path == "/api/workspace/open-github-downloads":
                self.send_json(open_github_downloads())
                return
            if parsed.path == "/api/steamwork/open-asset":
                self.send_json(open_steamwork_asset(payload.get("path", "")))
                return
            if parsed.path == "/api/randomrealm/open-resource":
                self.send_json(open_randomrealm_resource(payload.get("id", "")))
                return
            if parsed.path == "/api/randomrealm/blender/objects":
                self.send_json(load_blender_project_objects(payload.get("project", "")))
                return
            if parsed.path == "/api/randomrealm/blender/native-drag":
                self.send_json(start_native_file_drag(payload.get("path", "")))
                return
            if parsed.path == "/api/randomrealm/blender/open-texture":
                self.send_json(open_blender_texture_file(payload.get("path", "")))
                return
            if parsed.path == "/api/randomrealm/blender/stage-blank-texture":
                self.send_json(stage_blank_blender_texture(payload))
                return
            if parsed.path == "/api/randomrealm/blender/package-texture":
                self.send_json(package_blender_texture(payload))
                return
            if parsed.path == "/api/randomrealm/blender/package-status":
                self.send_json(blender_texture_package_status(payload))
                return
            if parsed.path == "/api/randomrealm/blender/package-remove-texture":
                self.send_json(package_blender_texture_removal(payload))
                return
            if parsed.path in BLENDER_MUTATION_API_PATHS:
                if not ENABLE_BLENDER_MUTATION_API:
                    self.send_json({
                        "error": "Blender mutation API is disabled. Use the Blender plugin for node/material changes.",
                    }, status=403)
                    return
                if parsed.path == "/api/randomrealm/blender/create-empty-texture":
                    self.send_json(create_empty_blender_texture(payload))
                    return
                if parsed.path == "/api/randomrealm/blender/add-texture":
                    self.send_json(add_blender_object_texture(payload))
                    return
                if parsed.path == "/api/randomrealm/blender/remove-textures":
                    self.send_json(remove_blender_object_textures(payload))
                    return
                if parsed.path == "/api/randomrealm/blender/remove-texture":
                    self.send_json(remove_blender_object_texture(payload))
                    return
                if parsed.path == "/api/randomrealm/blender/replace-texture":
                    self.send_json(replace_blender_object_texture(payload))
                    return
            if parsed.path == "/api/randomrealm/blender/export-to-unity":
                self.send_json(export_blender_to_unity(payload))
                return
            if parsed.path == "/api/material-import/import":
                self.send_json(import_material_candidate(payload.get("path", "")))
                return
            if parsed.path == "/api/console/state":
                self.send_json(write_console_state(payload))
                return
            if parsed.path == "/api/hotkey/start":
                self.send_json(start_hotkey_listener())
                return
            if parsed.path == "/api/startup/install":
                self.send_json(install_startup_listener())
                return
        except ValueError as error:
            self.send_json({"error": str(error)}, status=400)
            return
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)
            return

        self.send_json({"error": "not found"}, status=404)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        return

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_redirect(self, location, status=302):
        self.send_response(status)
        self.send_header("Location", location)
        self.end_headers()

    def send_file_response(self, path, content_type, filename=None):
        try:
            body = path.read_bytes()
        except OSError:
            self.send_json({"error": "not found"}, status=404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        if filename:
            safe_filename = str(filename).replace('"', "")
            self.send_header("Content-Disposition", f'inline; filename="{safe_filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_ranged_file_response(self, path, content_type):
        try:
            file_size = path.stat().st_size
        except OSError:
            self.send_json({"error": "not found"}, status=404)
            return

        range_header = self.headers.get("Range", "")
        start = 0
        end = file_size - 1
        status = 200

        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
            if not match:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return

            raw_start, raw_end = match.groups()
            if raw_start:
                start = int(raw_start)
                if raw_end:
                    end = int(raw_end)
            elif raw_end:
                suffix_length = int(raw_end)
                start = max(file_size - suffix_length, 0)
            else:
                start = 0

            if start >= file_size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return

            end = min(end, file_size - 1)
            status = 206

        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        try:
            with path.open("rb") as file:
                file.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = file.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (OSError, BrokenPipeError, ConnectionResetError):
            return

    def send_music_file_response(self, relative_path):
        try:
            path = music_path_from_relative(urllib.parse.unquote(relative_path))
        except ValueError:
            self.send_json({"error": "not found"}, status=404)
            return
        self.send_ranged_file_response(path, self.guess_type(str(path)) or "application/octet-stream")

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError as error:
            raise ValueError("invalid json body") from error

    def read_multipart_files(self, max_bytes=MAX_WALLPAPER_UPLOAD_BYTES):
        content_type = self.headers.get("Content-Type", "")
        boundary_match = re.search(r'boundary="?([^";]+)"?', content_type)
        if not boundary_match:
            raise ValueError("missing multipart boundary")

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            raise ValueError("no files were uploaded")
        if length > max_bytes:
            raise ValueError("uploaded files are too large")

        body = self.rfile.read(length)
        boundary = b"--" + boundary_match.group(1).encode("utf-8")
        files = []

        for raw_part in body.split(boundary):
            part = raw_part
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"--"):
                part = part[:-2]
            if part.endswith(b"\r\n"):
                part = part[:-2]
            if not part or part == b"--":
                continue

            header_blob, separator, data = part.partition(b"\r\n\r\n")
            if not separator:
                continue

            headers_text = header_blob.decode("utf-8", errors="replace")
            disposition = ""
            for line in headers_text.splitlines():
                if line.lower().startswith("content-disposition:"):
                    disposition = line
                    break

            filename_match = re.search(r'filename="([^"]*)"', disposition)
            if not filename_match:
                continue

            filename = filename_match.group(1).strip()
            if filename and data:
                files.append({"filename": filename, "data": data})

        if not files:
            raise ValueError("no files were uploaded")
        return files


def ensure_wallpaper_dir():
    WALLPAPER_DIR.mkdir(exist_ok=True)


def is_path_inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def ensure_child_path(root, child, label="target"):
    root_path = Path(root).resolve()
    child_path = Path(child).resolve()
    if not is_path_inside(child_path, root_path):
        raise ValueError(f"{label} path is outside the expected folder")
    return child_path


def wallpaper_path_from_relative(relative_path):
    ensure_wallpaper_dir()
    clean = str(relative_path or "").replace("\\", "/").lstrip("/")
    if not clean:
        raise ValueError("wallpaper path is required")
    candidate = (WALLPAPER_DIR / clean).resolve()
    if not is_path_inside(candidate, WALLPAPER_DIR):
        raise ValueError("wallpaper path is outside the wallpaper folder")
    if not candidate.exists() or candidate.suffix.lower() not in WALLPAPER_EXTENSIONS:
        raise ValueError("wallpaper file was not found")
    return candidate


def safe_wallpaper_filename(filename):
    raw_name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(raw_name).suffix.lower()
    if suffix not in WALLPAPER_EXTENSIONS:
        raise ValueError("only jpg, png, bmp, and webp files can be added")

    stem = Path(raw_name).stem.strip()
    stem = re.sub(r"[^\w .()\-]+", "-", stem, flags=re.UNICODE).strip(" .-_")
    if not stem:
        stem = "wallpaper"
    return f"{stem}{suffix}"


def unique_wallpaper_path(filename):
    ensure_wallpaper_dir()
    safe_name = safe_wallpaper_filename(filename)
    base = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    candidate = (WALLPAPER_DIR / safe_name).resolve()
    index = 2

    while candidate.exists():
        candidate = (WALLPAPER_DIR / f"{base}-{index}{suffix}").resolve()
        index += 1

    if not is_path_inside(candidate, WALLPAPER_DIR):
        raise ValueError("wallpaper path is outside the wallpaper folder")
    return candidate


def get_current_wallpaper():
    if sys.platform != "win32":
        return ""

    import ctypes

    SPI_GETDESKWALLPAPER = 0x0073
    buffer = ctypes.create_unicode_buffer(32768)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETDESKWALLPAPER,
        len(buffer),
        buffer,
        0,
    )
    if not ok:
        return ""
    return buffer.value


def read_original_wallpaper_record():
    try:
        return json.loads(ORIGINAL_WALLPAPER_RECORD.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_original_wallpaper_record(path, source="auto"):
    ORIGINAL_WALLPAPER_RECORD.parent.mkdir(exist_ok=True)
    backup_path = ""
    source_path = Path(path)
    if source_path.exists():
        backup_path = str(ORIGINAL_WALLPAPER_RECORD.with_name(f"original_wallpaper{source_path.suffix.lower()}"))
        shutil.copy2(source_path, backup_path)
    payload = {
        "path": str(path),
        "backupPath": backup_path,
        "source": source,
        "savedAt": datetime.now(timezone.utc).isoformat(),
    }
    ORIGINAL_WALLPAPER_RECORD.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def original_wallpaper_state():
    record = read_original_wallpaper_record()
    path = record.get("path") or ""
    backup_path = record.get("backupPath") or ""
    available = bool((backup_path and Path(backup_path).exists()) or (path and Path(path).exists()))
    return {
        "saved": available,
        "available": available,
        "path": path if available else "",
        "backupPath": backup_path if available else "",
        "savedAt": record.get("savedAt", "") if available else "",
    }


def capture_original_wallpaper(force=False):
    existing = original_wallpaper_state()
    if existing["saved"] and not force:
        return {"ok": True, "original": existing, "changed": False}

    current = get_current_wallpaper()
    if not current:
        raise ValueError("current wallpaper path could not be read")
    record = write_original_wallpaper_record(current, source="manual" if force else "auto")
    return {"ok": True, "original": original_wallpaper_state(), "changed": True, "record": record}


def set_windows_wallpaper(path):
    if sys.platform != "win32":
        raise ValueError("wallpaper switching is only available on Windows")

    import ctypes

    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 1
    SPIF_SENDCHANGE = 2
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER,
        0,
        str(path),
        SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
    )
    if not ok:
        raise RuntimeError("Windows rejected the wallpaper change")


def read_wallpaper_order():
    try:
        raw = json.loads(WALLPAPER_ORDER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if isinstance(raw, dict):
        return sanitize_string_list(raw.get("order"))
    return sanitize_string_list(raw)


def wallpaper_record_from_path(path):
    stat = path.stat()
    rel = path.relative_to(WALLPAPER_DIR).as_posix()
    return {
        "name": path.stem,
        "path": rel,
        "url": "/wallpapers/" + urllib.parse.quote(rel),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def scan_wallpapers():
    ensure_wallpaper_dir()
    items = []
    for path in WALLPAPER_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in WALLPAPER_EXTENSIONS:
            continue
        try:
            items.append(wallpaper_record_from_path(path))
        except OSError:
            continue
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items


def list_wallpapers():
    items = scan_wallpapers()
    order = read_wallpaper_order()
    if not order:
        return items
    order_index = {path: index for index, path in enumerate(order)}
    ordered = sorted((item for item in items if item["path"] in order_index), key=lambda item: order_index[item["path"]])
    ordered_paths = {item["path"] for item in ordered}
    return ordered + [item for item in items if item["path"] not in ordered_paths]


def write_wallpaper_order(payload):
    requested = sanitize_string_list(payload.get("order") if isinstance(payload, dict) else payload)
    current = scan_wallpapers()
    current_paths = {item["path"] for item in current}
    next_order = [path for path in requested if path in current_paths]
    seen = set(next_order)
    for item in current:
        if item["path"] not in seen:
            next_order.append(item["path"])
            seen.add(item["path"])

    WALLPAPER_ORDER_FILE.parent.mkdir(parents=True, exist_ok=True)
    WALLPAPER_ORDER_FILE.write_text(json.dumps({"order": next_order}, ensure_ascii=False, indent=2), encoding="utf-8")
    wallpapers = list_wallpapers()
    return {"ok": True, "order": [item["path"] for item in wallpapers], "wallpapers": wallpapers}


def apply_wallpaper(relative_path):
    path = wallpaper_path_from_relative(relative_path)
    capture_original_wallpaper(force=False)
    set_windows_wallpaper(path)
    return {"ok": True, "path": str(path), "original": original_wallpaper_state()}


def upload_wallpapers(files):
    saved = []
    for item in files:
        target = unique_wallpaper_path(item.get("filename", ""))
        data = item.get("data", b"")
        if not data:
            continue
        target.write_bytes(data)
        stat = target.stat()
        rel = target.relative_to(WALLPAPER_DIR).as_posix()
        saved.append({
            "name": target.stem,
            "path": rel,
            "url": "/wallpapers/" + urllib.parse.quote(rel),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    if not saved:
        raise ValueError("no image files were uploaded")

    return {"ok": True, "files": saved, "wallpapers": list_wallpapers()}


def delete_wallpaper(relative_path):
    path = wallpaper_path_from_relative(relative_path)
    path.unlink()
    return {"ok": True, "deleted": str(path), "wallpapers": list_wallpapers()}


def restore_original_wallpaper():
    original = original_wallpaper_state()
    if not original["saved"]:
        raise ValueError("original wallpaper has not been saved yet")
    if not original["available"]:
        raise ValueError("original wallpaper file is no longer available")
    restore_path = original["backupPath"] if original["backupPath"] and Path(original["backupPath"]).exists() else original["path"]
    set_windows_wallpaper(restore_path)
    return {"ok": True, "path": restore_path, "original": original}


def open_wallpaper_folder():
    ensure_wallpaper_dir()
    if sys.platform == "win32":
        os.startfile(str(WALLPAPER_DIR))
    else:
        webbrowser.open(WALLPAPER_DIR.as_uri())
    return {"ok": True, "path": str(WALLPAPER_DIR)}


def open_downloads_folder():
    MATERIAL_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(MATERIAL_SOURCE_DIR))
    else:
        webbrowser.open(MATERIAL_SOURCE_DIR.resolve().as_uri())
    return {"ok": True, "path": str(MATERIAL_SOURCE_DIR)}


def open_folder_resource(path):
    target = Path(path).resolve()
    if not target.exists() or not target.is_dir():
        raise ValueError(f"folder was not found: {target}")
    if sys.platform == "win32":
        os.startfile(str(target))
    else:
        webbrowser.open(target.as_uri())
    return {"ok": True, "path": str(target)}


def open_file_resource(path):
    target = Path(path).resolve()
    if not target.exists() or not target.is_file():
        raise ValueError(f"file was not found: {target}")
    if sys.platform == "win32":
        os.startfile(str(target))
    else:
        webbrowser.open(target.as_uri())
    return {"ok": True, "path": str(target)}


def open_url_resource(url):
    clean_url = str(url or "").strip()
    if not clean_url:
        raise ValueError("url is required")
    webbrowser.open(clean_url)
    return {"ok": True, "url": clean_url}


def github_releases_url_from_remote(remote_url):
    raw = str(remote_url or "").strip()
    if not raw:
        return ""
    raw = raw.removesuffix(".git").rstrip("/")
    match = re.search(r"github\.com[:/]([^/\s:]+)/([^/\s]+)$", raw, flags=re.IGNORECASE)
    if not match:
        return ""
    owner, repo = match.group(1), match.group(2)
    if not owner or not repo:
        return ""
    return f"https://github.com/{owner}/{repo}/releases"


def world_console_git_remote():
    if not WORLD_CONSOLE_DIR.exists():
        return ""
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={WORLD_CONSOLE_DIR.as_posix()}",
                "remote",
                "get-url",
                "origin",
            ],
            cwd=str(WORLD_CONSOLE_DIR),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=4,
            **hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def github_downloads_state():
    if WORLD_CONSOLE_RELEASES_URL:
        return {
            "ok": True,
            "configured": True,
            "source": "env",
            "url": WORLD_CONSOLE_RELEASES_URL,
            "project": str(WORLD_CONSOLE_DIR),
        }

    remote = world_console_git_remote()
    releases_url = github_releases_url_from_remote(remote)
    return {
        "ok": True,
        "configured": bool(releases_url),
        "source": "git-remote" if releases_url else "",
        "remote": remote,
        "url": releases_url,
        "project": str(WORLD_CONSOLE_DIR),
    }


def open_github_downloads():
    state = github_downloads_state()
    if not state.get("configured") or not state.get("url"):
        raise ValueError("Codex World GitHub Releases URL is not configured yet")
    open_url_resource(state["url"])
    return state


def open_randomrealm_resource(resource_id):
    resources = {
        "steamworks": ("url", STEAMWORKS_URL),
        "publishFolder": ("folder", RANDOMREALM_PUBLISH_DIR),
        "gameContentFolder": ("folder", STEAMWORK_GAMECONTENT_DIR),
        "publishToolFolder": ("file", STEAMWORK_PUBLISH_TOOL_EXE),
        "projectFolder": ("folder", RANDOMREALM_PROJECT_DIR),
        "promoFolder": ("folder", RANDOMREALM_PROMO_DIR),
        "steamworkAssetFolder": ("folder", STEAMWORK_ASSET_DIR),
        "steamworkStoreAssetFolder": ("folder", STEAMWORK_STORE_ASSET_DIR),
        "steamworkScreenshotFolder": ("folder", STEAMWORK_SCREENSHOT_DIR),
        "steamworkVideoFolder": ("folder", STEAMWORK_VIDEO_DIR),
    }
    resource = resources.get(str(resource_id or ""))
    if not resource:
        raise ValueError("unknown RandomRealm resource")
    kind, target = resource
    if kind == "url":
        return open_url_resource(target)
    if kind == "file":
        return open_file_resource(target)
    return open_folder_resource(target)


def find_blender_executable():
    env_path = os.environ.get("CODEX_CONTROL_BLENDER_EXE", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    from_path = shutil.which("blender")
    if from_path:
        return Path(from_path)

    candidates = []
    direct_candidates = [
        Path(r"D:\Blender5.1\blender.exe"),
        Path(r"D:\Steam\steamapps\common\Blender\blender.exe"),
    ]
    candidates.extend(path for path in direct_candidates if path.exists())

    if sys.platform == "win32":
        try:
            import winreg
            uninstall_roots = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            for hive, key_path in uninstall_roots:
                try:
                    with winreg.OpenKey(hive, key_path) as root_key:
                        for index in range(winreg.QueryInfoKey(root_key)[0]):
                            try:
                                subkey_name = winreg.EnumKey(root_key, index)
                                with winreg.OpenKey(root_key, subkey_name) as subkey:
                                    display_name = str(winreg.QueryValueEx(subkey, "DisplayName")[0])
                                    if "blender" not in display_name.casefold():
                                        continue
                                    install_location = ""
                                    try:
                                        install_location = str(winreg.QueryValueEx(subkey, "InstallLocation")[0])
                                    except OSError:
                                        pass
                                    if install_location:
                                        candidates.append(Path(install_location) / "blender.exe")
                            except OSError:
                                continue
                except OSError:
                    continue
        except OSError:
            pass

    for root in [
        Path(r"C:\Program Files\Blender Foundation"),
        Path(r"C:\Program Files (x86)\Blender Foundation"),
        Path(r"D:\Program Files\Blender Foundation"),
    ]:
        if not root.exists():
            continue
        candidates.extend(root.glob("Blender*\\blender.exe"))

    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            return resolved
        except OSError:
            continue
    return None


def find_photoshop_executable():
    env_path = os.environ.get("CODEX_CONTROL_PHOTOSHOP_EXE", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    from_path = shutil.which("Photoshop")
    if from_path:
        return Path(from_path)

    candidates = []
    for root in [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(r"D:\Program Files"),
    ]:
        adobe_root = root / "Adobe"
        if not adobe_root.exists():
            continue
        candidates.extend(adobe_root.glob("Adobe Photoshop*\\Photoshop.exe"))
        candidates.extend(adobe_root.glob("Photoshop*\\Photoshop.exe"))

    existing = []
    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            existing.append(resolved)
        except OSError:
            continue
    existing.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return existing[0] if existing else None


def find_csharp_compiler():
    env_path = os.environ.get("CODEX_CONTROL_CSC_EXE", "").strip()
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    from_path = shutil.which("csc")
    if from_path:
        return Path(from_path)

    candidates = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ensure_native_file_drag_helper():
    if not NATIVE_FILE_DRAG_SOURCE.exists():
        raise ValueError("native file drag helper source was not found")
    try:
        if NATIVE_FILE_DRAG_EXE.exists() and NATIVE_FILE_DRAG_EXE.stat().st_mtime >= NATIVE_FILE_DRAG_SOURCE.stat().st_mtime:
            return NATIVE_FILE_DRAG_EXE
    except OSError:
        pass

    compiler = find_csharp_compiler()
    if not compiler:
        raise ValueError("C# compiler was not found for native file dragging")

    NATIVE_FILE_DRAG_EXE.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(compiler),
        "/nologo",
        "/target:exe",
        "/nowin32manifest",
        "/optimize+",
        "/r:System.Windows.Forms.dll",
        "/r:System.Drawing.dll",
        f"/out:{NATIVE_FILE_DRAG_EXE}",
        str(NATIVE_FILE_DRAG_SOURCE),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        **hidden_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "native file drag helper could not be built").strip()
        raise ValueError(details)
    return NATIVE_FILE_DRAG_EXE


def is_blender_project_path(path):
    target = Path(path).resolve()
    if not target.exists() or not target.is_file() or target.suffix.lower() not in BLENDER_PROJECT_EXTENSIONS:
        return False
    allowed_roots = [root.resolve() for root in BLENDER_PROJECT_ROOTS if root.exists()]
    if not allowed_roots:
        return True
    return any(is_path_inside(target, root) for root in allowed_roots)


def blender_project_path(value):
    target = Path(str(value or "")).expanduser().resolve()
    if not is_blender_project_path(target):
        raise ValueError("Blender project was not found or is outside the configured project roots")
    return target


def same_filesystem_path(left, right):
    if not left or not right:
        return False
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except OSError:
        return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def read_blender_live_selection(project=""):
    try:
        payload = json.loads(BLENDER_LIVE_SELECTION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "available": False,
            "reason": "bridge not running",
            "path": str(BLENDER_LIVE_SELECTION_FILE),
        }

    updated = float(payload.get("updatedTimestamp") or 0)
    age = max(0.0, time.time() - updated) if updated else None
    live_project = str(payload.get("project") or "")
    active_object = payload.get("activeObject") if isinstance(payload.get("activeObject"), dict) else {}
    selected_objects = payload.get("selectedObjects") if isinstance(payload.get("selectedObjects"), list) else []
    matching_project = same_filesystem_path(live_project, project) if project else bool(live_project)
    active_name = str(active_object.get("name") or "")

    return {
        "available": bool(active_name and (age is None or age <= BLENDER_LIVE_SELECTION_MAX_AGE_SECONDS)),
        "reason": "" if active_name else "no active object",
        "stale": bool(age is not None and age > BLENDER_LIVE_SELECTION_MAX_AGE_SECONDS),
        "ageSeconds": round(age, 2) if age is not None else None,
        "matchingProject": matching_project,
        "project": live_project,
        "requestedProject": str(project or ""),
        "activeObject": active_object,
        "selectedObjects": selected_objects,
        "path": str(BLENDER_LIVE_SELECTION_FILE),
        "updated": payload.get("updated", ""),
    }


def normalize_search_text(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE).strip()


def blender_project_root_rank(path):
    target = Path(path).resolve()
    ranks = []
    for index, root in enumerate(BLENDER_PROJECT_ROOTS):
        if not root.exists():
            continue
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if is_path_inside(target, resolved):
            ranks.append(index)
    return min(ranks) if ranks else len(BLENDER_PROJECT_ROOTS)


def blender_project_query_score(project, query):
    query = normalize_search_text(query)
    if not query:
        return 0

    name = normalize_search_text(project.get("name", ""))
    file = normalize_search_text(project.get("file", ""))
    path = normalize_search_text(project.get("path", ""))
    haystack = f"{name} {file} {path}"
    tokens = [token for token in query.split() if token]
    if not tokens:
        return 0
    if name == query or file == query:
        return 1000
    if name.startswith(query) or file.startswith(query):
        return 860
    if query in name or query in file:
        return 720
    if all(token in haystack for token in tokens):
        return 560 + sum(30 for token in tokens if name.startswith(token) or file.startswith(token))
    if query in path:
        return 420
    return -1


def list_blender_projects(limit=None, max_depth=8, query=""):
    query = str(query or "").strip()
    limit = 5 if not query else 40 if limit is None else limit
    seen = set()
    projects = []
    existing_roots = [root.expanduser() for root in BLENDER_PROJECT_ROOTS if root.expanduser().exists() and root.expanduser().is_dir()]
    primary_root = next((root for root in existing_roots if root.resolve() == Path(r"D:\Blender\Projects").resolve()), None)
    scan_roots = [primary_root] if primary_root else existing_roots

    def add_project(path):
        try:
            target = Path(path).resolve()
            if target in seen or not is_blender_project_path(target):
                return
            seen.add(target)
            stat = target.stat()
            projects.append({
                "name": target.stem,
                "file": target.name,
                "path": str(target),
                "directory": str(target.parent),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "modifiedTimestamp": stat.st_mtime,
                "rootRank": blender_project_root_rank(target),
                "size": stat.st_size,
            })
        except OSError:
            return

    for path in BLENDER_PROJECT_FILES:
        add_project(path)

    for root in scan_roots:
        root_depth = len(root.resolve().parts)
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            if len(current_path.resolve().parts) - root_depth >= max_depth:
                dirs[:] = []
            dirs[:] = [
                name for name in dirs
                if name.lower() not in {"node_modules", ".git", "__pycache__", "library", "temp", "obj", "packages"}
            ]
            for name in files:
                if Path(name).suffix.lower() in BLENDER_PROJECT_EXTENSIONS:
                    add_project(current_path / name)

    if query:
        scored = []
        for project in projects:
            score = blender_project_query_score(project, query)
            if score >= 0:
                scored.append((score, project))
        scored.sort(key=lambda item: (item[0], -item[1]["rootRank"], item[1]["modifiedTimestamp"]), reverse=True)
        projects = [project for _, project in scored]
    else:
        projects.sort(key=lambda item: (-item["rootRank"], item["modifiedTimestamp"]), reverse=True)

    for project in projects:
        project.pop("modifiedTimestamp", None)
        project.pop("rootRank", None)
    return projects[:limit]


def blender_json_from_stdout(stdout):
    match = re.search(r"__CODEX_JSON_START__(.*?)__CODEX_JSON_END__", stdout, re.S)
    if not match:
        tail = "\n".join(stdout.splitlines()[-16:]).strip()
        if tail:
            raise ValueError(f"Blender did not return readable project data: {tail}")
        raise ValueError("Blender did not return readable project data")
    return json.loads(match.group(1))


def run_blender_json(project_path, script, timeout=45):
    blender = find_blender_executable()
    if not blender:
        raise ValueError("Blender executable was not found. Set CODEX_CONTROL_BLENDER_EXE if Blender is installed.")

    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)

    try:
        result = subprocess.run(
            [str(blender), "--background", str(project_path), "--python", str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **hidden_subprocess_kwargs(),
        )
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass

    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        tail = "\n".join(output.splitlines()[-12:])
        raise ValueError(f"Blender failed: {tail}")
    return blender_json_from_stdout(output)


def load_blender_project_objects(project):
    project_path = blender_project_path(project)
    script = r'''
import bpy, json, os, re

ROLE_SPECS = [
    {"kind": "base-color", "label": "Base Color", "inputs": ["Base Color"], "order": 0},
    {"kind": "roughness", "label": "Roughness", "inputs": ["Roughness"], "order": 10},
    {"kind": "normal", "label": "Normal", "inputs": ["Normal"], "order": 20},
    {"kind": "height", "label": "Height", "inputs": ["Height", "Displacement"], "order": 30},
    {"kind": "ambient-occlusion", "label": "Ambient Occlusion", "inputs": ["Ambient Occlusion"], "order": 40},
    {"kind": "metallic", "label": "Metallic", "inputs": ["Metallic", "Metalness"], "order": 50},
    {"kind": "alpha", "label": "Alpha", "inputs": ["Alpha"], "order": 60},
    {"kind": "emission", "label": "Emission", "inputs": ["Emission Color", "Emission"], "order": 70},
]
ROLE_LABELS = {item["kind"]: item["label"] for item in ROLE_SPECS}
ROLE_ORDERS = {item["kind"]: item["order"] for item in ROLE_SPECS}

def abs_path(value):
    try:
        path = bpy.path.abspath(value or "")
    except Exception:
        path = value or ""
    try:
        return os.path.abspath(path) if path else ""
    except Exception:
        return path or ""

def image_dimensions(image):
    try:
        width, height = list(getattr(image, "size", []))[:2]
        return int(width or 0), int(height or 0)
    except Exception:
        return 0, 0

def infer_kind(*values):
    text = " ".join(str(value or "") for value in values).lower()
    text = " " + re.sub(r"[^a-z0-9]+", " ", text) + " "
    if re.search(r"\b(normal|norm|nrm|nor)\b", text):
        return "normal"
    if re.search(r"\b(roughness|rough|rgh)\b", text):
        return "roughness"
    if re.search(r"\b(ambient occlusion|occlusion|ao)\b", text):
        return "ambient-occlusion"
    if re.search(r"\b(metallic|metalness|metal)\b", text):
        return "metallic"
    if re.search(r"\b(height|bump|displacement|disp)\b", text):
        return "height"
    if re.search(r"\b(alpha|opacity|mask)\b", text):
        return "alpha"
    if re.search(r"\b(emission|emissive|emit)\b", text):
        return "emission"
    if re.search(r"\b(base color|basecolor|albedo|diffuse|diff|color|col)\b", text):
        return "base-color"
    return ""

def texture_item(image, material_name="", node_name="", node_label="", kind="", role_label="", socket_name="", sort_order=900, material_index=0):
    path = abs_path(getattr(image, "filepath", "")) if image else ""
    width, height = image_dimensions(image) if image else (0, 0)
    inferred_kind = kind or infer_kind(node_name, node_label, getattr(image, "name", ""), path)
    label = role_label or ROLE_LABELS.get(inferred_kind, "Texture")
    file_name = os.path.basename(path) or getattr(image, "name", "") or node_label or node_name or "Image Slot"
    return {
        "name": getattr(image, "name", "") if image else node_label or node_name or "Image Slot",
        "path": path,
        "file": file_name,
        "exists": bool(path and os.path.exists(path)),
        "material": material_name,
        "node": node_name,
        "nodeLabel": node_label,
        "socket": socket_name,
        "kind": inferred_kind,
        "role": label,
        "roleLabel": label,
        "sortOrder": sort_order,
        "materialIndex": material_index,
        "width": width,
        "height": height,
    }

def linked_image_nodes_from_socket(socket, visited=None):
    nodes = []
    for link in getattr(socket, "links", []):
        nodes.extend(linked_image_nodes_from_node(getattr(link, "from_node", None), visited))
    return nodes

def linked_image_nodes_from_node(node, visited=None):
    if not node:
        return []
    if visited is None:
        visited = set()
    node_key = id(node)
    if node_key in visited:
        return []
    visited.add(node_key)
    if getattr(node, "type", "") == "TEX_IMAGE":
        return [node]

    inputs = list(getattr(node, "inputs", []))
    preferred = []
    node_type = getattr(node, "type", "")
    if node_type == "NORMAL_MAP":
        preferred = ["Color"]
    elif node_type == "BUMP":
        preferred = ["Height", "Normal"]

    ordered_inputs = []
    for name in preferred:
        socket = getattr(getattr(node, "inputs", None), "get", lambda _name: None)(name)
        if socket and socket not in ordered_inputs:
            ordered_inputs.append(socket)
    for socket in inputs:
        if socket not in ordered_inputs:
            ordered_inputs.append(socket)

    nodes = []
    for socket in ordered_inputs:
        if getattr(socket, "is_linked", False):
            nodes.extend(linked_image_nodes_from_socket(socket, visited))
    return nodes

def principled_nodes(mat):
    if not getattr(mat, "node_tree", None):
        return []
    nodes = [node for node in mat.node_tree.nodes if getattr(node, "type", "") == "BSDF_PRINCIPLED"]
    return sorted(nodes, key=lambda node: (getattr(node.location, "x", 0), -getattr(node.location, "y", 0), node.name))

def texture_nodes(mat):
    if not getattr(mat, "node_tree", None):
        return []
    return [node for node in mat.node_tree.nodes if getattr(node, "type", "") == "TEX_IMAGE"]

objects = []
for obj in bpy.data.objects:
    textures = []
    seen = set()
    materials = []
    for material_index, slot in enumerate(getattr(obj, "material_slots", [])):
        mat = getattr(slot, "material", None)
        if not mat:
            continue
        materials.append(mat.name)
        if getattr(mat, "use_nodes", False) and mat.node_tree:
            def add_texture_node(node, kind="", role_label="", socket_name="", sort_order=900):
                item = texture_item(
                    getattr(node, "image", None),
                    mat.name,
                    getattr(node, "name", ""),
                    getattr(node, "label", ""),
                    kind,
                    role_label,
                    socket_name,
                    material_index * 10000 + sort_order,
                    material_index,
                )
                key = (item["path"], item["material"], item["node"])
                if key not in seen:
                    seen.add(key)
                    textures.append(item)

            for bsdf_index, bsdf in enumerate(principled_nodes(mat)):
                for spec in ROLE_SPECS:
                    for input_name in spec["inputs"]:
                        socket = getattr(bsdf.inputs, "get", lambda _name: None)(input_name)
                        if not socket:
                            continue
                        for node_index, node in enumerate(linked_image_nodes_from_socket(socket, set())):
                            add_texture_node(
                                node,
                                spec["kind"],
                                spec["label"],
                                input_name,
                                spec["order"] * 100 + bsdf_index * 10 + node_index,
                            )

            for node_index, node in enumerate(texture_nodes(mat)):
                kind = infer_kind(
                    getattr(node, "name", ""),
                    getattr(node, "label", ""),
                    getattr(getattr(node, "image", None), "name", ""),
                    abs_path(getattr(getattr(node, "image", None), "filepath", "")),
                )
                item = texture_item(
                    getattr(node, "image", None),
                    mat.name,
                    getattr(node, "name", ""),
                    getattr(node, "label", ""),
                    kind,
                    ROLE_LABELS.get(kind, "Texture"),
                    "",
                    material_index * 10000 + 8000 + ROLE_ORDERS.get(kind, 90) * 100 + node_index,
                    material_index,
                )
                key = (item["path"], item["material"], item["node"])
                if key not in seen:
                    seen.add(key)
                    textures.append(item)
    textures.sort(key=lambda item: (item.get("sortOrder", 999999), item.get("file", ""), item.get("node", "")))
    objects.append({
        "name": obj.name,
        "type": obj.type,
        "materials": materials,
        "textures": textures,
    })

print("__CODEX_JSON_START__" + json.dumps({"objects": objects}, ensure_ascii=False) + "__CODEX_JSON_END__")
'''
    payload = run_blender_json(project_path, script)
    payload["project"] = str(project_path)
    return payload


def ensure_blender_replacement_texture_dir():
    BLENDER_REPLACEMENT_TEXTURE_DIR.mkdir(parents=True, exist_ok=True)


def ensure_blender_texture_package_dir(root=BLENDER_TEXTURE_PACKAGE_DIR):
    root.mkdir(parents=True, exist_ok=True)


def read_png_dimensions(data):
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    return None


def read_bmp_dimensions(data):
    if len(data) >= 26 and data[:2] == b"BM":
        width = struct.unpack_from("<i", data, 18)[0]
        height = struct.unpack_from("<i", data, 22)[0]
        if width and height:
            return abs(width), abs(height)
    return None


def read_jpeg_dimensions(data):
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    while index + 3 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            return None
        marker = data[index]
        index += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            return None
        segment_length = struct.unpack(">H", data[index:index + 2])[0]
        if segment_length < 2 or index + segment_length > len(data):
            return None
        if marker in sof_markers and segment_length >= 7:
            height, width = struct.unpack(">HH", data[index + 3:index + 7])
            return width, height
        index += segment_length
    return None


def read_webp_dimensions(data):
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width = struct.unpack_from("<H", data, 26)[0] & 0x3FFF
        height = struct.unpack_from("<H", data, 28)[0] & 0x3FFF
        return width, height
    return None


def texture_dimensions_from_bytes(data, suffix):
    suffix = suffix.lower()
    readers = {
        ".png": read_png_dimensions,
        ".jpg": read_jpeg_dimensions,
        ".jpeg": read_jpeg_dimensions,
        ".bmp": read_bmp_dimensions,
        ".webp": read_webp_dimensions,
    }
    reader = readers.get(suffix)
    if not reader:
        return None
    try:
        dimensions = reader(data)
    except (OSError, struct.error, ValueError):
        return None
    if not dimensions:
        return None
    width, height = dimensions
    if width <= 0 or height <= 0:
        return None
    return {"width": int(width), "height": int(height)}


def save_blender_replacement_texture(filename, data, source_package=""):
    target = unique_file_path(BLENDER_REPLACEMENT_TEXTURE_DIR, filename)
    target.write_bytes(data)
    record = {
        "name": target.name,
        "path": str(target),
        "size": target.stat().st_size,
    }
    if source_package:
        record["sourcePackage"] = source_package
    dimensions = texture_dimensions_from_bytes(data, target.suffix)
    if dimensions:
        record.update(dimensions)
    return record


def upload_blender_replacement_texture(files):
    ensure_blender_replacement_texture_dir()
    saved = []
    for item in files:
        filename = Path(str(item.get("filename", "")).replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        data = item.get("data", b"")
        if not filename or not data:
            continue
        if suffix in MATERIAL_TEXTURE_EXTENSIONS:
            saved.append(save_blender_replacement_texture(filename, data))
            continue
        if suffix in MATERIAL_PACKAGE_EXTENSIONS:
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for info in archive.infolist():
                        if info.is_dir():
                            continue
                        member_name = Path(info.filename.replace("\\", "/")).name
                        if Path(member_name).suffix.lower() not in MATERIAL_TEXTURE_EXTENSIONS:
                            continue
                        with archive.open(info) as source:
                            saved.append(save_blender_replacement_texture(member_name, source.read(), filename))
            except zipfile.BadZipFile as error:
                raise ValueError(f"{filename} is not a valid zip file") from error
    if not saved:
        raise ValueError("no texture files were uploaded")
    return {"ok": True, "files": saved, "directory": str(BLENDER_REPLACEMENT_TEXTURE_DIR)}


def texture_file_dimensions(path):
    try:
        return texture_dimensions_from_bytes(path.read_bytes(), path.suffix)
    except OSError:
        return None


def file_sha256(path):
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def texture_file_record(value):
    if not value:
        return {"path": "", "exists": False}
    try:
        path = Path(value).expanduser().resolve()
    except OSError:
        return {"path": str(value), "exists": False}
    if not path.exists() or not path.is_file():
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "name": path.name,
        "exists": True,
        "dimensions": texture_file_dimensions(path),
        "sha256": file_sha256(path),
    }


def texture_comparison_record(old_texture, new_texture):
    old_record = texture_file_record(old_texture)
    new_record = texture_file_record(new_texture)
    old_dimensions = old_record.get("dimensions")
    new_dimensions = new_record.get("dimensions")
    old_hash = old_record.get("sha256", "")
    new_hash = new_record.get("sha256", "")
    return {
        "old": old_record,
        "new": new_record,
        "sameDimensions": bool(old_dimensions and new_dimensions and old_dimensions == new_dimensions),
        "sameContent": bool(old_hash and new_hash and old_hash == new_hash),
    }


def blender_texture_package_name(object_name, material_name, config):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    object_slug = compact_object_slug(object_name)
    material_slug = compact_slug_part(material_name, "material", max_length=24)
    return f"{stamp}-{object_slug}-{material_slug}-{config['suffix']}"


def blender_texture_package_root(project_path):
    project_texture_dir = project_path.parent / "textures"
    if project_texture_dir.exists() and project_texture_dir.is_dir():
        return project_texture_dir / BLENDER_PROJECT_TEXTURE_PACKAGE_DIRNAME, "project-textures"
    return BLENDER_TEXTURE_PACKAGE_DIR, "global"


def path_exists(value):
    if not value:
        return False
    try:
        return Path(value).expanduser().exists()
    except OSError:
        return False


def write_json_file(path, payload):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_blender_texture_package_manifest(
    project_path,
    object_name,
    material_name,
    kind,
    config,
    old_texture,
    old_node,
    source_texture,
    copied_texture,
    package_dir,
    package_root,
    package_root_kind,
):
    comparison = texture_comparison_record(old_texture, copied_texture)
    return {
        "version": 1,
        "mode": "preview-package",
        "workflow": {
            "stage": "console-texture-intake",
            "consoleRole": "external workbench for reference gathering, browser/Photoshop handoff, old/new preview, comparison, and packaging into the Blender texture inbox",
            "blenderRole": "Blender plugin compares and applies texture changes inside the open Blender session",
            "unityRole": "Unity consumes the temp files exported by Blender and categorizes them into Builder assets",
        },
        "unityHandoff": {
            "blenderExportRoot": str(BLENDER_TO_UNITY_EXPORT_DIR),
            "unityTempFolder": str(UNITY_TEMP_BRIDGE_DIR),
            "rule": "Blender exports into the Unity temp bridge folder; Unity importer consumes that temp output and moves/categorizes it into Builder.",
        },
        "externalWorkbench": {
            "ownsBlenderMutation": False,
            "expectedTools": ["Photoshop", "Browser", "File Explorer"],
            "handoff": "The Blender plugin should read this package and decide how to apply it inside Blender.",
        },
        "pluginIntent": {
            "processor": "RandomRealm Blender plugin",
            "defaultScope": "selected-texture",
            "availableScopes": ["selected-texture", "selected-object", "all-matching-material", "all-matching-textures"],
            "recommendedAction": "compare-and-apply-in-blender",
        },
        "createdUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "project": str(project_path),
        "object": object_name,
        "material": material_name,
        "role": kind,
        "roleLabel": config["label"],
        "oldTexture": old_texture,
        "oldNode": old_node,
        "sourceTexture": str(source_texture),
        "packageRoot": str(package_root),
        "packageRootKind": package_root_kind,
        "newTexture": str(copied_texture),
        "newTextureRelative": copied_texture.relative_to(package_dir).as_posix(),
        "dimensions": comparison["new"].get("dimensions"),
        "comparison": comparison,
        "oldTextureExists": comparison["old"].get("exists", False),
        "notes": "Created by Codex Console for Blender plugin/node-render workflow. This package does not modify the Blender file.",
    }


def build_blender_texture_removal_manifest(
    project_path,
    object_name,
    material_name,
    kind,
    config,
    old_texture,
    old_node,
    package_dir,
    package_root,
    package_root_kind,
):
    old_record = texture_file_record(old_texture)
    return {
        "version": 1,
        "mode": "preview-package",
        "operation": "remove-texture",
        "workflow": {
            "stage": "console-texture-intake",
            "consoleRole": "external workbench for old/new preview, texture package assembly, and delete/add instructions",
            "blenderRole": "Blender plugin compares and applies texture changes inside the open Blender session",
            "unityRole": "Unity consumes the temp files exported by Blender and categorizes them into Builder assets",
        },
        "externalWorkbench": {
            "ownsBlenderMutation": False,
            "handoff": "The Blender plugin should remove this texture slot when Apply Latest Packages is run.",
        },
        "pluginIntent": {
            "processor": "RandomRealm Blender plugin",
            "defaultScope": "selected-texture",
            "availableScopes": ["selected-texture", "selected-object", "all-matching-material"],
            "recommendedAction": "remove-texture-in-blender",
        },
        "createdUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "project": str(project_path),
        "object": object_name,
        "material": material_name,
        "role": kind,
        "roleLabel": config["label"],
        "oldTexture": old_texture,
        "oldNode": old_node,
        "removeTexture": True,
        "newTexture": "",
        "newTextureRelative": "",
        "sourceTexture": "",
        "packageRoot": str(package_root),
        "packageRootKind": package_root_kind,
        "comparison": {
            "old": old_record,
            "new": {"path": "", "exists": False},
            "sameDimensions": False,
            "sameContent": False,
        },
        "oldTextureExists": old_record.get("exists", False),
        "notes": "Created by Codex Console as a deletion instruction. This package does not modify the Blender file by itself.",
    }


def package_blender_texture(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_name = str(payload.get("object", "")).strip()
    if not object_name:
        raise ValueError("object is required")

    new_texture = blender_texture_path(payload.get("newTexture", ""))
    kind = normalize_blender_texture_kind(payload.get("kind", "base-color"))
    config = BLENDER_TEXTURE_KIND_CONFIG[kind]
    material_name = str(payload.get("material") or payload.get("oldMaterial") or "").strip()
    old_texture = str(payload.get("oldTexture", "")).strip()
    old_node = str(payload.get("oldNode", "")).strip()

    package_root, package_root_kind = blender_texture_package_root(project_path)
    ensure_blender_texture_package_dir(package_root)
    package_dir = unique_directory(
        package_root,
        blender_texture_package_name(object_name, material_name, config),
    )
    new_dir = package_dir / "new"
    new_dir.mkdir(parents=True, exist_ok=False)

    copied_texture = unique_file_path(new_dir, new_texture.name)
    shutil.copy2(new_texture, copied_texture)

    manifest = build_blender_texture_package_manifest(
        project_path,
        object_name,
        material_name,
        kind,
        config,
        old_texture,
        old_node,
        new_texture,
        copied_texture,
        package_dir,
        package_root,
        package_root_kind,
    )
    manifest_path = package_dir / "manifest.json"
    write_json_file(manifest_path, manifest)

    return {
        "ok": True,
        "package": str(package_dir),
        "manifest": str(manifest_path),
        "texture": str(copied_texture),
        "name": package_dir.name,
        "packageRoot": str(package_root),
        "packageRootKind": package_root_kind,
        "dimensions": manifest["dimensions"],
        "comparison": manifest["comparison"],
    }


def package_blender_texture_removal(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_name = str(payload.get("object", "")).strip()
    if not object_name:
        raise ValueError("object is required")

    kind = normalize_blender_texture_kind(payload.get("kind", "base-color"))
    config = BLENDER_TEXTURE_KIND_CONFIG[kind]
    material_name = str(payload.get("material") or payload.get("oldMaterial") or "").strip()
    old_texture = str(payload.get("oldTexture", "")).strip()
    old_node = str(payload.get("oldNode", "")).strip()
    if not material_name and not old_texture and not old_node:
        raise ValueError("texture identity is required")

    package_root, package_root_kind = blender_texture_package_root(project_path)
    ensure_blender_texture_package_dir(package_root)
    removal_config = dict(config)
    removal_config["suffix"] = f"remove-{config['suffix']}"
    package_dir = unique_directory(
        package_root,
        blender_texture_package_name(object_name, material_name, removal_config),
    )
    package_dir.mkdir(parents=True, exist_ok=False)

    manifest = build_blender_texture_removal_manifest(
        project_path,
        object_name,
        material_name,
        kind,
        config,
        old_texture,
        old_node,
        package_dir,
        package_root,
        package_root_kind,
    )
    manifest_path = package_dir / "manifest.json"
    write_json_file(manifest_path, manifest)

    return {
        "ok": True,
        "package": str(package_dir),
        "manifest": str(manifest_path),
        "name": package_dir.name,
        "packageRoot": str(package_root),
        "packageRootKind": package_root_kind,
        "operation": "remove-texture",
    }


def is_allowed_blender_texture_package_dir(package_dir):
    try:
        package_path = Path(package_dir).expanduser().resolve()
    except OSError:
        return False

    global_root = BLENDER_TEXTURE_PACKAGE_DIR.expanduser()
    if global_root.exists() and is_path_inside(package_path, global_root.resolve()):
        return True

    if package_path.parent.name != BLENDER_PROJECT_TEXTURE_PACKAGE_DIRNAME:
        return False
    if package_path.parent.parent.name.lower() != "textures":
        return False

    allowed_roots = [root.resolve() for root in BLENDER_PROJECT_ROOTS if root.exists()]
    return not allowed_roots or any(is_path_inside(package_path, root) for root in allowed_roots)


def blender_texture_package_status(payload):
    requested = payload.get("packages", [])
    if not isinstance(requested, list):
        raise ValueError("packages must be a list")

    records = []
    for item in requested[:80]:
        value = item.get("package") if isinstance(item, dict) else item
        try:
            package_dir = Path(str(value or "")).expanduser().resolve()
        except OSError as error:
            records.append({
                "package": str(value or ""),
                "exists": False,
                "applied": False,
                "error": str(error),
            })
            continue

        record = {
            "package": str(package_dir),
            "exists": package_dir.is_dir(),
            "manifest": str(package_dir / "manifest.json"),
            "marker": str(package_dir / BLENDER_TEXTURE_PACKAGE_APPLIED_FILENAME),
            "applied": False,
            "appliedAt": "",
        }
        if not is_allowed_blender_texture_package_dir(package_dir):
            record["error"] = "package path is outside the Blender texture package folders"
            records.append(record)
            continue

        marker_path = package_dir / BLENDER_TEXTURE_PACKAGE_APPLIED_FILENAME
        if marker_path.exists():
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                marker = {}
            record["applied"] = True
            record["appliedAt"] = str(marker.get("appliedUtc") or marker.get("appliedAt") or "")
            record["result"] = marker
        records.append(record)

    return {"ok": True, "packages": records}


def blender_texture_path(value):
    target = Path(str(value or "")).expanduser().resolve()
    if not target.exists() or not target.is_file() or target.suffix.lower() not in MATERIAL_TEXTURE_EXTENSIONS:
        raise ValueError("new texture file was not found")
    return target


def blender_texture_preview_path(value):
    target = Path(str(value or "")).expanduser().resolve()
    if not target.exists() or not target.is_file() or target.suffix.lower() not in MATERIAL_TEXTURE_EXTENSIONS:
        raise ValueError("texture file was not found")
    if target.suffix.lower() not in PREVIEWABLE_TEXTURE_EXTENSIONS:
        raise ValueError("texture preview is available for png, jpg, bmp, and webp")

    allowed_roots = [root.resolve() for root in BLENDER_PROJECT_ROOTS if root.exists()]
    for root in (BLENDER_REPLACEMENT_TEXTURE_DIR, BLENDER_TEXTURE_PACKAGE_DIR, BUILDER_TEXTURE_DIR, MATERIAL_SOURCE_DIR, CODEX_TEMP_DIR):
        if root.exists():
            allowed_roots.append(root.resolve())
    if allowed_roots and not any(is_path_inside(target, root) for root in allowed_roots):
        raise ValueError("texture path is outside the configured texture roots")
    return target


def open_blender_texture_file(value):
    texture_path = blender_texture_preview_path(value)
    photoshop = find_photoshop_executable()
    if photoshop:
        subprocess.Popen(
            [str(photoshop), str(texture_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_subprocess_kwargs(),
        )
        return {"ok": True, "path": str(texture_path), "app": "Photoshop", "appPath": str(photoshop)}

    if sys.platform == "win32":
        os.startfile(str(texture_path))
        app = "default app"
    else:
        webbrowser.open(texture_path.as_uri())
        app = "default app"
    return {"ok": True, "path": str(texture_path), "app": app}


def start_native_file_drag(value):
    texture_path = blender_texture_preview_path(value)
    helper = ensure_native_file_drag_helper()
    subprocess.Popen(
        [str(helper), str(texture_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_subprocess_kwargs(),
    )
    return {"ok": True, "path": str(texture_path), "helper": str(helper)}


BLENDER_TEXTURE_KIND_CONFIG = {
    "base-color": {"label": "Base Color", "suffix": "basecolor", "color": (128, 128, 128, 255)},
    "normal": {"label": "Normal", "suffix": "normal", "color": (128, 128, 255, 255)},
    "roughness": {"label": "Roughness", "suffix": "roughness", "color": (180, 180, 180, 255)},
    "ambient-occlusion": {"label": "Ambient Occlusion", "suffix": "ao", "color": (255, 255, 255, 255)},
    "metallic": {"label": "Metallic", "suffix": "metallic", "color": (0, 0, 0, 255)},
    "height": {"label": "Height", "suffix": "height", "color": (128, 128, 128, 255)},
    "alpha": {"label": "Alpha", "suffix": "alpha", "color": (255, 255, 255, 255)},
    "emission": {"label": "Emission", "suffix": "emission", "color": (0, 0, 0, 255)},
}


def normalize_blender_texture_kind(value):
    key = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "basecolor": "base-color",
        "base-colour": "base-color",
        "albedo": "base-color",
        "diffuse": "base-color",
        "ao": "ambient-occlusion",
        "occlusion": "ambient-occlusion",
        "ambient": "ambient-occlusion",
        "ambient-occlusion": "ambient-occlusion",
        "ambientocclusion": "ambient-occlusion",
        "metalness": "metallic",
        "opacity": "alpha",
        "transparent": "alpha",
        "bump": "height",
    }
    key = aliases.get(key, key)
    if key not in BLENDER_TEXTURE_KIND_CONFIG:
        key = "base-color"
    return key


def normalize_texture_size(value):
    raw = str(value or "2048").strip().lower().replace("px", "")
    size_map = {"1k": 1024, "2k": 2048, "4k": 4096}
    size = size_map.get(raw)
    if size is None:
        try:
            size = int(float(raw))
        except ValueError:
            size = 2048
    if size <= 1024:
        return 1024
    if size <= 2048:
        return 2048
    return 4096


def texture_size_label(size):
    labels = {1024: "1k", 2048: "2k", 4096: "4k"}
    return labels.get(int(size), str(size))


def compact_slug_part(value, fallback, max_length=28, drop_tokens=None):
    text = str(value or "")
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", text)
    text = text.replace("&", " and ")
    text = text.encode("ascii", "ignore").decode("ascii")
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", text.lower()) if token]
    drop_tokens = set(drop_tokens or [])
    filtered = [
        token for token in tokens
        if token not in drop_tokens and not re.fullmatch(r"image\d*", token)
    ]
    useful = filtered or tokens
    if not useful:
        return fallback
    compact = "-".join(useful)
    if len(compact) <= max_length:
        return compact

    selected = []
    length = 0
    for token in useful:
        add = len(token) + (1 if selected else 0)
        if length + add > max_length:
            break
        selected.append(token)
        length += add
    return "-".join(selected) or compact[:max_length].rstrip("-") or fallback


def compact_object_slug(value):
    text = str(value or "")
    match = re.match(r"(?i)^([a-z]+)[_\-\s]*(?:\d+x\d+(?:x\d+)?)?[._\-\s]*(\d+)$", text)
    if match:
        return f"{match.group(1).lower()}-{match.group(2)}"
    return compact_slug_part(value, "object", max_length=22)


def compact_empty_texture_filename(object_name, material_name, suffix, size):
    object_slug = compact_object_slug(object_name)
    material_slug = compact_slug_part(
        material_name,
        "material",
        max_length=30,
        drop_tokens={"builder", "mat", "material", "pbr", "texture", "final", "codex"},
    )
    size_slug = texture_size_label(size)
    stem = f"{object_slug}-{material_slug}-{suffix}-{size_slug}"
    if len(stem) > 72:
        digest = hashlib.sha1(f"{object_name}|{material_name}|{suffix}|{size}".encode("utf-8")).hexdigest()[:6]
        tail = f"{suffix}-{size_slug}-{digest}"
        budget = max(18, 72 - len(tail) - 1)
        subject = f"{object_slug}-{material_slug}"[:budget].rstrip("-")
        stem = f"{subject}-{tail}"
    return f"{stem}.png"


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def solid_rgba_png_bytes(width, height, color):
    pixel = bytes(color)
    row = b"\x00" + pixel * width
    raw = row * height
    return b"".join([
        b"\x89PNG\r\n\x1a\n",
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        png_chunk(b"IDAT", zlib.compress(raw, 9)),
        png_chunk(b"IEND", b""),
    ])


def create_empty_blender_texture(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_name = str(payload.get("object", "")).strip()
    material_name = str(payload.get("material", "")).strip()
    if not object_name:
        raise ValueError("object is required")
    if not material_name:
        raise ValueError("material is required")

    kind = normalize_blender_texture_kind(payload.get("kind", "base-color"))
    config = BLENDER_TEXTURE_KIND_CONFIG[kind]
    size = normalize_texture_size(payload.get("size", "2048"))
    mutation_key = blender_mutation_key("create-empty-texture", project_path, object_name, material_name, kind, size)
    begin_blender_mutation(mutation_key)
    try:
        return create_empty_blender_texture_unlocked(project_path, object_name, material_name, kind, config, size)
    finally:
        end_blender_mutation(mutation_key)


def create_empty_blender_texture_unlocked(project_path, object_name, material_name, kind, config, size):
    texture_dir = project_path.parent / "textures"
    texture_dir.mkdir(parents=True, exist_ok=True)
    filename = compact_empty_texture_filename(object_name, material_name, config["suffix"], size)
    target = unique_file_path(texture_dir, filename)
    target.write_bytes(solid_rgba_png_bytes(size, size, config["color"]))
    stat = target.stat()
    return {
        "ok": True,
        "texture": {
            "name": target.name,
            "file": target.name,
            "path": str(target),
            "size": stat.st_size,
            "width": size,
            "height": size,
            "kind": kind,
            "material": material_name,
        },
        "directory": str(texture_dir),
    }


def stage_blank_blender_texture(payload):
    object_name = str(payload.get("object", "")).strip() or "object"
    material_name = str(payload.get("material", "")).strip() or "material"
    kind = normalize_blender_texture_kind(payload.get("kind", "base-color"))
    config = BLENDER_TEXTURE_KIND_CONFIG[kind]
    size = normalize_texture_size(payload.get("size", "2048"))
    ensure_blender_replacement_texture_dir()
    filename = compact_empty_texture_filename(object_name, material_name, config["suffix"], size)
    target = unique_file_path(BLENDER_REPLACEMENT_TEXTURE_DIR, filename)
    target.write_bytes(solid_rgba_png_bytes(size, size, config["color"]))
    stat = target.stat()
    record = {
        "name": target.name,
        "file": target.name,
        "path": str(target),
        "size": stat.st_size,
        "width": size,
        "height": size,
        "kind": kind,
        "material": material_name,
    }
    return {
        "ok": True,
        "texture": record,
        "files": [record],
        "directory": str(BLENDER_REPLACEMENT_TEXTURE_DIR),
    }


def add_blender_object_texture(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_name = str(payload.get("object", "")).strip()
    material_name = str(payload.get("material", "")).strip()
    kind = normalize_blender_texture_kind(payload.get("kind", "base-color"))
    new_texture = blender_texture_path(payload.get("newTexture", ""))
    if not object_name:
        raise ValueError("object is required")
    if not material_name:
        raise ValueError("material is required")

    mutation_key = blender_mutation_key("add-texture", project_path, object_name, material_name, kind)
    begin_blender_mutation(mutation_key)
    try:
        return add_blender_object_texture_unlocked(project_path, object_name, material_name, kind, new_texture)
    finally:
        end_blender_mutation(mutation_key)


def add_blender_object_texture_unlocked(project_path, object_name, material_name, kind, new_texture):
    backup = project_path.with_name(f"{project_path.stem}.codex-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{project_path.suffix}")
    shutil.copy2(project_path, backup)

    script = f'''
import bpy, json, os

object_name = {json.dumps(object_name)}
material_name = {json.dumps(material_name)}
kind = {json.dumps(kind)}
new_texture = {json.dumps(str(new_texture))}
project_path = {json.dumps(str(project_path))}

def socket(node, names):
    for name in names:
        item = node.inputs.get(name)
        if item:
            return item
    return None

def output_socket(node, names):
    for name in names:
        item = node.outputs.get(name)
        if item:
            return item
    return None

def unlink_target(links, target):
    for link in list(links):
        if link.to_socket == target:
            links.remove(link)

def connect_replace(links, source, target):
    if not source or not target:
        return False
    unlink_target(links, target)
    links.new(source, target)
    return True

def cleanup_orphan_helper_nodes():
    removed = []
    changed = True
    while changed:
        changed = False
        for node in list(nodes):
            if getattr(node, "type", "") not in {"NORMAL_MAP", "BUMP"}:
                continue
            has_output_links = any(getattr(output, "links", []) for output in getattr(node, "outputs", []))
            if has_output_links:
                continue
            removed.append(node.name)
            nodes.remove(node)
            changed = True
    return removed

def set_non_color(image):
    try:
        image.colorspace_settings.name = "Non-Color"
    except Exception:
        pass

def active_uv_name(obj):
    mesh = getattr(obj, "data", None)
    uv_layers = getattr(mesh, "uv_layers", None)
    if not uv_layers or len(uv_layers) == 0:
        return ""
    active = uv_layers.active or uv_layers[0]
    return getattr(active, "name", "") or ""

def find_or_create_uv_node(tex_node):
    uv_name = active_uv_name(obj)
    fallback = None
    for node in nodes:
        if getattr(node, "type", "") != "UVMAP":
            continue
        if uv_name and getattr(node, "uv_map", "") == uv_name:
            return node
        if fallback is None:
            fallback = node
    if fallback is not None:
        if uv_name and not getattr(fallback, "uv_map", ""):
            fallback.uv_map = uv_name
        return fallback
    uv_node = nodes.new("ShaderNodeUVMap")
    uv_node.name = "Codex UV Map"
    uv_node.label = "UV Map"
    if uv_name:
        uv_node.uv_map = uv_name
    uv_node.location = (tex_node.location.x - 260, tex_node.location.y)
    return uv_node

def ensure_texture_uv(tex_node):
    vector = socket(tex_node, ["Vector"])
    if not vector or vector.links:
        return False
    uv_node = find_or_create_uv_node(tex_node)
    output = output_socket(uv_node, ["UV"])
    if not output:
        return False
    links.new(output, vector)
    return True

obj = bpy.data.objects.get(object_name)
if obj is None:
    raise RuntimeError("object was not found: " + object_name)

mat = None
for slot in getattr(obj, "material_slots", []):
    candidate = getattr(slot, "material", None)
    if candidate and candidate.name == material_name:
        mat = candidate
        break
if mat is None:
    raise RuntimeError("material was not found: " + material_name)

mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
principled = next((node for node in nodes if getattr(node, "type", "") == "BSDF_PRINCIPLED"), None)
if principled is None:
    principled = nodes.new("ShaderNodeBsdfPrincipled")

def norm_path(value):
    return os.path.normcase(os.path.abspath(value)) if value else ""

def find_existing_texture_node():
    wanted_name = "Codex " + kind
    wanted_label = "Codex " + kind.replace("-", " ").title()
    wanted_path = norm_path(new_texture)
    for node in nodes:
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        image = getattr(node, "image", None)
        current = bpy.path.abspath(getattr(image, "filepath", "") or "") if image else ""
        if node.name == wanted_name or getattr(node, "label", "") == wanted_label or (wanted_path and norm_path(current) == wanted_path):
            return node
    return None

image = bpy.data.images.load(new_texture, check_existing=True)
tex = find_existing_texture_node()
reused = tex is not None
if tex is None:
    tex = nodes.new("ShaderNodeTexImage")
tex.image = image
tex.name = "Codex " + kind
tex.label = "Codex " + kind.replace("-", " ").title()
if not reused:
    tex.location = (principled.location.x - 650, principled.location.y)
uv_linked = ensure_texture_uv(tex)
color_out = output_socket(tex, ["Color"])
alpha_out = output_socket(tex, ["Alpha"])

changed = []
if reused:
    try:
        image.reload()
    except Exception:
        pass
if kind == "base-color":
    connect_replace(links, color_out, socket(principled, ["Base Color"]))
elif kind == "roughness":
    set_non_color(image)
    connect_replace(links, color_out, socket(principled, ["Roughness"]))
elif kind == "ambient-occlusion":
    set_non_color(image)
elif kind == "metallic":
    set_non_color(image)
    connect_replace(links, color_out, socket(principled, ["Metallic"]))
elif kind == "alpha":
    connect_replace(links, alpha_out or color_out, socket(principled, ["Alpha"]))
    for attr, value in [("blend_method", "BLEND"), ("use_screen_refraction", True)]:
        try:
            setattr(mat, attr, value)
        except Exception:
            pass
elif kind == "emission":
    connect_replace(links, color_out, socket(principled, ["Emission Color", "Emission"]))
elif kind == "normal":
    set_non_color(image)
    normal_input = socket(principled, ["Normal"])
    unlink_target(links, normal_input)
    cleanup_orphan_helper_nodes()
    normal = nodes.new("ShaderNodeNormalMap")
    normal.location = (principled.location.x - 360, principled.location.y - 180)
    links.new(color_out, socket(normal, ["Color"]))
    connect_replace(links, output_socket(normal, ["Normal"]), normal_input)
elif kind == "height":
    set_non_color(image)
    normal_input = socket(principled, ["Normal"])
    old_normal = None
    old_normal_node = None
    if normal_input:
        for link in list(links):
            if link.to_socket == normal_input:
                old_normal = link.from_socket
                old_normal_node = link.from_node
                links.remove(link)
                break
    cleanup_orphan_helper_nodes()
    bump = nodes.new("ShaderNodeBump")
    bump.location = (principled.location.x - 360, principled.location.y - 260)
    links.new(color_out, socket(bump, ["Height"]))
    if old_normal and old_normal_node and getattr(old_normal_node, "type", "") != "BUMP" and socket(bump, ["Normal"]):
        links.new(old_normal, socket(bump, ["Normal"]))
    connect_replace(links, output_socket(bump, ["Normal"]), normal_input)
cleanup_removed = cleanup_orphan_helper_nodes()

changed.append({{"material": mat.name, "node": tex.name, "kind": kind, "new": new_texture, "reused": reused, "uvLinked": uv_linked, "cleanupRemoved": cleanup_removed}})

bpy.ops.wm.save_as_mainfile(filepath=project_path, check_existing=False)
print("__CODEX_JSON_START__" + json.dumps({{"ok": True, "changed": changed}}, ensure_ascii=False) + "__CODEX_JSON_END__")
'''
    result = run_blender_json(project_path, script, timeout=60)
    result["project"] = str(project_path)
    result["backup"] = str(backup)
    return result


def normalize_blender_texture_removal_payload(payload):
    project_path = blender_project_path(payload.get("project", ""))
    raw_removals = payload.get("removals")
    if not isinstance(raw_removals, list):
        raw_removals = [payload]
    removals = []
    for item in raw_removals:
        if not isinstance(item, dict):
            continue
        object_name = str(item.get("object", "")).strip()
        old_texture = str(item.get("oldTexture", "")).strip()
        old_material = str(item.get("oldMaterial", "")).strip()
        old_node = str(item.get("oldNode", "")).strip()
        if not object_name:
            continue
        if not old_material and not old_node and not old_texture:
            continue
        removals.append({
            "object": object_name,
            "oldTexture": old_texture,
            "oldMaterial": old_material,
            "oldNode": old_node,
        })
    if not removals:
        raise ValueError("texture node identity is required")
    return project_path, removals


def remove_blender_object_textures(payload):
    project_path, removals = normalize_blender_texture_removal_payload(payload)

    backup = project_path.with_name(f"{project_path.stem}.codex-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{project_path.suffix}")
    shutil.copy2(project_path, backup)

    script = f'''
import bpy, json, os

removals = {json.dumps(removals)}
project_path = {json.dumps(str(project_path))}

def norm_path(value):
    return os.path.normcase(os.path.abspath(value)) if value else ""

removed = []
missing = []
for removal in removals:
    object_name = (removal.get("object") or "").strip()
    old_texture = norm_path((removal.get("oldTexture") or "").strip())
    old_material = (removal.get("oldMaterial") or "").strip()
    old_node = (removal.get("oldNode") or "").strip()
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        missing.append({{"object": object_name, "reason": "object not found"}})
        continue
    for slot in getattr(obj, "material_slots", []):
        mat = getattr(slot, "material", None)
        if not mat or not getattr(mat, "use_nodes", False) or not mat.node_tree:
            continue
        if old_material and mat.name != old_material:
            continue
        for node in list(mat.node_tree.nodes):
            if getattr(node, "type", "") != "TEX_IMAGE":
                continue
            if old_node and node.name != old_node:
                continue
            image = getattr(node, "image", None)
            current = bpy.path.abspath(getattr(image, "filepath", "") or "") if image else ""
            current_norm = norm_path(current)
            if old_texture and current_norm != old_texture:
                continue
            removed.append({{"object": object_name, "material": mat.name, "node": node.name, "old": current}})
            mat.node_tree.nodes.remove(node)

if not removed:
    raise RuntimeError("no matching image texture node was found on the selected object")

bpy.ops.wm.save_as_mainfile(filepath=project_path, check_existing=False)
print("__CODEX_JSON_START__" + json.dumps({{"ok": True, "removed": removed, "missing": missing}}, ensure_ascii=False) + "__CODEX_JSON_END__")
'''
    result = run_blender_json(project_path, script, timeout=60)
    result["project"] = str(project_path)
    result["backup"] = str(backup)
    return result


def remove_blender_object_texture(payload):
    return remove_blender_object_textures({
        "project": payload.get("project", ""),
        "removals": [payload],
    })


def delete_file_if_inside_roots(path, roots):
    if not path:
        return ""
    try:
        target = Path(path).resolve()
    except OSError:
        return ""
    if not target.exists() or not target.is_file():
        return ""
    resolved_roots = []
    for root in roots:
        try:
            resolved_roots.append(Path(root).resolve())
        except OSError:
            continue
    if resolved_roots and not any(is_path_inside(target, root) for root in resolved_roots):
        return ""
    target.unlink()
    return str(target)


def replace_blender_object_texture(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_name = str(payload.get("object", "")).strip()
    old_texture = str(payload.get("oldTexture", "")).strip()
    old_material = str(payload.get("oldMaterial", "")).strip()
    old_node = str(payload.get("oldNode", "")).strip()
    new_texture = blender_texture_path(payload.get("newTexture", ""))
    if not object_name:
        raise ValueError("object is required")
    if not old_texture and not old_material and not old_node:
        raise ValueError("old texture identity is required")

    backup = project_path.with_name(f"{project_path.stem}.codex-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{project_path.suffix}")
    shutil.copy2(project_path, backup)

    texture_backup = ""
    target_texture = new_texture
    relink_texture = ""
    same_path_replace = False
    try:
        old_texture_path = blender_texture_path(old_texture)
    except ValueError:
        old_texture_path = None
    if old_texture_path:
        same_path_replace = same_filesystem_path(old_texture_path, new_texture)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        texture_backup_path = old_texture_path.with_name(f"{old_texture_path.stem}.codex-backup-{stamp}{old_texture_path.suffix}")
        shutil.copy2(old_texture_path, texture_backup_path)
        if same_path_replace:
            relink_dir = BLENDER_REPLACEMENT_TEXTURE_DIR / "_same_path_relink"
            relink_dir.mkdir(parents=True, exist_ok=True)
            relink_path = unique_file_path(relink_dir, f"{old_texture_path.stem}-relink{old_texture_path.suffix}")
            shutil.copy2(old_texture_path, relink_path)
            relink_texture = str(relink_path)
        else:
            shutil.copy2(new_texture, old_texture_path)
        target_texture = old_texture_path
        texture_backup = str(texture_backup_path)

    script = f'''
import bpy, json, os

object_name = {json.dumps(object_name)}
old_texture_raw = {json.dumps(old_texture)}
old_texture = os.path.normcase(os.path.abspath(old_texture_raw)) if old_texture_raw else ""
old_material = {json.dumps(old_material)}
old_node = {json.dumps(old_node)}
new_texture = {json.dumps(str(target_texture))}
relink_texture = {json.dumps(relink_texture)}
same_path_replace = {repr(same_path_replace)}
project_path = {json.dumps(str(project_path))}

changed = []
obj = bpy.data.objects.get(object_name)
if obj is None:
    raise RuntimeError("object was not found: " + object_name)

def load_fresh_image(path, existing=None):
    image = existing if existing else bpy.data.images.load(path, check_existing=True)
    image.filepath = path
    try:
        image.reload()
    except Exception:
        pass
    return image

for slot in getattr(obj, "material_slots", []):
    mat = getattr(slot, "material", None)
    if not mat or not getattr(mat, "use_nodes", False) or not mat.node_tree:
        continue
    if old_material and mat.name != old_material:
        continue
    for node in mat.node_tree.nodes:
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        if old_node and node.name != old_node:
            continue
        image = getattr(node, "image", None)
        current = bpy.path.abspath(getattr(image, "filepath", "") or "") if image else ""
        current_norm = os.path.normcase(os.path.abspath(current)) if current else ""
        image_name = getattr(image, "name", "") if image else ""
        if (old_texture and current_norm == old_texture) or (old_texture_raw and image_name == old_texture_raw) or (not old_texture and old_node):
            before = current
            original_image = image
            try:
                if relink_texture:
                    bounce_image = load_fresh_image(relink_texture)
                    node.image = bounce_image
                    node.image.filepath = relink_texture
                fresh_image = load_fresh_image(new_texture, original_image)
                node.image = fresh_image
                node.image.filepath = new_texture
            except Exception as exc:
                raise RuntimeError("could not reload replacement image: " + str(exc))
            try:
                mat.node_tree.update_tag()
            except Exception:
                pass
            changed.append({{"material": mat.name, "node": node.name, "old": before, "new": new_texture, "samePath": same_path_replace}})

if not changed:
    raise RuntimeError("no matching image texture was found on the selected object")

bpy.ops.wm.save_as_mainfile(filepath=project_path, check_existing=False)
print("__CODEX_JSON_START__" + json.dumps({{"ok": True, "changed": changed}}, ensure_ascii=False) + "__CODEX_JSON_END__")
'''
    result = run_blender_json(project_path, script, timeout=60)
    deleted_originals = []
    cleanup_errors = []
    for cleanup_path, roots in [
        (texture_backup, [project_path.parent]),
        (relink_texture, [BLENDER_REPLACEMENT_TEXTURE_DIR]),
    ]:
        try:
            deleted = delete_file_if_inside_roots(cleanup_path, roots)
            if deleted:
                deleted_originals.append(deleted)
        except OSError as error:
            cleanup_errors.append(f"{cleanup_path}: {error}")

    if old_texture_path and not same_path_replace and not same_filesystem_path(new_texture, old_texture_path):
        try:
            deleted = delete_file_if_inside_roots(new_texture, [BLENDER_REPLACEMENT_TEXTURE_DIR])
            if deleted:
                deleted_originals.append(deleted)
        except OSError as error:
            cleanup_errors.append(f"{new_texture}: {error}")

    result["project"] = str(project_path)
    result["backup"] = str(backup)
    result["textureBackup"] = texture_backup
    result["inPlaceTexture"] = str(target_texture) if texture_backup else ""
    result["samePathReplace"] = same_path_replace
    result["relinkTexture"] = relink_texture
    result["deletedOriginals"] = deleted_originals
    result["cleanupErrors"] = cleanup_errors
    return result


def unique_blender_object_names(payload):
    raw_items = payload.get("objects")
    if not isinstance(raw_items, list):
        raw_items = []
    raw_items.append(payload.get("object", ""))
    names = []
    seen = set()
    for item in raw_items:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    if not names:
        raise ValueError("object is required")
    return names


def write_unity_bridge_request(project_path, export_results, source_object_label=""):
    export_results = [item for item in export_results if isinstance(item, dict)]
    if not export_results:
        raise ValueError("no Blender export packages were created")

    external_manifest_paths = []
    unity_temp_manifest_paths = []
    package_ids = []
    temp_folders = []
    for item in export_results:
        package_dir = ensure_child_path(BLENDER_TO_UNITY_EXPORT_DIR, item.get("packageDir", ""), "export package")
        manifest_path = ensure_child_path(package_dir, package_dir / "manifest.json", "manifest")
        if not manifest_path.exists():
            raise ValueError("Blender export did not create manifest.json")
        external_manifest_paths.append(str(manifest_path))
        package_ids.append(str(item.get("id") or package_dir.name))
        if item.get("unityTempFolder"):
            temp_dir = ensure_child_path(UNITY_TEMP_BRIDGE_DIR, item.get("unityTempFolder"), "Unity temp package")
            temp_manifest = temp_dir / "manifest.json"
            if not temp_manifest.exists():
                raise ValueError("Unity temp package did not include manifest.json")
            temp_folders.append(str(temp_dir))
            unity_temp_manifest_paths.append(str(temp_manifest))

    package_label = package_ids[0] if len(package_ids) == 1 else f"{len(package_ids)} objects"
    UNITY_BRIDGE_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    manifest_paths = unity_temp_manifest_paths or external_manifest_paths
    source_folder = str(UNITY_TEMP_BRIDGE_DIR.resolve()) if unity_temp_manifest_paths else str(BLENDER_TO_UNITY_EXPORT_DIR.resolve())
    request = {
        "version": 1,
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "sourceFolder": source_folder,
        "sourceExportFolder": str(BLENDER_TO_UNITY_EXPORT_DIR.resolve()),
        "manifestPaths": manifest_paths,
        "externalManifestPaths": external_manifest_paths,
        "packageId": package_label,
        "packageIds": package_ids,
        "sourceBlend": str(project_path),
        "sourceObject": source_object_label or package_label,
        "tempFolder": temp_folders[0] if len(temp_folders) == 1 else str(UNITY_TEMP_BRIDGE_DIR.resolve()),
        "tempFolders": temp_folders,
        "selectAsset": f"Assets/Art/Generated/Builds/{package_ids[0]}/model.fbx",
    }
    temp_request = UNITY_BRIDGE_REQUEST_FILE.with_suffix(".tmp")
    temp_request.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_request, UNITY_BRIDGE_REQUEST_FILE)
    return request


def randomrealm_unity_bridge_status():
    status_file = RANDOMREALM_PROJECT_DIR / "Temp" / "CodexBlenderToUnity.status.json"
    status = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            status = {}

    packages = []
    if UNITY_TEMP_BRIDGE_DIR.exists():
        for path in sorted(UNITY_TEMP_BRIDGE_DIR.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
            if not path.is_dir():
                continue
            manifest = path / "manifest.json"
            packages.append({
                "id": path.name,
                "path": str(path),
                "manifest": str(manifest) if manifest.exists() else "",
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            })
            if len(packages) >= 12:
                break

    request_pending = UNITY_BRIDGE_REQUEST_FILE.exists()
    state = "pending" if request_pending else str(status.get("state") or "ready")
    message = "Unity import request is waiting" if request_pending else str(status.get("message") or "Ready")
    return {
        "ok": True,
        "state": state,
        "message": message,
        "status": status,
        "requestPending": request_pending,
        "request": str(UNITY_BRIDGE_REQUEST_FILE),
        "tempFolder": str(UNITY_TEMP_BRIDGE_DIR),
        "packages": packages,
    }


def export_blender_to_unity(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_names = unique_blender_object_names(payload)
    if len(object_names) == 1:
        single_payload = dict(payload)
        single_payload["object"] = object_names[0]
        single_payload["objects"] = [object_names[0]]
        return export_blender_object_to_unity(single_payload)

    results = []
    for object_name in object_names:
        item_payload = dict(payload)
        item_payload["object"] = object_name
        item_payload["objects"] = [object_name]
        item_payload["deferUnityRequest"] = True
        results.append(export_blender_object_to_unity(item_payload))

    request = write_unity_bridge_request(project_path, results, ", ".join(object_names))
    return {
        "ok": True,
        "id": request["packageId"],
        "packageId": request["packageId"],
        "packageIds": request["packageIds"],
        "count": len(results),
        "results": results,
        "project": str(project_path),
        "exportRoot": str(BLENDER_TO_UNITY_EXPORT_DIR.resolve()),
        "unityTempFolder": str(UNITY_TEMP_BRIDGE_DIR.resolve()),
        "unityRequest": str(UNITY_BRIDGE_REQUEST_FILE),
    }


def export_blender_object_to_unity(payload):
    project_path = blender_project_path(payload.get("project", ""))
    object_name = str(payload.get("object", "")).strip()
    if not object_name:
        raise ValueError("object is required")

    export_root = BLENDER_TO_UNITY_EXPORT_DIR.resolve()
    temp_bridge_root = UNITY_TEMP_BRIDGE_DIR.resolve()
    export_root.mkdir(parents=True, exist_ok=True)
    temp_bridge_root.mkdir(parents=True, exist_ok=True)

    script = r'''
import bpy
import json
import os
import re
import shutil
from datetime import datetime, timezone

project_path = __PROJECT_PATH__
object_name = __OBJECT_NAME__
export_root = __EXPORT_ROOT__
fail_on_problems = __FAIL_ON_PROBLEMS__

def safe_id(value, fallback="Object"):
    text = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "")).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = fallback + "_" + text
    return text[:90]

def display_name(value):
    text = re.sub(r"[_\.]+", " ", str(value or "")).strip()
    return text or "Blender Object"

def infer_type(name):
    key = str(name or "").lower().replace("-", "_")
    compact = key.replace("_", "")
    if compact.startswith("innerwall"):
        return "InnerWall"
    if key.startswith("wall"):
        return "Wall"
    if key.startswith("floor"):
        return "Floor"
    if key.startswith("stair"):
        return "Stair"
    if key.startswith("ramp"):
        return "Ramp"
    if key.startswith("cube"):
        return "Cube"
    return "Prop"

def inside(path, root):
    return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)

def image_path(image):
    if not image:
        return ""
    raw = getattr(image, "filepath", "") or ""
    if not raw:
        return ""
    try:
        return os.path.abspath(bpy.path.abspath(raw))
    except Exception:
        return os.path.abspath(raw)

def socket_by_name(node, names):
    if not node:
        return None
    for name in names:
        item = node.inputs.get(name)
        if item:
            return item
    return None

def find_principled(mat):
    if not mat or not getattr(mat, "use_nodes", False) or not mat.node_tree:
        return None
    for node in mat.node_tree.nodes:
        if getattr(node, "type", "") == "BSDF_PRINCIPLED":
            return node
    return None

def image_from_socket(socket, visited=None):
    if socket is None:
        return None
    visited = visited or set()
    for link in getattr(socket, "links", []):
        node = getattr(link, "from_node", None)
        if node is None or node.name in visited:
            continue
        visited.add(node.name)
        if getattr(node, "type", "") == "TEX_IMAGE":
            return getattr(node, "image", None)
        for input_socket in getattr(node, "inputs", []):
            image = image_from_socket(input_socket, visited)
            if image:
                return image
    return None

def infer_texture_role(*values):
    text = " ".join(str(value or "") for value in values).lower()
    compact = re.sub(r"[^a-z0-9]+", "", text)
    if "normal" in compact or compact.endswith("nrm"):
        return "normal"
    if "rough" in compact:
        return "roughness"
    if "occlusion" in compact or "ambientocclusion" in compact or re.search(r"(^|[^a-z])ao([^a-z]|$)", text):
        return "occlusion"
    if "metallicsmoothness" in compact or "metallic" in compact or "metalness" in compact:
        return "metallicSmoothness"
    if "basecolor" in compact or "basecolour" in compact or "albedo" in compact or "diffuse" in compact or "color" in compact or "colour" in compact:
        return "baseColor"
    return ""

def texture_nodes(mat):
    if not mat or not getattr(mat, "use_nodes", False) or not mat.node_tree:
        return []
    return [node for node in mat.node_tree.nodes if getattr(node, "type", "") == "TEX_IMAGE"]

def material_role_images(mat):
    roles = {}
    principled = find_principled(mat)
    if principled:
        for role, names in [
            ("baseColor", ["Base Color"]),
            ("roughness", ["Roughness"]),
            ("metallicSmoothness", ["Metallic"]),
            ("normal", ["Normal"]),
            ("occlusion", ["Ambient Occlusion", "Occlusion"]),
        ]:
            image = image_from_socket(socket_by_name(principled, names))
            if image:
                roles[role] = image

    for node in texture_nodes(mat):
        image = getattr(node, "image", None)
        path = image_path(image)
        role = infer_texture_role(getattr(node, "name", ""), getattr(node, "label", ""), getattr(image, "name", ""), path)
        if role and role not in roles:
            roles[role] = image
    return roles

def copy_texture(source_path, package_dir, material_name, role, used_names):
    source_path = os.path.abspath(source_path)
    textures_dir = os.path.join(package_dir, "textures")
    os.makedirs(textures_dir, exist_ok=True)
    base = safe_id(material_name, "Material") + "_" + safe_id(role, "Map") + "_" + os.path.basename(source_path)
    stem, ext = os.path.splitext(base)
    candidate = base
    index = 2
    while candidate.lower() in used_names:
        candidate = f"{stem}_{index}{ext}"
        index += 1
    used_names.add(candidate.lower())
    target = os.path.join(textures_dir, candidate)
    shutil.copy2(source_path, target)
    return "textures/" + candidate

def collect_meshes(root):
    meshes = []
    if getattr(root, "type", "") == "MESH":
        meshes.append(root)
    for child in getattr(root, "children_recursive", []):
        if getattr(child, "type", "") == "MESH":
            meshes.append(child)
    return meshes

root = bpy.data.objects.get(object_name)
errors = []
warnings = []
if root is None:
    errors.append("Object not found: " + object_name)
    meshes = []
else:
    meshes = collect_meshes(root)
    if not meshes:
        errors.append(object_name + " has no mesh to export.")

if meshes:
    checked = set()
    for obj in meshes:
        for slot in getattr(obj, "material_slots", []):
            mat = getattr(slot, "material", None)
            if not mat or mat.name in checked:
                continue
            checked.add(mat.name)
            for node in texture_nodes(mat):
                image = getattr(node, "image", None)
                path = image_path(image)
                if path and not os.path.exists(path):
                    errors.append(f"{mat.name}/{node.name}: missing texture file {path}")
                elif not path and getattr(image, "packed_file", None):
                    warnings.append(f"{mat.name}/{node.name}: packed image was not copied to Unity.")

if errors and fail_on_problems:
    print("__CODEX_JSON_START__" + json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False) + "__CODEX_JSON_END__")
    raise SystemExit(0)

package_id = safe_id(object_name)
package_dir = os.path.abspath(os.path.join(export_root, package_id))
if not inside(package_dir, export_root):
    errors.append("Export package path escaped the export root.")
    print("__CODEX_JSON_START__" + json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False) + "__CODEX_JSON_END__")
    raise SystemExit(0)

if os.path.isdir(package_dir):
    shutil.rmtree(package_dir)
os.makedirs(package_dir, exist_ok=True)

used_texture_names = set()
material_maps = []
seen_materials = set()
for obj in meshes:
    for slot in getattr(obj, "material_slots", []):
        mat = getattr(slot, "material", None)
        if not mat or mat.name in seen_materials:
            continue
        seen_materials.add(mat.name)
        role_images = material_role_images(mat)
        entry = {"material": mat.name}
        for role, image in role_images.items():
            path = image_path(image)
            if not path or not os.path.exists(path):
                continue
            entry[role] = copy_texture(path, package_dir, mat.name, role, used_texture_names)
        if len(entry) > 1:
            material_maps.append(entry)

if not material_maps:
    warnings.append(package_id + ": no usable image texture maps were found.")

model_path = os.path.join(package_dir, "model.fbx")
bpy.ops.object.select_all(action="DESELECT")
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0] if meshes else root
bpy.context.view_layer.update()
bpy.ops.export_scene.fbx(
    filepath=model_path,
    use_selection=True,
    object_types={"MESH"},
    use_mesh_modifiers=True,
    add_leaf_bones=False,
    bake_anim=False,
    path_mode="AUTO",
    apply_unit_scale=True,
    axis_forward="-Z",
    axis_up="Y",
)

manifest = {
    "schemaVersion": 1,
    "profile": "CodexBridge",
    "id": package_id,
    "displayName": display_name(object_name),
    "type": infer_type(object_name),
    "sourceBlend": project_path,
    "sourceObject": object_name,
    "exportedAtUtc": datetime.now(timezone.utc).isoformat(),
    "modelFile": "model.fbx",
    "iconFile": "icon.png",
    "unityModelScale": 1.0,
    "warnings": warnings,
    "materialMaps": material_maps,
}
manifest_path = os.path.join(package_dir, "manifest.json")
with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, ensure_ascii=False, indent=2)

print("__CODEX_JSON_START__" + json.dumps({
    "ok": True,
    "id": package_id,
    "type": manifest["type"],
    "packageDir": package_dir,
    "manifestPath": manifest_path,
    "modelPath": model_path,
    "textureCount": sum(max(0, len(item) - 1) for item in material_maps),
    "materialCount": len(material_maps),
    "warnings": warnings,
}, ensure_ascii=False) + "__CODEX_JSON_END__")
'''
    script = script.replace("__PROJECT_PATH__", json.dumps(str(project_path)))
    script = script.replace("__OBJECT_NAME__", json.dumps(object_name))
    script = script.replace("__EXPORT_ROOT__", json.dumps(str(export_root)))
    script = script.replace("__FAIL_ON_PROBLEMS__", "True" if payload.get("failOnProblems", True) else "False")

    result = run_blender_json(project_path, script, timeout=180)
    if not result.get("ok"):
        problems = result.get("errors") if isinstance(result.get("errors"), list) else []
        raise ValueError("; ".join(problems[:4]) or "Blender export preflight failed")

    package_dir = ensure_child_path(export_root, result.get("packageDir", ""), "export package")
    manifest_path = ensure_child_path(package_dir, package_dir / "manifest.json", "manifest")
    if not manifest_path.exists():
        raise ValueError("Blender export did not create manifest.json")

    icon_path = package_dir / "icon.png"
    if not icon_path.exists():
        icon_path.write_bytes(solid_rgba_png_bytes(128, 128, (84, 150, 220, 255)))

    mirror_dir = ensure_child_path(temp_bridge_root, temp_bridge_root / package_dir.name, "Unity temp package")
    if mirror_dir.exists():
        shutil.rmtree(mirror_dir)
    shutil.copytree(package_dir, mirror_dir)

    result.update({
        "project": str(project_path),
        "exportRoot": str(export_root),
        "unityTempFolder": str(mirror_dir),
        "unityRequest": "",
    })
    if not payload.get("deferUnityRequest"):
        request = write_unity_bridge_request(project_path, [result], object_name)
        result["packageId"] = request["packageId"]
        result["unityRequest"] = str(UNITY_BRIDGE_REQUEST_FILE)
    return result


def ensure_music_dir():
    MUSIC_DIR.mkdir(exist_ok=True)


def ensure_youtube_cookie_dir():
    YOUTUBE_COOKIE_DIR.mkdir(parents=True, exist_ok=True)


def blender_mutation_key(*parts):
    return "\u001f".join(str(part or "") for part in parts)


def begin_blender_mutation(key):
    now = time.time()
    with BLENDER_MUTATION_LOCK:
        stale = [item for item, timestamp in BLENDER_MUTATION_KEYS.items() if now - timestamp > BLENDER_MUTATION_TTL_SECONDS]
        for item in stale:
            BLENDER_MUTATION_KEYS.pop(item, None)
        if key in BLENDER_MUTATION_KEYS:
            raise ValueError("same Blender operation is already running")
        BLENDER_MUTATION_KEYS[key] = now


def end_blender_mutation(key):
    with BLENDER_MUTATION_LOCK:
        BLENDER_MUTATION_KEYS.pop(key, None)


def ensure_music_library_dir():
    ensure_music_dir()
    MUSIC_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ensure_youtube_cookie_dir()


def music_path_from_relative(relative_path):
    ensure_music_dir()
    clean = str(relative_path or "").replace("\\", "/").lstrip("/")
    if not clean:
        raise ValueError("music path is required")
    candidate = (MUSIC_DIR / clean).resolve()
    if not is_path_inside(candidate, MUSIC_DIR):
        raise ValueError("music path is outside the music folder")
    if not candidate.exists() or candidate.suffix.lower() not in MUSIC_EXTENSIONS:
        raise ValueError("music file was not found")
    return candidate


def safe_music_filename(filename):
    raw_name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(raw_name).suffix.lower()
    if suffix not in MUSIC_EXTENSIONS:
        raise ValueError("only mp3, wav, m4a, aac, flac, ogg, and opus files can be added")

    stem = Path(raw_name).stem.strip()
    stem = re.sub(r"[^\w .()\-]+", "-", stem, flags=re.UNICODE).strip(" .-_")
    if not stem:
        stem = "track"
    return f"{stem}{suffix}"


def unique_music_path(filename):
    ensure_music_dir()
    safe_name = safe_music_filename(filename)
    base = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    candidate = (MUSIC_DIR / safe_name).resolve()
    index = 2

    while candidate.exists():
        candidate = (MUSIC_DIR / f"{base}-{index}{suffix}").resolve()
        index += 1

    if not is_path_inside(candidate, MUSIC_DIR):
        raise ValueError("music path is outside the music folder")
    return candidate


def clean_music_stem(stem):
    name = str(stem or "").replace("_", " ").strip()
    name = re.sub(r"^\d{3,4}[-\s]+", "", name).strip()
    name = re.sub(r"[-\s]+[A-Za-z0-9_-]{11}$", "", name).strip()
    name = re.sub(r"\s+", " ", name)
    return name.strip(" -")


def display_music_name(stem):
    name = clean_music_stem(stem)
    if re.match(r"(?i)^a8\s*-\s*", name):
        suffix = re.sub(r"(?i)^a8\s*-\s*", "", name).strip(" -")
        return f"A8 - {suffix}" if suffix else "A8"

    lower = name.lower()
    if "asphalt 8" not in lower and "airborne" not in lower:
        return name

    song = re.sub(r"(?i)^asphalt\s*8\s*(?:new\s+song\s*)?", "", name).strip(" -")
    song = re.split(r"(?i)\s+asphalt\s*8\b", song, maxsplit=1)[0].strip(" -")
    song = re.split(r"(?i)\s*-\s*by\b", song, maxsplit=1)[0].strip(" -")
    song = re.split(r"(?i)\s*-\s*dj\b", song, maxsplit=1)[0].strip(" -")
    song = re.split(r"\s+-\s+", song, maxsplit=1)[0].strip(" -")
    song = re.sub(r"(?i)\b(?:official|video|audio|ost|soundtrack)\b.*$", "", song).strip(" -")
    song = re.sub(r"\s+", " ", song).strip(" -")
    return f"A8 - {song or name}"


def music_name_key(name):
    normalized = unicodedata.normalize("NFKC", str(name or "")).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def music_path_name_key(path):
    return music_name_key(display_music_name(path.stem))


def local_music_name_keys():
    ensure_music_dir()
    keys = set()
    for path in MUSIC_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MUSIC_EXTENSIONS:
            continue
        if is_path_inside(path.resolve(), MUSIC_LIBRARY_DIR):
            continue
        key = music_path_name_key(path)
        if key:
            keys.add(key)
    return keys


def list_music():
    ensure_music_dir()
    items = []
    for path in MUSIC_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MUSIC_EXTENSIONS:
            continue
        if is_path_inside(path.resolve(), MUSIC_LIBRARY_DIR):
            continue
        try:
            item = music_track_from_path(path)
        except OSError:
            continue
        items.append(item)
    items.sort(key=lambda item: item["modified"], reverse=True)
    return items


def upload_music(files):
    saved = []
    for item in files:
        target = unique_music_path(item.get("filename", ""))
        data = item.get("data", b"")
        if not data:
            continue
        target.write_bytes(data)
        saved.append(music_track_from_path(target))

    if not saved:
        raise ValueError("no music files were uploaded")

    return {"ok": True, "files": saved, "tracks": list_music()}


def sanitize_console_module_id(value):
    clean = str(value or "").strip().lower()
    return clean if clean in CONSOLE_MODULE_HREFS and console_module_allowed(clean) else "wallpaper"


def read_console_state():
    try:
        raw = json.loads(CONSOLE_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    module_id = sanitize_console_module_id(raw.get("lastModule"))
    return {
        "lastModule": module_id,
        "href": CONSOLE_MODULE_HREFS[module_id],
    }


def write_console_state(payload):
    current = read_console_state()
    if isinstance(payload, dict) and "lastModule" in payload:
        module_id = sanitize_console_module_id(payload.get("lastModule"))
        current = {
            "lastModule": module_id,
            "href": CONSOLE_MODULE_HREFS[module_id],
        }
    CONSOLE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONSOLE_STATE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "state": current}


def console_start_url(port):
    href = read_console_state().get("href") or "index.html"
    if href not in CONSOLE_MODULE_HREFS.values():
        href = "index.html"
    module_id = console_module_id_from_href(href)
    if not console_module_allowed(module_id):
        href = CONSOLE_MODULE_HREFS["wallpaper"]
    return f"http://127.0.0.1:{port}/{href}{console_edition_query()}"


def sanitize_string_map(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        clean_key = str(key or "").replace("\\", "/").lstrip("/").strip()
        clean_item = str(item or "").replace("\\", "/").lstrip("/").strip()
        if clean_key and clean_item:
            result[clean_key] = clean_item
    return result


def sanitize_string_list(value):
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        clean = str(item or "").replace("\\", "/").lstrip("/").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def read_music_state():
    try:
        raw = json.loads(MUSIC_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "tiers": sanitize_string_map(raw.get("tiers")),
        "order": sanitize_string_list(raw.get("order")),
        "promotedLibraryTracks": sanitize_string_map(raw.get("promotedLibraryTracks")),
    }


def music_state_payload_version(payload):
    try:
        return int(payload.get("stateVersion") or 0)
    except (TypeError, ValueError):
        return 0


def write_music_state(payload):
    previous = read_music_state()
    current = dict(previous)
    if isinstance(payload, dict):
        if "tiers" in payload:
            next_tiers = sanitize_string_map(payload.get("tiers"))
            if previous.get("tiers") and not next_tiers:
                return {"ok": False, "staleClient": True, "state": previous}
            current["tiers"] = next_tiers
        if "order" in payload:
            current["order"] = sanitize_string_list(payload.get("order"))
        if "promotedLibraryTracks" in payload:
            current["promotedLibraryTracks"] = sanitize_string_map(payload.get("promotedLibraryTracks"))

    MUSIC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if previous != current:
        MUSIC_STATE_BACKUP_FILE.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
    MUSIC_STATE_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "state": current}


def local_music_path_for_display_name(display_name):
    clean_name = str(display_name or "").strip().casefold()
    if not clean_name:
        return None
    ensure_music_dir()
    for path in MUSIC_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MUSIC_EXTENSIONS:
            continue
        if is_path_inside(path.resolve(), MUSIC_LIBRARY_DIR):
            continue
        if display_music_name(path.stem).casefold() == clean_name:
            return path
    return None


def delete_music(relative_path):
    path = music_path_from_relative(relative_path)
    path.unlink()
    return {"ok": True, "deleted": str(path), "tracks": list_music(), "libraries": list_music_libraries()}


def promote_library_music(relative_path):
    source = music_path_from_relative(relative_path)
    if not is_path_inside(source.resolve(), MUSIC_LIBRARY_DIR):
        raise ValueError("only Library tracks can be added to local music")
    display_name = display_music_name(source.stem)
    target = local_music_path_for_display_name(display_name)
    if not target:
        target = unique_music_path(f"{display_name}{source.suffix.lower()}")
        shutil.copy2(source, target)
    try:
        source.unlink()
    except OSError:
        pass
    return {
        "ok": True,
        "file": music_track_from_path(target),
        "tracks": list_music(),
        "libraries": list_music_libraries(),
    }


def validate_music_url(url):
    clean = str(url or "").strip()
    parsed = urllib.parse.urlparse(clean)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("a valid http or https URL is required")
    return clean


def normalize_youtube_video_url(url):
    clean = validate_music_url(url)
    parsed = urllib.parse.urlparse(clean)
    host = (parsed.hostname or "").lower()
    query = urllib.parse.parse_qs(parsed.query)
    video_id = ""

    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            video_id = (query.get("v") or [""])[0]
        elif parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            video_id = parsed.path.strip("/").split("/")[1] if len(parsed.path.strip("/").split("/")) > 1 else ""

    video_id = str(video_id or "").strip()
    if video_id:
        return f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id, safe='')}"
    return clean


def youtube_cookie_state():
    try:
        stat = YOUTUBE_COOKIE_FILE.stat()
    except OSError:
        return {"available": False, "path": "", "updated": "", "size": 0}
    return {
        "available": True,
        "path": str(YOUTUBE_COOKIE_FILE),
        "updated": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "size": stat.st_size,
    }


def youtube_cookie_file():
    state = youtube_cookie_state()
    return YOUTUBE_COOKIE_FILE if state["available"] else None


def upload_youtube_cookies(files):
    if not files:
        raise ValueError("no cookies file was uploaded")
    item = files[0]
    filename = str(item.get("filename") or "").lower()
    data = item.get("data", b"")
    if not data:
        raise ValueError("cookies file is empty")
    if not filename.endswith(".txt"):
        raise ValueError("please upload a cookies.txt file")

    text = data.decode("utf-8", errors="replace")
    lowered = text.lower()
    if "youtube.com" not in lowered and ".youtube.com" not in lowered:
        raise ValueError("this cookies file does not appear to contain YouTube cookies")

    ensure_youtube_cookie_dir()
    YOUTUBE_COOKIE_FILE.write_bytes(data)
    return {"ok": True, "cookies": youtube_cookie_state(), "tracks": list_music()}


def music_url_provider(url):
    host = urllib.parse.urlparse(url).hostname or ""
    host = host.lower()
    if host == "youtu.be" or host.endswith("youtube.com"):
        return "YouTube"
    return host or "URL"


def normalize_youtube_playlist_url(url):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be" or host.endswith("youtube.com"):
        query = urllib.parse.parse_qs(parsed.query)
        playlist_id = (query.get("list") or [""])[0].strip()
        if playlist_id:
            return f"https://www.youtube.com/playlist?list={urllib.parse.quote(playlist_id, safe='')}"
    return url


def python_console_executable():
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(executable)


def yt_dlp_command():
    downloader = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if downloader:
        return [downloader]
    completed = subprocess.run(
        [python_console_executable(), "-m", "yt_dlp", "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        **hidden_subprocess_kwargs(),
    )
    if completed.returncode == 0:
        return [python_console_executable(), "-m", "yt_dlp"]
    return []


def ffmpeg_location():
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if ffmpeg:
        return str(Path(ffmpeg).parent)
    bundled = Path("D:/misc/ffmpeg/ffmpeg-7.1.1-essentials_build/bin/ffmpeg.exe")
    if bundled.exists():
        return str(bundled.parent)
    return ""


def node_js_runtime_arg():
    configured = os.environ.get("CODEX_CONTROL_NODE_RUNTIME", "")
    candidates = [
        configured,
        r"C:\Users\Randy\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
        shutil.which("node"),
        shutil.which("node.exe"),
    ]
    for item in candidates:
        if item and Path(item).exists():
            return f"node:{item}"
    return ""


def node_js_runtime_config():
    arg = node_js_runtime_arg()
    if not arg:
        return {"deno": {}}
    runtime, path = ([*arg.split(":", 1), None])[:2]
    return {"deno": {}, runtime: {"path": path}}


def friendly_yt_dlp_error(message):
    clean = str(message or "").strip()
    lowered = clean.lower()
    if "sign in to confirm" in lowered and "not a bot" in lowered:
        return "YouTube 要求登录验证。请先在 Music 里导入 YouTube cookies.txt；如果没有 cookies.txt，再勾选使用 Edge 登录状态后重试。"
    if "could not copy chrome cookie database" in lowered or "failed to decrypt" in lowered or "cookie" in lowered and "decrypt" in lowered:
        return "浏览器 cookies 读取失败。请导出 YouTube cookies.txt 后在 Music 里导入，再重试。"
    if "signature solving failed" in lowered or "challenge solver" in lowered or "only images are available" in lowered:
        return "YouTube 需要 JS challenge 解析。Control console 已配置 Node runtime；如果仍失败，请更新 yt-dlp[default] 后重试。"
    return clean


def music_file_snapshot():
    return {
        path.resolve()
        for path in MUSIC_DIR.rglob("*")
        if path.is_file()
    }


def imported_music_files(before):
    after = [
        path
        for path in MUSIC_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in MUSIC_EXTENSIONS and path.resolve() not in before
    ]
    after.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    tracks = list_music()
    files = []
    for path in after:
        rel = path.relative_to(MUSIC_DIR).as_posix()
        match = next((track for track in tracks if track["path"] == rel), None)
        if match:
            files.append(match)
    return files, tracks


def download_music_url_with_python_api(clean_url, use_browser_cookies=False):
    try:
        import yt_dlp
    except ImportError as error:
        raise RuntimeError("yt-dlp is not installed yet") from error

    output_template = str(MUSIC_DIR / "%(title).120B-%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "restrictfilenames": True,
        "noplaylist": True,
        "sleep_interval": 2,
        "max_sleep_interval": 5,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    ffmpeg_path = ffmpeg_location()
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path
    js_runtime = node_js_runtime_arg()
    if js_runtime:
        ydl_opts["js_runtimes"] = node_js_runtime_config()
    cookie_path = youtube_cookie_file()
    if cookie_path:
        ydl_opts["cookiefile"] = str(cookie_path)
    elif use_browser_cookies:
        ydl_opts["cookiesfrombrowser"] = ("edge", None, None, None)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([clean_url])


def download_music_url_with_command(clean_url, use_browser_cookies=False):
    downloader = yt_dlp_command()
    if not downloader:
        raise RuntimeError("yt-dlp is not installed yet")

    output_template = str(MUSIC_DIR / "%(title).120B-%(id)s.%(ext)s")
    command = downloader + [
        "--no-playlist",
        "--format",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "192",
        "--restrict-filenames",
        "--sleep-interval",
        "2",
        "--max-sleep-interval",
        "5",
        "--newline",
        "-o",
        output_template,
    ]
    cookie_path = youtube_cookie_file()
    if cookie_path:
        command.extend(["--cookies", str(cookie_path)])
    elif use_browser_cookies:
        command.extend(["--cookies-from-browser", "edge"])
    js_runtime = node_js_runtime_arg()
    if js_runtime:
        command.extend(["--js-runtimes", js_runtime])
    ffmpeg_path = ffmpeg_location()
    if ffmpeg_path:
        command.extend(["--ffmpeg-location", ffmpeg_path])
    command.append(clean_url)

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        **hidden_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip().splitlines()
        message = details[-1] if details else "yt-dlp could not import this link"
        raise RuntimeError(message)


def import_music_url(url, use_browser_cookies=False):
    clean_url = normalize_youtube_video_url(url)

    ensure_music_dir()
    before = music_file_snapshot()
    try:
        download_music_url_with_python_api(clean_url, use_browser_cookies)
    except RuntimeError:
        try:
            download_music_url_with_command(clean_url, use_browser_cookies)
        except Exception as error:
            raise ValueError(friendly_yt_dlp_error(str(error))) from error
    except Exception as error:
        raise ValueError(friendly_yt_dlp_error(str(error))) from error

    files, tracks = imported_music_files(before)

    return {
        "ok": True,
        "provider": music_url_provider(clean_url),
        "url": clean_url,
        "files": files,
        "tracks": tracks,
        "directory": str(MUSIC_DIR),
        "cookies": youtube_cookie_state(),
    }


def read_music_library_records():
    ensure_music_library_dir()
    try:
        payload = json.loads(MUSIC_LIBRARY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    records = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if item_id:
            records.append(item)
    return records


def write_music_library_records(records):
    ensure_music_library_dir()
    MUSIC_LIBRARY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def music_track_from_path(path):
    stat = path.stat()
    rel = path.relative_to(MUSIC_DIR).as_posix()
    return {
        "name": display_music_name(path.stem),
        "path": rel,
        "url": "/music/" + urllib.parse.quote(rel),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "type": path.suffix.lower().lstrip("."),
    }


def library_tracks_for_record(record, hide_local_duplicates=True):
    clean = str(record.get("path") or "").replace("\\", "/").lstrip("/")
    if not clean:
        return []
    library_dir = (MUSIC_DIR / clean).resolve()
    if not is_path_inside(library_dir, MUSIC_DIR) or not library_dir.exists():
        return []
    local_keys = local_music_name_keys() if hide_local_duplicates else set()
    tracks = []
    for path in library_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MUSIC_EXTENSIONS:
            continue
        if hide_local_duplicates:
            key = music_path_name_key(path)
            if key and key in local_keys:
                continue
        try:
            tracks.append(music_track_from_path(path))
        except OSError:
            continue
    tracks.sort(key=lambda item: item["path"])
    return tracks


def prune_duplicate_library_files(library_dir):
    library_dir = Path(library_dir).resolve()
    if not is_path_inside(library_dir, MUSIC_LIBRARY_DIR) or not library_dir.exists():
        return 0

    local_keys = local_music_name_keys()
    removed = 0
    for path in library_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MUSIC_EXTENSIONS:
            continue
        key = music_path_name_key(path)
        if not key or key not in local_keys:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def public_music_library_record(record):
    public = dict(record)
    tracks = library_tracks_for_record(record)
    public["count"] = len(tracks)
    public["tracks"] = tracks
    return public


def list_music_libraries():
    with MUSIC_LIBRARY_LOCK:
        records = read_music_library_records()
    libraries = [public_music_library_record(record) for record in records]
    libraries.sort(key=lambda item: item.get("updatedAt") or item.get("createdAt") or "", reverse=True)
    return libraries


def save_music_library_record(record):
    with MUSIC_LIBRARY_LOCK:
        records = read_music_library_records()
        next_records = []
        replaced = False
        for item in records:
            if item.get("id") == record.get("id"):
                next_records.append(record)
                replaced = True
            else:
                next_records.append(item)
        if not replaced:
            next_records.append(record)
        write_music_library_records(next_records)


def update_music_library_record(library_id, **fields):
    with MUSIC_LIBRARY_LOCK:
        records = read_music_library_records()
        updated = None
        for item in records:
            if item.get("id") == library_id:
                item.update(fields)
                item["updatedAt"] = datetime.now(timezone.utc).isoformat()
                updated = item
                break
        if updated:
            write_music_library_records(records)
        return updated


def existing_music_library_for_url(clean_url):
    normalized = normalize_youtube_playlist_url(clean_url)
    for record in read_music_library_records():
        if normalize_youtube_playlist_url(record.get("url") or "") == normalized:
            return record
    return None


def unique_music_library_id(name):
    ensure_music_library_dir()
    base = slugify_english_name(name, "music-library")
    existing = {record.get("id") for record in read_music_library_records()}
    candidate = base
    index = 2
    while candidate in existing or (MUSIC_LIBRARY_DIR / candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def fetch_music_library_metadata(downloader, clean_url):
    command = downloader + [
        "--dump-single-json",
        "--flat-playlist",
        "--no-warnings",
    ]
    cookie_path = youtube_cookie_file()
    if cookie_path:
        command.extend(["--cookies", str(cookie_path)])
    js_runtime = node_js_runtime_arg()
    if js_runtime:
        command.extend(["--js-runtimes", js_runtime])
    command.append(clean_url)
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        **hidden_subprocess_kwargs(),
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return {}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def music_library_entry_url(entry):
    if not isinstance(entry, dict):
        return ""
    for key in ("webpage_url", "original_url"):
        value = str(entry.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    value = str(entry.get("url") or entry.get("id") or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return f"https://www.youtube.com/watch?v={urllib.parse.quote(value, safe='')}"


def download_music_library_entry(downloader, library_dir, archive_file, index, entry_url):
    output_template = str(library_dir / f"{index:03d}-%(title).120B-%(id)s.%(ext)s")
    command = downloader + [
        "--no-playlist",
        "--ignore-errors",
        "--no-abort-on-error",
        "--format",
        "bestaudio/best",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--restrict-filenames",
        "--download-archive",
        archive_file,
        "--newline",
        "-o",
        output_template,
    ]
    cookie_path = youtube_cookie_file()
    if cookie_path:
        command.extend(["--cookies", str(cookie_path)])
    js_runtime = node_js_runtime_arg()
    if js_runtime:
        command.extend(["--js-runtimes", js_runtime])
    ffmpeg_path = ffmpeg_location()
    if ffmpeg_path:
        command.extend(["--ffmpeg-location", ffmpeg_path])
    command.append(entry_url)
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
        **hidden_subprocess_kwargs(),
    )


def run_music_library_import(library_id, clean_url, requested_name=""):
    downloader = yt_dlp_command()
    if not downloader:
        update_music_library_record(library_id, status="failed", message="yt-dlp is not installed yet")
        return

    record = update_music_library_record(library_id, status="grabbing", message="", finishedAt="")
    if not record:
        return

    library_dir = (MUSIC_DIR / record["path"]).resolve()
    library_dir.mkdir(parents=True, exist_ok=True)

    metadata = fetch_music_library_metadata(downloader, clean_url)
    title = str(requested_name or metadata.get("title") or record.get("name") or "Library").strip()
    entries = metadata.get("entries") if isinstance(metadata.get("entries"), list) else []
    expected = len(entries)
    update_music_library_record(
        library_id,
        name=title,
        expected=expected,
        status="grabbing",
        message=f"Found {expected} playlist entries." if expected else "",
    )

    archive_file = str(library_dir / ".downloaded.txt")
    source_entries = entries or [{"webpage_url": clean_url}]
    failures = []
    skipped = 0
    removed_duplicates = prune_duplicate_library_files(library_dir)
    for index, entry in enumerate(source_entries, start=1):
        entry_url = music_library_entry_url(entry)
        if not entry_url:
            skipped += 1
            continue
        completed = download_music_library_entry(downloader, library_dir, archive_file, index, entry_url)
        removed_duplicates += prune_duplicate_library_files(library_dir)
        tracks = library_tracks_for_record({"path": record["path"]})
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip().splitlines()
            if details:
                failures.append(details[-1])
        update_music_library_record(
            library_id,
            status="grabbing",
            message=f"Imported {len(tracks)}/{expected or len(source_entries)} tracks.",
            count=len(tracks),
            expected=expected,
        )

    tracks = library_tracks_for_record({"path": record["path"]})
    status = "ready" if tracks or removed_duplicates else "failed"
    message = f"Imported {len(tracks)}/{expected or len(source_entries)} tracks."
    if skipped:
        message += f" Skipped {skipped} entries without URLs."
    if failures:
        message += f" Skipped {len(failures)} unavailable entries."
    if removed_duplicates:
        message += f" Removed {removed_duplicates} local duplicates from Library."
    if not tracks and removed_duplicates and not failures:
        message = f"All imported tracks already exist locally. Removed {removed_duplicates} Library duplicates."
    elif not tracks and failures:
        message = failures[-1]
    elif not tracks:
        message = "yt-dlp could not import this playlist"
    message = friendly_yt_dlp_error(message)
    update_music_library_record(
        library_id,
        status=status,
        message=message,
        count=len(tracks),
        expected=expected,
        finishedAt=datetime.now(timezone.utc).isoformat(),
    )


def import_music_library(url, name=""):
    clean_url = normalize_youtube_playlist_url(validate_music_url(url))
    ensure_music_library_dir()
    requested_name = str(name or "").strip() or "Library"
    provider = music_url_provider(clean_url)
    now = datetime.now(timezone.utc).isoformat()
    already_running = None

    with MUSIC_LIBRARY_LOCK:
        existing = existing_music_library_for_url(clean_url)
        if existing and existing.get("status") in {"queued", "grabbing"}:
            already_running = dict(existing)
        else:
            if existing:
                library_id = existing["id"]
                rel_path = existing.get("path") or f"libraries/{library_id}"
                record = {
                    **existing,
                    "name": requested_name or existing.get("name") or "Library",
                    "url": clean_url,
                    "provider": provider,
                    "path": rel_path,
                    "status": "queued",
                    "message": "",
                    "updatedAt": now,
                }
            else:
                library_id = unique_music_library_id(requested_name)
                record = {
                    "id": library_id,
                    "name": requested_name,
                    "url": clean_url,
                    "provider": provider,
                    "path": f"libraries/{library_id}",
                    "status": "queued",
                    "message": "",
                    "expected": 0,
                    "count": 0,
                    "createdAt": now,
                    "updatedAt": now,
                }
            records = [item for item in read_music_library_records() if item.get("id") != library_id]
            records.append(record)
            write_music_library_records(records)

    if already_running:
        return {
            "ok": True,
            "library": public_music_library_record(already_running),
            "libraries": list_music_libraries(),
            "tracks": list_music(),
        }

    thread = threading.Thread(
        target=run_music_library_import,
        args=(library_id, clean_url, requested_name),
        daemon=True,
    )
    thread.start()

    return {
        "ok": True,
        "library": public_music_library_record(record),
        "libraries": list_music_libraries(),
        "tracks": list_music(),
    }


def ensure_builder_texture_dir():
    BUILDER_TEXTURE_DIR.mkdir(parents=True, exist_ok=True)


def material_source_path_from_relative(relative_path):
    clean = str(relative_path or "").replace("\\", "/").lstrip("/")
    if not clean:
        raise ValueError("material path is required")
    candidate = (MATERIAL_SOURCE_DIR / clean).resolve()
    if not is_path_inside(candidate, MATERIAL_SOURCE_DIR):
        raise ValueError("material path is outside the source folder")
    if not candidate.exists() or not candidate.is_file() or candidate.suffix.lower() not in MATERIAL_CANDIDATE_EXTENSIONS:
        raise ValueError("material file was not found")
    return candidate


def slugify_english_name(value, fallback="item"):
    text = str(value or "")
    text = text.replace("&", " and ")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:80] or fallback


def safe_material_name(path):
    name = path.name
    if name.lower().endswith(".zip"):
        name = name[:-4]
    if name.lower().endswith(".blend"):
        name = name[:-6]
    return slugify_english_name(Path(name).stem, "material")


def unique_directory(root, name):
    candidate = (root / name).resolve()
    index = 2
    while candidate.exists():
        candidate = (root / f"{name}-{index}").resolve()
        index += 1
    if not is_path_inside(candidate, root):
        raise ValueError("target path is outside the texture folder")
    return candidate


def unique_file_path(root, filename):
    raw_name = Path(str(filename or "")).name
    suffix = Path(raw_name).suffix.lower()
    stem = slugify_english_name(Path(raw_name).stem, "texture")
    candidate = (root / f"{stem}{suffix}").resolve()
    index = 2
    while candidate.exists():
        candidate = (root / f"{stem}-{index}{suffix}").resolve()
        index += 1
    if not is_path_inside(candidate, root):
        raise ValueError("target file is outside the texture folder")
    return candidate


def list_material_candidates(limit=24):
    if not MATERIAL_SOURCE_DIR.exists():
        return []

    items = []
    for path in MATERIAL_SOURCE_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MATERIAL_CANDIDATE_EXTENSIONS:
            continue
        try:
            stat = path.stat()
            rel = path.relative_to(MATERIAL_SOURCE_DIR).as_posix()
        except OSError:
            continue
        items.append({
            "name": path.name,
            "path": rel,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "type": "package" if path.suffix.lower() in MATERIAL_PACKAGE_EXTENSIONS else "texture",
        })

    items.sort(key=lambda item: item["modified"], reverse=True)
    return items[:limit]


def copy_texture_file(source, destination_dir):
    target = unique_file_path(destination_dir, source.name)
    shutil.copy2(source, target)
    return target


def import_material_candidate(relative_path):
    source = material_source_path_from_relative(relative_path)
    ensure_builder_texture_dir()

    destination = unique_directory(BUILDER_TEXTURE_DIR, safe_material_name(source))
    destination.mkdir(parents=True, exist_ok=False)
    copied = []

    if source.suffix.lower() in MATERIAL_PACKAGE_EXTENSIONS:
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member_name = Path(info.filename.replace("\\", "/")).name
                if Path(member_name).suffix.lower() not in MATERIAL_TEXTURE_EXTENSIONS:
                    continue
                target = unique_file_path(destination, member_name)
                with archive.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                copied.append(target)
    else:
        copied.append(copy_texture_file(source, destination))

    if not copied:
        shutil.rmtree(destination, ignore_errors=True)
        raise ValueError("no texture files were found in the selected material")

    return {
        "ok": True,
        "source": str(source),
        "destination": str(destination),
        "files": [
            {
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
            }
            for path in copied
        ],
        "candidates": list_material_candidates(),
    }


def render_texture_upload_folder_name(files):
    valid_names = [
        str(item.get("filename", ""))
        for item in files
        if Path(str(item.get("filename", ""))).suffix.lower() in MATERIAL_CANDIDATE_EXTENSIONS
    ]
    if len(valid_names) == 1:
        name = Path(valid_names[0]).name
        if name.lower().endswith(".zip"):
            name = name[:-4]
        if name.lower().endswith(".blend"):
            name = name[:-6]
        return slugify_english_name(Path(name).stem, "render-textures")
    return "render-textures-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def import_render_textures_upload(files):
    if not files:
        raise ValueError("no files were uploaded")

    ensure_builder_texture_dir()
    destination = unique_directory(BUILDER_TEXTURE_DIR, render_texture_upload_folder_name(files))
    destination.mkdir(parents=True, exist_ok=False)
    copied = []

    try:
        for item in files:
            filename = str(item.get("filename", ""))
            data = item.get("data", b"")
            suffix = Path(filename).suffix.lower()
            if not filename or not data:
                continue

            if suffix in MATERIAL_TEXTURE_EXTENSIONS:
                target = unique_file_path(destination, filename)
                target.write_bytes(data)
                copied.append(target)
                continue

            if suffix in MATERIAL_PACKAGE_EXTENSIONS:
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        for info in archive.infolist():
                            if info.is_dir():
                                continue
                            member_name = Path(info.filename.replace("\\", "/")).name
                            if Path(member_name).suffix.lower() not in MATERIAL_TEXTURE_EXTENSIONS:
                                continue
                            target = unique_file_path(destination, member_name)
                            with archive.open(info) as src, target.open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                            copied.append(target)
                except zipfile.BadZipFile as error:
                    raise ValueError(f"{filename} is not a valid zip file") from error

        if not copied:
            raise ValueError("no texture files were found")

        return {
            "ok": True,
            "folder": destination.name,
            "destination": str(destination),
            "target": str(BUILDER_TEXTURE_DIR),
            "files": [
                {
                    "name": path.name,
                    "path": str(path),
                    "size": path.stat().st_size,
                }
                for path in copied
            ],
            "candidates": list_material_candidates(),
        }
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def steamwork_upload_target(target_key):
    targets = {
        "gameContent": ("GameContent", STEAMWORK_GAMECONTENT_DIR),
        "publishTool": ("Publish Tool", STEAMWORK_PUBLISH_TOOL_DIR),
    }
    target = targets.get(str(target_key or ""))
    if not target:
        raise ValueError("unknown Steamwork import target")
    return target


def unique_steamwork_file_path(root, filename):
    raw_name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(raw_name).suffix.lower()
    stem = slugify_english_name(Path(raw_name).stem, "steamwork-file")
    candidate = (root / f"{stem}{suffix}").resolve()
    index = 2
    while candidate.exists():
        candidate = (root / f"{stem}-{index}{suffix}").resolve()
        index += 1
    if not is_path_inside(candidate, root):
        raise ValueError("target file is outside the Steamwork folder")
    return candidate


def import_steamwork_files(target_key, files):
    if not files:
        raise ValueError("no files were uploaded")

    target_name, root = steamwork_upload_target(target_key)
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Steamwork target folder was not found: {root}")
    copied = []

    for item in files:
        filename = str(item.get("filename", ""))
        data = item.get("data", b"")
        if not filename or not data:
            continue
        target = unique_steamwork_file_path(root, filename)
        target.write_bytes(data)
        copied.append(target)

    if not copied:
        raise ValueError("no files were imported")

    return {
        "ok": True,
        "target": target_key,
        "targetName": target_name,
        "destination": str(root),
        "files": [
            {
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
            }
            for path in copied
        ],
    }


STEAMWORK_ASSET_REQUIREMENTS = [
    {
        "id": "header_capsule",
        "category": "Store",
        "name": "Header Capsule",
        "required": True,
        "spec": "920 x 430",
        "target": "Store Page Admin > Graphical Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 920,
        "height": 430,
        "patterns": ["header capsule", "header", "capsule", "920x430"],
    },
    {
        "id": "small_capsule",
        "category": "Store",
        "name": "Small Capsule",
        "required": True,
        "spec": "462 x 174",
        "target": "Store Page Admin > Graphical Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 462,
        "height": 174,
        "patterns": ["small capsule", "small", "462x174"],
    },
    {
        "id": "main_capsule",
        "category": "Store",
        "name": "Main Capsule",
        "required": True,
        "spec": "1232 x 706",
        "target": "Store Page Admin > Graphical Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 1232,
        "height": 706,
        "patterns": ["main capsule", "main", "1232x706"],
    },
    {
        "id": "vertical_capsule",
        "category": "Store",
        "name": "Vertical Capsule",
        "required": True,
        "spec": "748 x 896",
        "target": "Store Page Admin > Graphical Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 748,
        "height": 896,
        "patterns": ["vertical capsule", "vertical", "hero capsule", "748x896"],
    },
    {
        "id": "screenshots",
        "category": "Store",
        "name": "Screenshots",
        "required": True,
        "spec": "5+ files, 1920 x 1080 minimum, 16:9",
        "target": "Store Page Admin > Screenshots",
        "kind": "image-set",
        "dimensionMode": "min16x9",
        "minWidth": 1920,
        "minHeight": 1080,
        "minCount": 5,
        "multiple": True,
        "rootHint": "screenshots",
        "patterns": ["screenshot", "screen"],
    },
    {
        "id": "page_background",
        "category": "Store",
        "name": "Page Background",
        "required": False,
        "spec": "1438 x 810",
        "target": "Store Page Admin > Graphical Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 1438,
        "height": 810,
        "patterns": ["page background", "background", "1438x810"],
    },
    {
        "id": "shortcut_icon",
        "category": "Community",
        "name": "Shortcut Icon",
        "required": True,
        "spec": "256 x 256 or 512 x 512, ICO/PNG",
        "target": "Store Page Admin > Community & Client Icons",
        "kind": "image",
        "dimensionMode": "shortcutIcon",
        "patterns": ["256.ico", "shortcut", "icon", "logo256"],
    },
    {
        "id": "app_icon",
        "category": "Community",
        "name": "App Icon",
        "required": True,
        "spec": "184 x 184 JPG",
        "target": "Store Page Admin > Community & Client Icons",
        "kind": "image",
        "dimensionMode": "appIcon",
        "width": 184,
        "height": 184,
        "patterns": ["app icon", "app", "184"],
    },
    {
        "id": "library_capsule",
        "category": "Library",
        "name": "Library Capsule",
        "required": True,
        "spec": "600 x 900",
        "target": "Steamworks > Edit Library Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 600,
        "height": 900,
        "patterns": ["600x900", "library capsule", "lib", "capsule"],
    },
    {
        "id": "library_header",
        "category": "Library",
        "name": "Library Header",
        "required": True,
        "spec": "920 x 430",
        "target": "Steamworks > Edit Library Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 920,
        "height": 430,
        "patterns": ["library header", "header", "capsule", "920x430"],
    },
    {
        "id": "library_hero",
        "category": "Library",
        "name": "Library Hero",
        "required": True,
        "spec": "3840 x 1240 PNG",
        "target": "Steamworks > Edit Library Assets",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 3840,
        "height": 1240,
        "patterns": ["3840x1240", "hero"],
    },
    {
        "id": "library_logo",
        "category": "Library",
        "name": "Library Logo",
        "required": True,
        "spec": "PNG, 1280 wide and/or 720 tall",
        "target": "Steamworks > Edit Library Assets",
        "kind": "image",
        "dimensionMode": "libraryLogo",
        "patterns": ["1280x720", "library logo", "logo", "icon1280"],
    },
    {
        "id": "trailer",
        "category": "Video",
        "name": "Trailer",
        "required": True,
        "spec": "MP4/MOV/WMV, up to 1920 x 1080, 30/60 fps",
        "target": "Store Page Admin > Trailers",
        "kind": "video",
        "dimensionMode": "video",
        "patterns": ["demo", "trailer", "video", "vedio"],
    },
    {
        "id": "trailer_poster",
        "category": "Video",
        "name": "Custom Trailer Poster",
        "required": False,
        "spec": "1920 x 1080 JPG/PNG, frame from the video",
        "target": "Store Page Admin > Trailers",
        "kind": "image",
        "dimensionMode": "exact",
        "width": 1920,
        "height": 1080,
        "candidateRootHint": "screenshots",
        "candidatePatterns": ["screenshot", "screen"],
        "patterns": ["poster", "thumbnail", "trailer", "1920x1080"],
    },
]


def steamwork_scan_roots():
    primary_candidates = [
        ("store", STEAMWORK_STORE_ASSET_DIR),
        ("screenshots", STEAMWORK_SCREENSHOT_DIR),
        ("video", STEAMWORK_VIDEO_DIR),
    ]
    roots = []
    seen = set()
    for label, path in primary_candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.exists() or not resolved.is_dir() or resolved in seen:
            continue
        if STEAMWORK_ASSET_DIR.exists() and not is_path_inside(resolved, STEAMWORK_ASSET_DIR):
            continue
        roots.append((label, resolved))
        seen.add(resolved)
    if roots:
        return roots
    try:
        root = STEAMWORK_ASSET_DIR.resolve()
    except OSError:
        return roots
    if root.exists() and root.is_dir():
        roots.append(("root", root))
    return roots


def steamwork_asset_path_from_relative(relative_path):
    clean = str(relative_path or "").replace("\\", "/").lstrip("/")
    if not clean:
        raise ValueError("Steamwork asset path is required")
    root = STEAMWORK_ASSET_DIR.resolve()
    candidate = (root / clean).resolve()
    if not is_path_inside(candidate, root):
        raise ValueError("Steamwork asset path is outside the asset folder")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError("Steamwork asset file was not found")
    return candidate


def steamwork_asset_preview_path(relative_path):
    target = steamwork_asset_path_from_relative(relative_path)
    if target.suffix.lower() not in PREVIEWABLE_TEXTURE_EXTENSIONS | {".ico"}:
        raise ValueError("preview is available for image assets only")
    return target


def steamwork_asset_thumbnail_path(relative_path, max_size=(360, 240)):
    source = steamwork_asset_preview_path(relative_path)
    try:
        stat = source.stat()
    except OSError as error:
        raise ValueError("Steamwork asset file was not found") from error

    cache_key = hashlib.sha256(
        f"{source.relative_to(STEAMWORK_ASSET_DIR.resolve()).as_posix()}|{stat.st_mtime_ns}|{stat.st_size}|{max_size[0]}x{max_size[1]}".encode("utf-8")
    ).hexdigest()[:24]
    target = STEAMWORK_THUMB_DIR / f"{cache_key}.jpg"
    if target.exists():
        return target

    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise ValueError("thumbnail generation requires Pillow") from error

    try:
        STEAMWORK_THUMB_DIR.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "L"}:
                background = Image.new("RGB", image.size, (36, 48, 63))
                alpha = image.getchannel("A") if "A" in image.getbands() else None
                background.paste(image.convert("RGBA"), mask=alpha)
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            image.save(target, format="JPEG", quality=78, optimize=True, progressive=True)
    except OSError as error:
        raise ValueError(f"could not generate Steamwork thumbnail: {error}") from error
    return target


def open_steamwork_asset(relative_path):
    return open_file_resource(steamwork_asset_path_from_relative(relative_path))


def steamwork_requirement_by_id(requirement_id):
    clean_id = str(requirement_id or "").strip()
    for requirement in STEAMWORK_ASSET_REQUIREMENTS:
        if requirement.get("id") == clean_id:
            return requirement
    raise ValueError("unknown Steamwork asset slot")


def steamwork_stage_folder(requirement):
    requirement_id = requirement.get("id", "")
    if requirement_id == "screenshots":
        return STEAMWORK_SCREENSHOT_DIR
    if requirement.get("kind") == "video":
        return STEAMWORK_VIDEO_DIR
    return STEAMWORK_STORE_ASSET_DIR


def steamwork_allowed_stage_extensions(requirement):
    if requirement.get("kind") == "video":
        return STEAMWORK_VIDEO_EXTENSIONS
    return STEAMWORK_IMAGE_EXTENSIONS | {".psd"}


def safe_steamwork_stage_filename(requirement, filename):
    raw_name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(raw_name).suffix.lower()
    if suffix not in steamwork_allowed_stage_extensions(requirement):
        raise ValueError("file type does not match this Steamwork asset slot")

    stem = Path(raw_name).stem.strip()
    stem = re.sub(r"[^\w .()\-]+", "-", stem, flags=re.UNICODE).strip(" .-_")
    if not stem:
        stem = "asset"
    prefix = slugify_english_name(requirement.get("name", requirement.get("id", "")), "steamwork-asset")
    if not stem.lower().startswith(prefix.lower()):
        stem = f"{prefix} - {stem}"
    return f"{stem[:120]}{suffix}"


def unique_steamwork_stage_path(root, filename):
    safe_name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(safe_name).suffix.lower()
    stem = Path(safe_name).stem
    candidate = (root / safe_name).resolve()
    index = 2
    while candidate.exists():
        candidate = (root / f"{stem}-{index}{suffix}").resolve()
        index += 1
    if not is_path_inside(candidate, root):
        raise ValueError("target file is outside the Steamwork asset folder")
    return candidate


def stage_steamwork_asset_files(requirement_id, files):
    if not files:
        raise ValueError("no files were uploaded")

    requirement = steamwork_requirement_by_id(requirement_id)
    root = steamwork_stage_folder(requirement).resolve()
    if STEAMWORK_ASSET_DIR.exists() and not is_path_inside(root, STEAMWORK_ASSET_DIR):
        raise ValueError("Steamwork asset target is outside the asset folder")
    root.mkdir(parents=True, exist_ok=True)

    saved = []
    for item in files:
        filename = str(item.get("filename", ""))
        data = item.get("data", b"")
        if not filename or not data:
            continue
        safe_name = safe_steamwork_stage_filename(requirement, filename)
        target = unique_steamwork_stage_path(root, safe_name)
        target.write_bytes(data)
        record = steamwork_asset_file_record(target, "staged")
        if record:
            saved.append(record)

    if not saved:
        raise ValueError("no files were staged")

    state = steamwork_assets_state()
    return {
        "ok": True,
        "slot": requirement.get("id"),
        "destination": str(root),
        "files": saved,
        "state": state,
    }


def steamwork_asset_file_record(path, root_label):
    try:
        stat = path.stat()
        rel = path.relative_to(STEAMWORK_ASSET_DIR.resolve()).as_posix()
    except (OSError, ValueError):
        return None

    suffix = path.suffix.lower()
    dimensions = texture_file_dimensions(path) if suffix in PREVIEWABLE_TEXTURE_EXTENSIONS else None
    record = {
        "name": path.name,
        "path": rel,
        "folder": root_label,
        "extension": suffix,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "type": "video" if suffix in STEAMWORK_VIDEO_EXTENSIONS else "image",
        "preview": suffix in PREVIEWABLE_TEXTURE_EXTENSIONS | {".ico"},
    }
    if dimensions:
        record["width"] = dimensions.get("width")
        record["height"] = dimensions.get("height")
    return record


def list_steamwork_asset_files(limit=500):
    files = []
    seen = set()
    for root_label, root in steamwork_scan_roots():
        for path in root.rglob("*"):
            if len(files) >= limit:
                break
            if not path.is_file() or path.suffix.lower() not in STEAMWORK_ASSET_EXTENSIONS:
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            record = steamwork_asset_file_record(resolved, root_label)
            if record:
                files.append(record)
                seen.add(resolved)
    files.sort(key=lambda item: item.get("modified", ""), reverse=True)
    return files


def steamwork_asset_dimensions_ok(requirement, file_record):
    mode = requirement.get("dimensionMode", "")
    suffix = file_record.get("extension", "")
    width = int(file_record.get("width") or 0)
    height = int(file_record.get("height") or 0)

    if mode == "video":
        return suffix in STEAMWORK_VIDEO_EXTENSIONS
    if mode == "exact":
        return width == int(requirement.get("width") or 0) and height == int(requirement.get("height") or 0)
    if mode == "min16x9":
        if width <= 0 or height <= 0:
            return False
        ratio = width / height
        return width >= int(requirement.get("minWidth") or 0) and height >= int(requirement.get("minHeight") or 0) and abs(ratio - (16 / 9)) < 0.04
    if mode == "shortcutIcon":
        if suffix == ".ico":
            return True
        return suffix == ".png" and (width, height) in {(256, 256), (512, 512)}
    if mode == "appIcon":
        return suffix in {".jpg", ".jpeg"} and width == 184 and height == 184
    if mode == "libraryLogo":
        return suffix == ".png" and (width == 1280 or height == 720)
    return False


def steamwork_asset_match_score(requirement, file_record):
    suffix = file_record.get("extension", "")
    kind = requirement.get("kind", "")
    if kind == "video" and suffix not in STEAMWORK_VIDEO_EXTENSIONS:
        return -1
    if kind != "video" and suffix not in STEAMWORK_IMAGE_EXTENSIONS:
        return -1

    haystack = f"{file_record.get('name', '')} {file_record.get('path', '')}".replace("_", " ").replace("-", " ").lower()
    score = 0
    has_match_signal = False
    if steamwork_asset_dimensions_ok(requirement, file_record):
        score += 120
        has_match_signal = True
    if file_record.get("folder") == "staged":
        score += 90
        has_match_signal = True
    if requirement.get("rootHint") and file_record.get("folder") == requirement.get("rootHint"):
        score += 80
        has_match_signal = True
    if file_record.get("folder") == "store" and requirement.get("category") in {"Store", "Library", "Community"}:
        score += 20
    if file_record.get("folder") == "video" and requirement.get("category") == "Video":
        score += 80
        has_match_signal = True

    for pattern in requirement.get("patterns", []):
        clean_pattern = str(pattern).replace("_", " ").replace("-", " ").lower()
        if clean_pattern and clean_pattern in haystack:
            score += 35 if len(clean_pattern) > 4 else 15
            has_match_signal = True

    return score if has_match_signal else -1


def steamwork_asset_reference_score(requirement, file_record):
    suffix = file_record.get("extension", "")
    kind = requirement.get("kind", "")
    if kind == "video":
        return 100 if suffix in STEAMWORK_VIDEO_EXTENSIONS else -1
    if suffix not in STEAMWORK_IMAGE_EXTENSIONS | {".ico"}:
        return -1

    score = 300 if steamwork_asset_dimensions_ok(requirement, file_record) else 0
    if file_record.get("folder") == "staged":
        score += 80
    candidate_root = requirement.get("candidateRootHint") or requirement.get("rootHint")
    if candidate_root and file_record.get("folder") == candidate_root:
        score += 140
    if requirement.get("category") in {"Store", "Library", "Community", "Video"} and file_record.get("folder") in {"store", "root", "staged"}:
        score += 18

    width = int(file_record.get("width") or 0)
    height = int(file_record.get("height") or 0)
    target_width = int(requirement.get("width") or requirement.get("minWidth") or 0)
    target_height = int(requirement.get("height") or requirement.get("minHeight") or 0)
    if width > 0 and height > 0 and target_width > 0 and target_height > 0:
        ratio = width / height
        target_ratio = target_width / target_height
        ratio_delta = abs(math.log(ratio / target_ratio))
        area_delta = abs(math.log((width * height) / (target_width * target_height)))
        score += max(0, 110 - ratio_delta * 180)
        score += max(0, 75 - area_delta * 28)
        if (width >= height) == (target_width >= target_height):
            score += 18
        if width < target_width * 0.25 or height < target_height * 0.25:
            score -= 80
        if abs(ratio - 1) < 0.04 and abs(target_ratio - 1) > 0.2:
            score -= 70

    haystack = f"{file_record.get('name', '')} {file_record.get('path', '')}".replace("_", " ").replace("-", " ").lower()
    if requirement.get("id") == "trailer_poster":
        if suffix == ".ico" or re.search(r"\b(icon|logo)\b", haystack):
            score -= 140
    for pattern in [*requirement.get("patterns", []), *requirement.get("candidatePatterns", [])]:
        clean_pattern = str(pattern).replace("_", " ").replace("-", " ").lower()
        if clean_pattern and clean_pattern in haystack:
            score += 45 if len(clean_pattern) > 4 else 18
    return score


def steamwork_requirement_matches(requirement, files):
    scored = []
    for file_record in files:
        score = steamwork_asset_match_score(requirement, file_record)
        if score <= 0:
            continue
        scored.append((score, file_record))
    scored.sort(key=lambda item: (item[0], item[1].get("modified", "")), reverse=True)
    if requirement.get("multiple"):
        return [item[1] for item in scored[:24]]
    return [scored[0][1]] if scored else []


def steamwork_requirement_candidate_files(requirement, files, matches):
    matched_paths = {item.get("path") for item in matches if item.get("path")}
    category = requirement.get("category")
    kind = requirement.get("kind")
    candidates = []
    for file_record in files:
        suffix = file_record.get("extension", "")
        if file_record.get("path") in matched_paths:
            continue
        score = steamwork_asset_match_score(requirement, file_record)
        if score <= 0:
            score = steamwork_asset_reference_score(requirement, file_record)
            if score < 0:
                continue
        if kind == "video":
            if suffix not in STEAMWORK_VIDEO_EXTENSIONS or file_record.get("folder") != "video":
                continue
        else:
            if suffix not in STEAMWORK_IMAGE_EXTENSIONS | {".psd"}:
                continue
            if requirement.get("id") == "screenshots":
                if file_record.get("folder") != "screenshots":
                    continue
            elif requirement.get("id") == "trailer_poster":
                if file_record.get("folder") not in {"screenshots", "store", "root", "staged"}:
                    continue
            elif category in {"Store", "Library", "Community", "Video"}:
                if file_record.get("folder") not in {"store", "root", "staged"}:
                    continue
        candidates.append((score, file_record))

    candidates.sort(key=lambda item: (item[0], item[1].get("modified", "")), reverse=True)
    return [item[1] for item in candidates[:18]]


def steamwork_requirement_state(requirement, files):
    matches = steamwork_requirement_matches(requirement, files)
    min_count = int(requirement.get("minCount") or 1)
    required = bool(requirement.get("required"))
    enough_matches = len(matches) >= min_count

    if not matches:
        status = "missing" if required else "optional"
        issue = "Missing required asset" if required else "Optional"
    elif not enough_matches:
        status = "missing" if required else "review"
        issue = f"Need {min_count} files"
    else:
        valid_count = sum(1 for item in matches if steamwork_asset_dimensions_ok(requirement, item))
        if valid_count >= min_count:
            status = "ready"
            issue = ""
        else:
            status = "review"
            issue = "File found, check size/format"

    return {
        **requirement,
        "status": status,
        "issue": issue,
        "files": matches,
        "candidates": steamwork_requirement_candidate_files(requirement, files, matches),
    }


def steamwork_assets_state():
    files = list_steamwork_asset_files()
    items = [steamwork_requirement_state(requirement, files) for requirement in STEAMWORK_ASSET_REQUIREMENTS]
    summary = {
        "total": len(items),
        "ready": sum(1 for item in items if item["status"] == "ready"),
        "review": sum(1 for item in items if item["status"] == "review"),
        "missing": sum(1 for item in items if item["status"] == "missing"),
        "optional": sum(1 for item in items if item["status"] == "optional"),
        "files": len(files),
    }
    return {
        "ok": True,
        "root": str(STEAMWORK_ASSET_DIR),
        "storeAssets": str(STEAMWORK_STORE_ASSET_DIR),
        "screenshots": str(STEAMWORK_SCREENSHOT_DIR),
        "videos": str(STEAMWORK_VIDEO_DIR),
        "thumbs": True,
        "items": items,
        "files": files,
        "summary": summary,
    }


def start_hotkey_listener():
    if sys.platform != "win32":
        raise ValueError("Alt+C hotkey listener is only available on Windows")
    if not HOTKEY_LAUNCHER.exists():
        raise ValueError("hotkey launcher is missing")
    subprocess.Popen(
        ["wscript.exe", str(HOTKEY_LAUNCHER)],
        cwd=str(APP_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **hidden_subprocess_kwargs(),
    )
    return {"ok": True}


def startup_folder():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not available")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_startup_listener():
    if sys.platform != "win32":
        raise ValueError("startup install is only available on Windows")
    if not HOTKEY_LAUNCHER.exists():
        raise ValueError("hotkey launcher is missing")
    folder = startup_folder()
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / STARTUP_SCRIPT_NAME
    launcher = str(HOTKEY_LAUNCHER).replace('"', '""')
    script.write_text(
        'Option Explicit\n'
        'Dim shell\n'
        'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.Run "wscript.exe ""{launcher}""", 0, False\n',
        encoding="utf-8",
    )
    start_hotkey_listener()
    return {"ok": True, "path": str(script)}


def fetch_url(url, timeout=6):
    request = urllib.request.Request(url, headers={"User-Agent": "CodexWorldConsole/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def strip_markup(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def direct_event_title(title):
    cleaned = re.sub(r"\s+", " ", title or "").strip()
    cleaned = re.sub(r"^(analysis|comment|commentary|explainer|opinion)\s*:\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^[^:]{1,56}\blive\s*:\s*", "", cleaned, flags=re.I)
    cleaned = cleaned.rstrip(" ?")
    return cleaned[:180]


def parse_datetime(value):
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return datetime.now(timezone.utc).isoformat()


def event_datetime(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (AttributeError, ValueError):
        return datetime.now(timezone.utc)


def event_window_days(event):
    severity = int(event.get("severity") or 1)
    if severity >= 5:
        return 21
    if severity >= 4:
        return 7
    return 3


def event_is_recent_enough(event, now):
    published = event_datetime(event.get("published"))
    return published >= now - timedelta(days=event_window_days(event))


def classify_event(text):
    lowered = text.lower()
    if any(word in lowered for word in ["summit", "talks", "meeting", "diplomacy", "president", "minister"]):
        return "diplomacy"
    if any(word in lowered for word in ["war", "strike", "missile", "conflict", "military"]):
        return "security"
    if any(word in lowered for word in ["election", "vote", "parliament", "court"]):
        return "politics"
    if any(word in lowered for word in ["earthquake", "flood", "storm", "heat", "fire"]):
        return "climate"
    if any(word in lowered for word in ["market", "oil", "tariff", "trade", "inflation"]):
        return "economy"
    return "world"


def score_event(text):
    lowered = text.lower()
    score = 1
    for word, weight in IMPORTANT_TERMS.items():
        if word in lowered:
            score += weight
    return min(max(score, 1), 5)


def translation_api_key():
    return (
        os.environ.get("WORLD_CONSOLE_GOOGLE_TRANSLATE_API_KEY")
        or os.environ.get("GOOGLE_TRANSLATE_API_KEY")
        or ""
    ).strip()


def load_translation_cache():
    try:
        if TRANSLATION_CACHE.exists():
            payload = json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_translation_cache(cache):
    try:
        TRANSLATION_CACHE.parent.mkdir(exist_ok=True)
        TRANSLATION_CACHE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass


def translation_cache_key(text):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{TRANSLATION_TARGET}:{digest}"


def google_translate_batch(texts, api_key, timeout=10):
    if not texts:
        return []

    url = GOOGLE_TRANSLATE_ENDPOINT + "?" + urllib.parse.urlencode({"key": api_key})
    body = json.dumps({
        "q": texts,
        "target": TRANSLATION_TARGET,
        "format": "text",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    rows = payload.get("data", {}).get("translations", [])
    translated = []
    for row in rows:
        translated.append(html.unescape(row.get("translatedText", "")).strip())
    return translated


def apply_translations(events):
    api_key = translation_api_key()
    if not api_key:
        return events

    cache = load_translation_cache()
    missing = []
    missing_keys = []

    for event in events:
        for field in ("title", "statement", "summary"):
            text = (event.get(field) or "").strip()
            if not text:
                continue
            key = translation_cache_key(text)
            cached = cache.get(key)
            if cached:
                event[f"{field}_zh"] = cached
            else:
                missing.append(text)
                missing_keys.append((event, field, key))

    if missing:
        try:
            for start in range(0, len(missing), 24):
                batch = missing[start:start + 24]
                batch_keys = missing_keys[start:start + 24]
                translations = google_translate_batch(batch, api_key)
                for translated, (event, field, key) in zip(translations, batch_keys):
                    if translated:
                        cache[key] = translated
                        event[f"{field}_zh"] = translated
            save_translation_cache(cache)
        except Exception:
            # Translation is helpful, not required. Keep reports usable if the API is unavailable.
            return events

    return events


def normalize_lookup_text(text):
    return f" {re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()} "


def lookup_key(key):
    return re.sub(r"[^a-z0-9]+", " ", key.lower()).strip()


def lookup_has(lookup, key):
    normalized_key = lookup_key(key)
    return bool(normalized_key) and f" {normalized_key} " in lookup


def first_lookup_word(text):
    match = re.search(r"[a-z0-9]+", text.lower())
    return match.group(0) if match else ""


def is_question_headline(title):
    stripped = (title or "").strip()
    if "?" in stripped:
        return True
    return first_lookup_word(stripped) in QUESTION_STARTERS


def has_any_lookup_term(lookup, terms):
    return any(lookup_has(lookup, term) for term in terms)


def is_concrete_event(title, summary):
    title_lookup = normalize_lookup_text(title)

    if has_any_lookup_term(title_lookup, NON_EVENT_TITLE_TERMS):
        return False

    if is_question_headline(title):
        return False

    if (
        has_any_lookup_term(title_lookup, HYPOTHETICAL_TITLE_TERMS)
        and not has_any_lookup_term(title_lookup, HYPOTHETICAL_ALLOWED_TERMS)
    ):
        return False

    return has_any_lookup_term(title_lookup, CONCRETE_EVENT_TERMS)


def location_key_weight(key):
    normalized_key = lookup_key(key)
    if normalized_key in LOCATION_KEY_WEIGHTS:
        return LOCATION_KEY_WEIGHTS[normalized_key]
    return 10 if len(normalized_key) > 4 else 5


def score_location_keys(lookup, keys):
    return sum(location_key_weight(key) for key in keys if lookup_has(lookup, key))


def best_scored_location(title, summary):
    title_lookup = normalize_lookup_text(title)
    summary_lookup = normalize_lookup_text(summary)
    title_has_location = any(score_location_keys(title_lookup, keys) for _, _, _, _, keys in LOCATION_HINTS)
    summary_multiplier = 0.25 if title_has_location else 0.65

    best = None
    best_score = 0
    for city, country, lat, lon, keys in LOCATION_HINTS:
        score = score_location_keys(title_lookup, keys)
        score += score_location_keys(summary_lookup, keys) * summary_multiplier
        if score > best_score:
            best = city, country, lat, lon
            best_score = score

    if best and best_score >= 8:
        return best
    return None


def locate_event(title, summary=""):
    title_lookup = normalize_lookup_text(title)
    combined_lookup = normalize_lookup_text(f"{title} {summary}")

    if any(lookup_has(title_lookup, key) for key in [
        "us senate",
        "senate advances",
        "war powers resolution",
        "us imposes sanctions",
        "trump administration",
        "white house",
    ]):
        return "Washington", "United States", 38.9072, -77.0369

    if lookup_has(title_lookup, "taiwan says") or lookup_has(title_lookup, "taiwan s"):
        return "Taipei", "Taiwan", 25.0330, 121.5654

    scored = best_scored_location(title, summary)
    if scored:
        return scored

    if lookup_has(combined_lookup, "trump"):
        return "Washington", "United States", 38.9072, -77.0369
    return "Unplaced", "", None, None


def parse_feed(source, xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item")
    if not items:
        items = root.findall("{http://www.w3.org/2005/Atom}entry")

    events = []
    for item in items[:30]:
        title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "Untitled report"
        link = item.findtext("link") or ""
        atom_link = item.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            link = atom_link.attrib.get("href", link)
        summary = (
            item.findtext("description")
            or item.findtext("summary")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
            or title
        )
        published = item.findtext("pubDate") or item.findtext("published") or item.findtext("{http://www.w3.org/2005/Atom}published")
        clean_title = strip_markup(title)
        clean_summary = strip_markup(summary)
        if not clean_title:
            continue
        if not is_concrete_event(clean_title, clean_summary):
            continue

        combined = f"{clean_title} {clean_summary}"
        location, country, lat, lon = locate_event(clean_title, clean_summary)
        category = classify_event(combined)
        events.append({
            "id": re.sub(r"[^a-z0-9]+", "-", f"{source}-{clean_title}".lower()).strip("-")[:90],
            "title": clean_title[:180],
            "statement": direct_event_title(clean_title),
            "summary": clean_summary[:300],
            "source": source,
            "url": link,
            "published": parse_datetime(published),
            "location": location,
            "country": country,
            "lat": lat,
            "lon": lon,
            "category": category,
            "severity": score_event(combined),
        })
    return events


def load_events():
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    for source, url in NEWS_FEEDS:
        try:
            for event in parse_feed(source, fetch_url(url)):
                key = event["title"].lower()
                if key in seen:
                    continue
                if event["severity"] < 3:
                    continue
                if not event_is_recent_enough(event, now):
                    continue
                seen.add(key)
                events.append(event)
        except Exception:
            continue

    if not events:
        return FALLBACK_EVENTS

    events.sort(key=lambda item: (item["severity"], event_datetime(item["published"])), reverse=True)
    return apply_translations(events[:24])


def load_world_geojson():
    if WORLD_CACHE.exists():
        try:
            return json.loads(WORLD_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    for url in WORLD_GEOJSON_URLS:
        try:
            data = fetch_url(url, timeout=8)
            parsed = json.loads(data.decode("utf-8"))
            WORLD_CACHE.parent.mkdir(exist_ok=True)
            WORLD_CACHE.write_text(json.dumps(parsed), encoding="utf-8")
            return parsed
        except Exception:
            continue
    return None


def port_is_available(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return False
    except OSError:
        return True


def pick_port(start):
    port = start
    while port < start + 30:
        if port_is_available(port):
            return port
        port += 1
    raise RuntimeError("No local port available.")


def running_console_port(start):
    for port in range(start, start + 30):
        if port_is_available(port):
            continue
        url = f"http://127.0.0.1:{port}/index.html"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "CodexWorldConsole/1.0"})
            with urllib.request.urlopen(request, timeout=1.2) as response:
                body = response.read(4096).decode("utf-8", errors="ignore")
            if (
                "Codex Console" in body
                or "电脑总控台" in body
                or "Codex World" in body
                or "World Event Console" in body
            ):
                return port
        except Exception:
            continue
    return None


def browser_candidates():
    candidates = []
    for name in ("msedge.exe", "chrome.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    local_app = os.environ.get("LOCALAPPDATA", "")
    program_files = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
    candidates.extend([
        str(Path(program_files[0]) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(program_files[1]) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        str(Path(program_files[0]) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(program_files[1]) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        str(Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ])
    return [item for item in candidates if item and Path(item).exists()]


def open_console_window(url):
    for browser in browser_candidates():
        try:
            subprocess.Popen(
                [browser, f"--app={url}", "--new-window"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **hidden_subprocess_kwargs(),
            )
            return
        except OSError:
            continue
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="Codex Console")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--edition", choices=tuple(CONSOLE_EDITION_MODULES.keys()), default=current_console_edition())
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    CONSOLE_CONFIG["edition"] = sanitize_console_edition(args.edition)

    local_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    existing_port = running_console_port(args.port) if local_host == "127.0.0.1" else None
    if existing_port:
        url = console_start_url(existing_port)
        if not args.no_browser:
            open_console_window(url)
        return

    port = pick_port(args.port)
    url = console_start_url(port).replace("127.0.0.1", local_host, 1)
    server = ThreadingHTTPServer((args.host, port), ConsoleHandler)

    if sys.stdout:
        print()
        print("Codex Console is running.")
        print(f"URL: {url}")
        if args.host in ("0.0.0.0", "::"):
            print(f"LAN mode is enabled on port {port}. Use your PC LAN IP from Android.")
        print("Press Ctrl+C to stop it.")
        print()

    if not args.no_browser:
        open_console_window(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This launcher is tuned for Windows, but the page itself is portable.")
    main()
