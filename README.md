# Codex Control Console

Codex Control Console is a local Windows control surface for wallpaper, workspace, music, Blender texture handoff, and project utilities.

## Downloads

The current public release is available on GitHub:

- Release page: <https://github.com/tx74666/CodexControlConsole/releases/tag/v0.1.0>
- Windows desktop ZIP: <https://github.com/tx74666/CodexControlConsole/releases/download/v0.1.0/CodexControlConsole-windows.zip>
- Android companion APK: <https://github.com/tx74666/CodexControlConsole/releases/download/v0.1.0/CodexControlConsole-android.apk>

The static download page source lives in `docs/index.html`. GitHub Pages can be enabled later from repository settings; the release downloads above work without Pages.

## Windows Desktop

Requirements:

- Windows 10 or Windows 11
- Python 3.11 or newer
- Microsoft Edge or Google Chrome

Install:

1. Download and unzip `CodexControlConsole-windows.zip`.
2. Double-click `Start-ControlConsole.vbs`.
3. The console opens at `http://127.0.0.1:8898/index.html`.

For Android access on the same trusted network, start `Start-ControlConsole-LAN.vbs` instead. Then connect from Android to:

```text
http://YOUR-PC-LAN-IP:8898/index.html
```

LAN mode exposes the console to other devices on the network. Use it only on a trusted network.

## Android Companion

Install `CodexControlConsole-android.apk`, open it, and enter the PC LAN URL shown above. The Android app is a WebView companion for the PC console; the PC desktop service must be running for it to control local resources.

## Release

The release workflow builds both assets when a `v*` tag is pushed or when the workflow is run manually.

To build the Windows ZIP locally:

```powershell
.\tools\package-desktop.ps1 -Version 0.1.0 -OutputDir dist
```

The package script intentionally excludes runtime cache, cookies, downloaded music, and local browser profiles.
