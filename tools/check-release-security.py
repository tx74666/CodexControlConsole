from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def position(text, value):
    result = text.find(value)
    require(result >= 0, f"release workflow is missing: {value}")
    return result


def main():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    audit_workflow = (ROOT / ".github" / "workflows" / "security-audit.yml").read_text(encoding="utf-8")
    store_audit_workflow = (ROOT / ".github" / "workflows" / "store-package-audit.yml").read_text(encoding="utf-8")
    build = (ROOT / "tools" / "build-windows.ps1").read_text(encoding="utf-8")
    blender_share = (ROOT / "blender_github_share.py").read_text(encoding="utf-8")
    publisher = (ROOT / "tools" / "publish-direct-github.ps1").read_text(encoding="utf-8")
    release_helper = (ROOT / "tools" / "publish-release.ps1").read_text(encoding="utf-8")
    requirements = (ROOT / "tools" / "windows-release-requirements.txt").read_text(encoding="utf-8")

    require("Require Artifact Signing configuration" in workflow, "signing configuration is not mandatory")
    require("azure/artifact-signing-action@v2" in workflow, "current Artifact Signing action is not used")
    require("if: ${{ vars.ARTIFACT_SIGNING_ENDPOINT" not in workflow, "signing can still be skipped")

    application = position(workflow, "-Stage Application")
    sign_application = position(workflow, "Sign application PE files")
    verify_application = position(workflow, "Verify application PE signatures")
    installer = position(workflow, "-Stage Installer")
    sign_installer = position(workflow, "Sign Windows Setup")
    verify_installer = position(workflow, "Verify signed Windows Setup")
    defender = position(workflow, "Defender scan release artifacts")
    publish = position(workflow, "Publish GitHub Release")
    require(
        application < sign_application < verify_application < installer < sign_installer < verify_installer < defender < publish,
        "release security stages are out of order",
    )

    require("files-folder-filter: exe,dll,pyd" in workflow, "all packaged PE extensions are not signed")
    require("files-folder-recurse: true" in workflow, "application signing is not recursive")
    require("check-authenticode-signatures.ps1" in workflow, "recursive signature verification is missing")
    require("check-defender-artifacts.ps1" in workflow, "Defender release scan is missing")
    require('runs-on: windows-2025' in workflow, "release runner is not locked to the known baseline")
    require('python-version: "3.12.10"' in workflow, "release Python is not locked to the known baseline")
    require("windows-release-requirements.txt" in workflow, "release dependencies are not installed from the lock file")

    require("workflow_dispatch:" in audit_workflow, "security audit cannot be started manually")
    require("push:" not in audit_workflow, "security audit must never run as a publishing trigger")
    require("check-defender-artifacts.ps1" in audit_workflow, "security audit does not scan with Defender")
    require("upload-artifact" not in audit_workflow, "unsigned audit artifacts must not be uploaded")
    require("action-gh-release" not in audit_workflow, "security audit must not publish a release")
    require("dist-audit" in audit_workflow, "security audit output is not isolated")

    require("workflow_dispatch:" in store_audit_workflow, "Store audit cannot be started manually")
    require("push:" not in store_audit_workflow, "Store audit must never run as a publishing trigger")
    require("build-store-msix.ps1" in store_audit_workflow, "Store audit does not build the MSIX")
    require("check-defender-artifacts.ps1" in store_audit_workflow, "Store audit does not scan with Defender")
    require("upload-artifact" not in store_audit_workflow, "development-identity MSIX must not be uploaded")
    require("action-gh-release" not in store_audit_workflow, "Store audit must not publish a release")

    locked_packages = {
        "altgraph==0.17.5",
        "packaging==26.2",
        "pefile==2024.8.26",
        "pillow==12.3.0",
        "pyinstaller==6.21.0",
        "pyinstaller-hooks-contrib==2026.6",
        "pywin32-ctypes==0.2.3",
        "setuptools==83.0.0",
        "yt-dlp==2026.7.4",
    }
    require(set(requirements.splitlines()) == locked_packages, "Windows release dependency lock changed unexpectedly")

    require("Resolve-CSharpCompiler" in build, "NativeFileDrag compiler discovery is missing")
    require("NativeFileDrag.exe could not be compiled from source" in build, "NativeFileDrag build is not enforced")
    require('Source = "tools\\NativeFileDrag.exe"' not in build, "precompiled NativeFileDrag.exe is still packaged")
    require('"--noupx"' in build, "PyInstaller UPX is not explicitly disabled")
    require('@("--exclude-module", "yt_dlp")' in build, "Store package still includes the network media downloader")
    require('"--collect-all", "yt_dlp"' not in build, "yt-dlp source files are still duplicated in the installed package")
    require('"--exclude-module", "tkinter"' in build, "unused Tcl/Tk files are still included")
    require('"--hidden-import", "tkinter"' not in build, "tkinter is still forced into the package")
    require("System.Windows.Forms.OpenFileDialog" in blender_share, "Windows Blender picker no longer uses the native dialog")
    require("import tkinter as tk" not in blender_share, "a static tkinter import can restore the slow Tcl/Tk package")
    require("LEGACY_CACHE_ITEMS" in (ROOT / "world_console.py").read_text(encoding="utf-8"), "legacy cache migration is not allowlisted")
    require("for source in legacy_cache.rglob" not in (ROOT / "world_console.py").read_text(encoding="utf-8"), "legacy cache migration can copy the entire development cache")

    require("Get-FileHash" in publisher, "direct publisher does not hash the Setup")
    require("$Asset.digest" in publisher, "direct publisher does not verify the GitHub asset digest")
    require("Removed incomplete draft release" in publisher, "direct publisher does not clean failed drafts")
    signature_gate = position(publisher, "Assert-TrustedInstallerSignature")
    credential_access = position(publisher, "Get-GitHubCredential")
    require(signature_gate < credential_access, "direct publisher checks credentials before blocking unsigned installers")
    require('Status -ne "Valid"' in publisher, "direct publisher does not require a valid Authenticode signature")
    require("TimeStamperCertificate" in publisher, "direct publisher does not require a timestamped signature")
    require('PublicKey.Oid.Value -ne "1.2.840.113549.1.1.1"' in publisher, "direct publisher does not require RSA signing")
    require("self-signed certificates are not accepted" in publisher, "direct publisher can accept a self-signed public release")
    require("Install-PublisherCopy" in publisher, "publisher device is not synchronized after release")
    require("ExpectedVersion" in publisher, "local publisher upgrade is not version-verified")
    require("/FORCECLOSEAPPLICATIONS" in publisher, "publisher upgrade cannot close a headless old backend")
    require("DirectGitHub" not in release_helper, "normal release helper still exposes unsigned direct publishing")
    require("check-package-footprint.py" in release_helper, "direct publishing does not test packaged startup")
    require("check-console-ui-local.ps1" in release_helper, "release UI checks still depend on an installed version")

    print("PASS release signing and Defender gates are fail-closed")


if __name__ == "__main__":
    main()
