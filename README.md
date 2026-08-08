# Codex Console

A Windows control console for music, wallpaper, Blender, Unity, Steamwork, RandomRealm, and workspace tools.

## Download / 下载

There is one public package: [CodexControlConsole-Setup-x64.exe](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Setup-x64.exe).

公开下载只有一个：[CodexControlConsole-Setup-x64.exe](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Setup-x64.exe)。

Latest release: [github.com/tx74666/CodexControlConsole/releases/latest](https://github.com/tx74666/CodexControlConsole/releases/latest)

## Install / 安装

1. Double-click `CodexControlConsole-Setup-x64.exe`.
2. Choose **简体中文** or **English**.
3. Choose the install drive and folder on the destination page.
4. Finish Setup and launch Codex Console from the desktop or Start menu.

1. 双击 `CodexControlConsole-Setup-x64.exe`。
2. 选择 **简体中文** 或 **English**。
3. 在安装位置页面选择磁盘和目录。
4. 完成安装，从桌面或开始菜单启动 Codex Console。

The installer contains the x64 application runtime. Users do not need to install Python.

## Updates

Codex Console checks the latest GitHub Releases for both Codex Console and Codex World. When an update is available, the update control downloads the verified Windows x64 Setup and opens the same bilingual installation guide. Updates are never installed silently.

## Per-device Data

Each Windows account keeps its own settings, indexes, cookies, desktop layouts, downloaded music, and update files under:

```text
%LOCALAPPDATA%\CodexControlConsole
```

No personal desktop layout or local media is included in the source repository or release installer.

## Desktop Layouts

Console can save, import, and manually restore Windows desktop icon layouts. Every plan is local to the current device. Saving a plan creates a timestamped backup first.

## Feedback

Users can send a category, short description, and optional PNG/JPEG/WebP screenshot from the Console tab. Reports pass through a Cloudflare Worker; the owner's PC does not expose an inbound port. The default limit is 10 reports per installation per UTC day, with Turnstile and an additional hashed network limit.

Report text is stored in D1 and screenshots are private in R2. Raw IP addresses are not stored. The inbox token is encrypted for the current Windows account and never returned to the browser.

Deployment files are under `services/feedback-relay`. The public installer reads the Worker URL and Turnstile site key from release repository variables.

## Requirements

- Windows 10 or Windows 11, 64-bit
- Microsoft Edge or Google Chrome

## Build Locally

Install Python 3.12 x64, PyInstaller, Pillow, yt-dlp, and Inno Setup 7, then run:

```powershell
python -m pip install pyinstaller pillow yt-dlp
.\tools\build-windows.ps1 -Version 1.0.2 -OutputDir dist
```

The result is `dist\CodexControlConsole-Setup-x64.exe`. A local build is unsigned and is only for development and security testing.

## Publish A Release

The release helper retries intermittent GitHub connections, pushes `main`, creates the version tag, and waits until the single Windows x64 Setup asset is available:

```powershell
.\tools\publish-release.ps1 -Version 1.0.2
```

Use `-CheckConnection` to verify GitHub access without uploading anything.

Unsigned local builds can never be published by the release helper. The emergency direct-publisher helper accepts only an installer that already has a valid, timestamped, RSA Authenticode signature from a trusted issuer.

Public releases are fail-closed. GitHub Actions uses the same Windows 2025, Python 3.12.10, PyInstaller 6.21.0, and dependency baseline as the clean v0.7.0 build. It first builds the application, signs every packaged `exe`, `dll`, and `pyd`, verifies those signatures, builds and signs Setup, recursively verifies again, and finally scans the main executable, native drag helper, and Setup with Microsoft Defender. The workflow stops before publishing if any signature is missing, Defender reports a threat, or any Artifact Signing setting is absent.

The manual `Audit Windows x64 Setup` workflow reproduces the build and Defender scan without signing, uploading, or publishing its temporary installer. Use it to compare a candidate with an earlier release while trusted signing is being configured.

Required repository variables are `ARTIFACT_SIGNING_ENDPOINT`, `ARTIFACT_SIGNING_ACCOUNT`, and `ARTIFACT_SIGNING_PROFILE`. Required secrets are `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`. The certificate profile must use a publicly trusted signing identity; self-signed and test profiles are not release identities.

## Checks

```powershell
node .\tools\check-console-ui.mjs
node --test .\services\feedback-relay\test\feedback.test.js
python .\tools\check-feedback.py
python .\tools\check-blender-github-share.py
python .\tools\check-reference-views.py
python .\tools\check-console-update.py
python .\tools\check-desktop-layout.py
python .\tools\check-release-security.py
```

Blender > Helper > GitHub Coop lists repositories from `github-coop.json`. GitHub Desktop handles authentication, clone, commits, pull, and push.

Blender > Builder > Reference View Set accepts Front, Back, Left, Right, Top, and Bottom images for any kind of object. Temporary uploads are decoded and copied into the selected project's `References/CDesigner/<set-name>--<set-id>/images` folder. Create/Update submits configuration, replacements, and removals as one transaction; all images are validated before the versioned `reference-views.json` manifest is atomically replaced, so a failed request leaves the previous set usable. The manifest stores only POSIX paths relative to itself so the C designer Blender add-on can rebuild the set after either application restarts.

Codex Console checks the selected repository against GitHub when Blender Helper opens and whenever Refresh is pressed. A cloud card guides first-time users into Clone; a local card reports remote updates, uncommitted work, pending pushes, or a synchronized state. Before editing a `.blend`, pull the latest version and make sure nobody else is editing that same binary file. When finished, save and close Blender, then commit and push through GitHub Desktop. External textures and references must be packed into the `.blend` or intentionally included in the repository.

The release workflow requires Microsoft Artifact Signing and cannot publish an unsigned Setup. `NativeFileDrag.exe` is compiled from `NativeFileDrag.cs` during every clean application build instead of packaging the repository's precompiled helper. Self-signing is intentionally not used because it does not establish public Windows trust.
