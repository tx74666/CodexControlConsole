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
.\tools\build-windows.ps1 -Version 0.5.3 -OutputDir dist
```

The result is `dist\CodexControlConsole-Setup-x64.exe`.

## Checks

```powershell
node .\tools\check-console-ui.mjs
node --test .\services\feedback-relay\test\feedback.test.js
python .\tools\check-feedback.py
python .\tools\check-blender-github-share.py
python .\tools\check-console-update.py
python .\tools\check-desktop-layout.py
```

Blender > Helper > GitHub Coop lists repositories from `github-coop.json`. GitHub Desktop handles authentication, clone, commits, pull, and push.

The release workflow can sign Setup with Microsoft Artifact Signing when its Azure secrets and repository variables are configured. Self-signing is intentionally not used because it does not establish public Windows trust.
