# Codex Console

A small Windows control console for wallpaper, music, and optional developer tools.

## Download

Most people should use the Lite desktop build:

| Need | Download |
| --- | --- |
| Wallpaper + Music only | [CodexControlConsole-lite-windows.zip](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-lite-windows.zip) |
| Full developer tools | [CodexControlConsole-developer-windows.zip](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-developer-windows.zip) |
| Android companion | [CodexControlConsole-android.apk](https://github.com/tx74666/CodexControlConsole/releases/latest/download/CodexControlConsole-android.apk) |

Latest release: [github.com/tx74666/CodexControlConsole/releases/latest](https://github.com/tx74666/CodexControlConsole/releases/latest)

## Start On Windows

1. Download one of the ZIP files above.
2. Unzip it anywhere you like.
3. Double-click `Start-ControlConsole.vbs`.

Lite opens with only Wallpaper and Music. Developer opens with Manager, Console, Blender, Unity, Steamwork, RandomRealm, Music, and Wallpaper.

## Updates

Portable Windows builds check the latest GitHub release in the background. When a newer version is available, choose **Update** in Console; Codex Console downloads the matching Lite or Developer ZIP, verifies its SHA-256 checksum and app manifest, installs it, and restarts.

Updates are never installed silently. A source checkout opens the release page instead of overwriting the repository.

## Multiple Windows Users

Each Windows account keeps its own settings, indexes, cookies, and update files in:

```text
%LOCALAPPDATA%\CodexControlConsole
```

The extracted program folder can therefore be shared without mixing users' runtime data. Set `CODEX_CONTROL_DATA_DIR` to use a different per-user location. No installation identifier or usage data is sent anywhere.

## Android

1. On the PC, start `Start-ControlConsole-LAN.vbs`.
2. Install `CodexControlConsole-android.apk`.
3. In Android, enter:

```text
http://YOUR-PC-LAN-IP:8898/index.html
```

Use LAN mode only on a trusted network.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer
- Microsoft Edge or Google Chrome

## Build Locally

```powershell
.\tools\package-desktop.ps1 -Version 0.3.0 -OutputDir dist
```

The package script builds the developer ZIP, the lite ZIP, and the compatibility Windows ZIP. Runtime cache, cookies, downloaded music, and local browser profiles are not included.

## Check The UI

With Control Console running locally, use Node.js 22 or newer:

```powershell
node .\tools\check-console-ui.mjs
```

The check covers cache consistency, lazy module loading, Blender view transitions, stable backgrounds, and horizontal overflow.

To verify the Blender GitHub Coop workflow without touching a real project, remote, or desktop app:

```powershell
python .\tools\check-blender-github-share.py
```

To verify archive validation, rollback, and per-user update storage:

```powershell
python .\tools\check-console-update.py
```

Blender > Helper > GitHub Coop lists the `.blend` files in the selected project as compact cards. Use the three links to open that project in GitHub Desktop, its local folder, or its GitHub repository. When no remote exists yet, the GitHub link opens the new-repository page. The underlying share service still supports Git, Git LFS, per-project settings, version commits, and pushes.
