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
    build = (ROOT / "tools" / "build-windows.ps1").read_text(encoding="utf-8")

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

    require("Resolve-CSharpCompiler" in build, "NativeFileDrag compiler discovery is missing")
    require("NativeFileDrag.exe could not be compiled from source" in build, "NativeFileDrag build is not enforced")
    require('Source = "tools\\NativeFileDrag.exe"' not in build, "precompiled NativeFileDrag.exe is still packaged")
    require('"--noupx"' in build, "PyInstaller UPX is not explicitly disabled")

    print("PASS release signing and Defender gates are fail-closed")


if __name__ == "__main__":
    main()
