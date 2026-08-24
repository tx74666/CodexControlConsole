# Codex Console

A Windows control console for music, wallpaper, Blender, Unity, Steamwork, RandomRealm, and workspace tools.

## Download / 下载

Recommended: [CodexControlConsole-Setup-x64.exe](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Setup-x64.exe), the signed installer with the simplest update path.

Alternative: [CodexControlConsole-Windows-x64.zip](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Windows-x64.zip). Extract the `Codex Console` folder and run `Codex Console.exe`; it does not install shortcuts.

推荐下载：[CodexControlConsole-Setup-x64.exe](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Setup-x64.exe)，这是已签名安装包，后续更新最方便。

免安装备用：[CodexControlConsole-Windows-x64.zip](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-Windows-x64.zip)。解压 `Codex Console` 文件夹后运行 `Codex Console.exe`，不会自动创建快捷方式。

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

Install Python 3.12 x64 and Inno Setup 7, install the locked Windows build dependencies, then run:

```powershell
python -m pip install --only-binary=:all: -r .\tools\windows-release-requirements.txt
.\tools\build-windows.ps1 -OutputDir dist
```

`app-manifest.json` is the single build-version source. `-Version` may be omitted; when supplied for release automation it must match the manifest exactly (an optional leading `v` is accepted).

The result is `dist\CodexControlConsole-Setup-x64.exe`. A local build is unsigned and is only for development and security testing.

## Publish A Release

The release helper retries intermittent GitHub connections, pushes `main`, creates the version tag, and waits until both Windows x64 downloads are available:

```powershell
.\tools\publish-release.ps1 -Version 1.0.5
```

Use `-CheckConnection` to verify GitHub access without uploading anything.

Unsigned builds can never be published by the release workflow or release helper. The emergency direct-publisher helper accepts only an installer that already has a valid, timestamped, RSA Authenticode signature from a trusted issuer.

Public releases are fail-closed. GitHub Actions requires every Artifact Signing setting and requires the requested tag version to match `app-manifest.json`. It first runs the shared quality checks, builds the application, signs every packaged `exe`, `dll`, and `pyd`, verifies those signatures, builds and signs Setup, creates the ZIP from that signed application folder, and finally scans the main executable, native drag helper, Setup, and ZIP with Microsoft Defender. The workflow stops before publishing if any signature is missing, Defender reports a threat, or any Artifact Signing setting is absent. There is no committed unsigned-release exception.

The manual `Audit Windows x64 Setup` workflow reproduces the build and Defender scan without signing, uploading, or publishing its temporary installer. Use it to compare a candidate with an earlier release while trusted signing is being configured.

Required repository variables are `ARTIFACT_SIGNING_ENDPOINT`, `ARTIFACT_SIGNING_ACCOUNT`, and `ARTIFACT_SIGNING_PROFILE`. Required secrets are `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET`. The certificate profile must use a publicly trusted signing identity; self-signed and test profiles are not release identities.

## Checks

The same lightweight, non-building check entry point is used by pull requests, pushes to `main`, and public releases:

```powershell
.\tools\check-quality.ps1
```

It covers Python syntax and core services, desktop layouts, external application launching, Blender collaboration, feedback Worker tests, and static Node syntax checks for the UI. For the full local browser regression, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\check-console-ui-local.ps1` separately.

Blender > Helper > GitHub Coop lists repositories from `github-coop.json`. GitHub Desktop handles authentication, clone, commits, pull, and push.

Blender > Builder > Reference View Set accepts Front, Back, Left, Right, Top, and Bottom images for any kind of object. Temporary uploads are decoded and copied into the selected project's `References/CDesigner/<set-name>--<set-id>/images` folder. Create/Update submits configuration, replacements, and removals as one transaction; all images are validated before the versioned `reference-views.json` manifest is atomically replaced, so a failed request leaves the previous set usable. The manifest stores only POSIX paths relative to itself so the C designer Blender add-on can rebuild the set after either application restarts.

Codex Console checks the selected repository against GitHub when Blender Helper opens and whenever Refresh is pressed. A cloud card guides first-time users into Clone; a local card reports remote updates, uncommitted work, pending pushes, or a synchronized state. Before editing a `.blend`, pull the latest version and make sure nobody else is editing that same binary file. When finished, save and close Blender, then commit and push through GitHub Desktop. External textures and references must be packed into the `.blend` or intentionally included in the repository.

The release workflow requires Microsoft Artifact Signing and cannot publish an unsigned Setup. `NativeFileDrag.exe` is compiled from `NativeFileDrag.cs` during every clean application build instead of packaging the repository's precompiled helper. Self-signing is intentionally not used because it does not establish public Windows trust.
