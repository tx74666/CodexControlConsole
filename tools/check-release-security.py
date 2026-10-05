from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def position(text, value):
    result = text.find(value)
    require(result >= 0, f"release workflow is missing: {value}")
    return result


def main():
    desktop_version = json.loads((ROOT / "app-manifest.json").read_text(encoding="utf-8"))["version"]
    phone_version = json.loads((ROOT / "phone" / "version.json").read_text(encoding="utf-8"))["version"]
    require(desktop_version == phone_version, "Windows and iPhone release versions must match")
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    audit_workflow = (ROOT / ".github" / "workflows" / "security-audit.yml").read_text(encoding="utf-8")
    store_audit_workflow = (ROOT / ".github" / "workflows" / "store-package-audit.yml").read_text(encoding="utf-8")
    build = (ROOT / "tools" / "build-windows.ps1").read_text(encoding="utf-8")
    blender_share = (ROOT / "blender_github_share.py").read_text(encoding="utf-8")
    publisher = (ROOT / "tools" / "publish-direct-github.ps1").read_text(encoding="utf-8")
    release_helper = (ROOT / "tools" / "publish-release.ps1").read_text(encoding="utf-8")
    publisher_sync = (ROOT / "tools" / "sync-publisher-installation.ps1").read_text(encoding="utf-8")
    requirements = (ROOT / "tools" / "windows-release-requirements.txt").read_text(encoding="utf-8")
    quality_workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
    quality_script = (ROOT / "tools" / "check-quality.ps1").read_text(encoding="utf-8")

    require(not (ROOT / ".github" / "unsigned-release-approval.txt").exists(), "a persistent unsigned release approval still exists")
    require("Resolve Artifact Signing policy" in workflow, "signing policy is missing")
    require("azure/artifact-signing-action@v2" in workflow, "current Artifact Signing action is not used")
    require("if: ${{ vars.ARTIFACT_SIGNING_ENDPOINT" not in workflow, "signing can still be skipped")
    require(workflow.count("if: env.SIGNING_ENABLED == 'true'") == 4, "signing steps do not share one explicit policy")
    require(workflow.count("SIGNING_ENABLED=false") == 1, "the unsigned fallback is not explicit and singular")
    require("unsigned-release-approval" not in workflow, "the release workflow still reads a persistent unsigned approval")
    require("if ($missing.Count -eq 0)" in workflow, "complete signing configuration is not detected")
    require("elseif ($missing.Count -eq $required.Count)" in workflow, "the unsigned fallback does not require every signing setting to be absent")
    require("trusted signing is only partially configured" in workflow, "partial signing configuration does not fail closed")
    require("Windows SmartScreen may show an unknown-publisher warning" in workflow, "unsigned release notes do not disclose the warning")
    require("INPUT_VERSION: ${{ github.event.inputs.version }}" in workflow, "the release input is not passed through the environment")
    require('$tag = "${{ github.event.inputs.version }}"' not in workflow, "the release input is interpolated into PowerShell source")
    require('REF: ${{ github.ref }}' in workflow, "the release ref is not passed through the environment")
    require('refs/heads/main' in workflow, "manual releases are not restricted to main")
    require('git merge-base --is-ancestor $env:GITHUB_SHA origin/main' in workflow, "release commits are not bound to main history")
    require('fetch-depth: 0' in workflow, "release checkout cannot verify main ancestry")
    require('persist-credentials: false' in workflow, "release checkout persists write credentials unnecessarily")
    require('group: release-${{ github.event.inputs.version || github.ref_name }}' in workflow, "duplicate release runs are not serialized")
    require("app-manifest.json" in workflow and "$version -ne $manifestVersion" in workflow, "release version is not bound to app-manifest.json")
    require("Codex Console v${{ env.RELEASE_VERSION }}" in workflow, "release notes do not use the resolved version")
    require("./tools/check-quality.ps1" in workflow, "the release workflow does not use the shared quality checks")

    application = position(workflow, "-Stage Application")
    sign_application = position(workflow, "Sign application PE files")
    verify_application = position(workflow, "Verify application PE signatures")
    installer = position(workflow, "-Stage Installer")
    sign_installer = position(workflow, "Sign Windows Setup")
    verify_installer = position(workflow, "Verify signed Windows Setup")
    zip_archive = position(workflow, "Build Windows x64 ZIP")
    defender = position(workflow, "Defender scan release artifacts")
    publish = position(workflow, "Publish GitHub Release")
    require(
        application < sign_application < verify_application < installer < sign_installer < verify_installer < zip_archive < defender < publish,
        "release security stages are out of order",
    )

    require("files-folder-filter: exe,dll,pyd" in workflow, "all packaged PE extensions are not signed")
    require("files-folder-recurse: true" in workflow, "application signing is not recursive")
    require("check-authenticode-signatures.ps1" in workflow, "recursive signature verification is missing")
    require("check-defender-artifacts.ps1" in workflow, "Defender release scan is missing")
    require("Compress-Archive" in workflow, "application ZIP is not created")
    require(
        workflow.count("CodexControlConsole-Windows-x64.zip") >= 4,
        "Windows ZIP is not verified, scanned, documented, and published",
    )
    require('runs-on: windows-2025' in workflow, "release runner is not locked to the known baseline")
    require('python-version: "3.12.10"' in workflow, "release Python is not locked to the known baseline")
    require("windows-release-requirements.txt" in workflow, "release dependencies are not installed from the lock file")

    require("workflow_dispatch:" in audit_workflow, "security audit cannot be started manually")
    require("push:" not in audit_workflow, "security audit must never run as a publishing trigger")
    require("check-defender-artifacts.ps1" in audit_workflow, "security audit does not scan with Defender")
    require("upload-artifact" not in audit_workflow, "unsigned audit artifacts must not be uploaded")
    require("action-gh-release" not in audit_workflow, "security audit must not publish a release")
    require("dist-audit" in audit_workflow, "security audit output is not isolated")
    require("-Version 1.0.2" not in audit_workflow, "security audit still builds a stale hard-coded version")
    require("-Version $env:APP_VERSION" in audit_workflow, "security audit does not use the manifest version")

    require("workflow_dispatch:" in store_audit_workflow, "Store audit cannot be started manually")
    require("push:" not in store_audit_workflow, "Store audit must never run as a publishing trigger")
    require("build-store-msix.ps1" in store_audit_workflow, "Store audit does not build the MSIX")
    require("check-defender-artifacts.ps1" in store_audit_workflow, "Store audit does not scan with Defender")
    require("upload-artifact" not in store_audit_workflow, "development-identity MSIX must not be uploaded")
    require("action-gh-release" not in store_audit_workflow, "Store audit must not publish a release")

    locked_packages = {
        "colorama==0.4.6",
        "qrcode==8.2",
        "ifaddr==0.2.0",
        "zeroconf==0.151.5",
        "altgraph==0.17.5",
        "packaging==26.2",
        "PyJWT[crypto]==2.15.1",
        "cryptography==50.0.1",
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
    require("sync-publisher-installation.ps1" in release_helper, "normal releases do not synchronize the publisher installation")
    require("[switch]$SkipPublisherSync" in release_helper, "publisher synchronization has no explicit opt-out")
    release_verified = position(release_helper, "Release exists but its Windows downloads are incomplete")
    publisher_synchronized = position(release_helper, "sync-publisher-installation.ps1")
    require(release_verified < publisher_synchronized, "publisher synchronization runs before release assets are verified")
    require("Get-FileHash" in publisher_sync, "publisher synchronization does not hash the downloaded Setup")
    require(".digest" in publisher_sync, "publisher synchronization does not require the GitHub asset digest")
    require("Invoke-WebRequest -Headers $DownloadHeaders" in publisher_sync, "publisher synchronization can forward API credentials to the asset redirect")
    require("publisher-state.json" in publisher_sync, "publisher releases are not recorded device-locally")
    require("installationId" in publisher_sync, "publisher state is not bound to the local installation")
    require("localInstallSynchronized" in publisher_sync, "publisher state does not record synchronization outcome")
    require('[string]$installedManifest.version -ne $Version' in publisher_sync, "publisher synchronization does not verify the installed version")

    require("pull_request:" in quality_workflow, "quality checks do not run for pull requests")
    require("push:" in quality_workflow and "main" in quality_workflow, "quality checks do not run for main pushes")
    require("./tools/check-quality.ps1" in quality_workflow, "quality workflow does not use the shared entry point")
    for required_check in (
        "check-desktop-layout.py",
        "check-external-app-launcher.py",
        "check-build-version.ps1",
        "check-blender-github-share.py",
        "check-feedback.py",
        "services/feedback-relay/test/feedback.test.js",
        "--check",
        "app.js",
    ):
        require(required_check in quality_script, f"shared quality entry point is missing: {required_check}")

    print("PASS release signing policy, version, quality, and Defender gates")


if __name__ == "__main__":
    main()
