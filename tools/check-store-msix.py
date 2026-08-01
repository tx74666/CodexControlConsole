import argparse
import json
from pathlib import Path
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image


FOUNDATION = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP = "http://schemas.microsoft.com/appx/manifest/uap/windows10"
UAP10 = "http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
RESCAP = "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
NS = {"f": FOUNDATION, "uap": UAP, "uap10": UAP10, "rescap": RESCAP}
ASSET_SIZES = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square150x150Logo.png": (150, 150),
    "Square310x310Logo.png": (310, 310),
    "Wide310x150Logo.png": (310, 150),
}
STORE_WALLPAPERS = {
    "blue-lake-boats.jpg",
    "calm-mountain-lake.jpg",
    "quiet-forest-aerial.jpg",
    "snow-water-mountains.jpg",
    "soft-mountain-sun.jpg",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def normalized(path):
    return urllib.parse.unquote(str(path).replace("\\", "/"))


def read_manifest(payload):
    return ET.fromstring(payload)


def verify_manifest(root, identity_name, publisher, package_version):
    identity = root.find("f:Identity", NS)
    require(identity is not None, "MSIX identity is missing")
    require(identity.get("Name") == identity_name, "MSIX identity name is wrong")
    require(identity.get("Publisher") == publisher, "MSIX publisher is wrong")
    require(identity.get("Version") == package_version, "MSIX package version is wrong")
    require(identity.get("ProcessorArchitecture") == "x64", "MSIX is not x64")

    description = root.find("f:Properties/f:Description", NS)
    require(description is not None and (description.text or "").strip(), "MSIX package description is missing")

    target = root.find("f:Dependencies/f:TargetDeviceFamily", NS)
    require(target is not None and target.get("Name") == "Windows.Desktop", "MSIX does not target Windows Desktop")
    require(target.get("MinVersion") == "10.0.19041.0", "MSIX minimum Windows version changed")

    application = root.find("f:Applications/f:Application", NS)
    require(application is not None, "MSIX application declaration is missing")
    require(application.get("Executable") == "Codex Console.exe", "MSIX executable is wrong")
    require(
        application.get(f"{{{UAP10}}}RuntimeBehavior") == "packagedClassicApp",
        "MSIX runtime behavior is not packagedClassicApp",
    )
    require(application.get(f"{{{UAP10}}}TrustLevel") == "mediumIL", "MSIX trust level is wrong")
    capability = root.find("f:Capabilities/rescap:Capability", NS)
    require(capability is not None and capability.get("Name") == "runFullTrust", "runFullTrust is missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--msix", type=Path, required=True)
    parser.add_argument("--msixupload", type=Path)
    parser.add_argument("--listing-assets-dir", type=Path)
    parser.add_argument("--identity-name", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--product-id", default="")
    args = parser.parse_args()

    staging = args.staging_dir.resolve()
    manifest_path = staging / "AppxManifest.xml"
    require(manifest_path.is_file(), "AppxManifest.xml is missing")
    verify_manifest(read_manifest(manifest_path.read_bytes()), args.identity_name, args.publisher, args.package_version)
    require((staging / "Codex Console.exe").is_file(), "Codex Console.exe is missing from MSIX staging")
    require(not list(staging.rglob("unins*.exe")), "an Inno uninstaller entered the Store package")
    require(not list(staging.rglob("*.mp3")), "unlicensed music entered the Store package")
    require(not list(staging.rglob("*.lrc")), "third-party lyrics entered the Store package")
    require(
        not any("yt_dlp" in normalized(path).casefold() for path in staging.rglob("*")),
        "network media downloader entered the Store package",
    )

    wallpaper_dirs = [path for path in staging.rglob("wallpapers") if path.is_dir()]
    require(len(wallpaper_dirs) == 1, "Store wallpaper directory is missing or duplicated")
    packaged_wallpapers = {
        path.name for path in wallpaper_dirs[0].iterdir() if path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}
    }
    require(packaged_wallpapers == STORE_WALLPAPERS, "Store package contains undocumented wallpapers")

    app_manifests = list(staging.rglob("app-manifest.json"))
    require(len(app_manifests) == 1, "application manifest is missing or duplicated")
    app_manifest = json.loads(app_manifests[0].read_text(encoding="utf-8"))
    require(app_manifest.get("installMode") == "store", "Store package can overwrite itself with GitHub Setup")
    require(app_manifest.get("edition") == "public", "Store package is not the public edition")
    require(str(app_manifest.get("storeProductId") or "") == args.product_id, "Store product ID is wrong")

    for name, expected in ASSET_SIZES.items():
        path = staging / "Assets" / name
        require(path.is_file(), f"Store visual asset is missing: {name}")
        with Image.open(path) as image:
            require(image.size == expected, f"Store visual asset has the wrong size: {name}")
            require(image.mode == "RGBA", f"Store visual asset lost transparency: {name}")

    if args.listing_assets_dir:
        listing_logo = args.listing_assets_dir.resolve() / "StoreLogo300x300.png"
        require(listing_logo.is_file(), "Store listing logo is missing")
        with Image.open(listing_logo) as image:
            require(image.size == (300, 300), "Store listing logo has the wrong size")
            require(image.mode == "RGBA", "Store listing logo lost transparency")

    require(args.msix.is_file(), "MSIX was not created")
    with zipfile.ZipFile(args.msix) as package:
        names = {normalized(name) for name in package.namelist()}
        required = {"AppxManifest.xml", "AppxBlockMap.xml", "[Content_Types].xml", "Codex Console.exe"}
        require(required <= names, f"MSIX container is incomplete: {sorted(required - names)}")
        packaged_manifest = read_manifest(package.read("AppxManifest.xml"))
        verify_manifest(packaged_manifest, args.identity_name, args.publisher, args.package_version)
        require(not any(re.search(r"(^|/)desktop-layout.*\.json$", name, re.I) for name in names), "device layout entered MSIX")

    if args.msixupload:
        require(args.msixupload.is_file(), "MSIX upload wrapper was not created")
        with zipfile.ZipFile(args.msixupload) as upload:
            require(upload.testzip() is None, "MSIX upload wrapper is damaged")
            entries = upload.infolist()
            require(len(entries) == 1, "MSIX upload wrapper contains unexpected files")
            require(entries[0].filename == args.msix.name, "MSIX upload wrapper contains the wrong package")
            require(entries[0].file_size == args.msix.stat().st_size, "MSIX upload wrapper package size is wrong")

    print(f"PASS Store MSIX {args.package_version} ({args.msix.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
