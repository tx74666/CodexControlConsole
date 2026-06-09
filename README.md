# Codex Control Console

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
.\tools\package-desktop.ps1 -Version 0.2.1 -OutputDir dist
```

The package script builds the developer ZIP, the lite ZIP, and the compatibility Windows ZIP. Runtime cache, cookies, downloaded music, and local browser profiles are not included.
