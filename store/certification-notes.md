# Microsoft Store certification notes

Codex Console is a packaged classic Windows desktop application. It declares `runFullTrust` because its user-requested workflows need ordinary desktop capabilities that are unavailable in an app-container process:

- reading and writing user-selected music, wallpaper, desktop-layout, Blender, and Git project files;
- launching user-selected desktop applications and HTTPS links, including Blender, GitHub Desktop, Steamworks tools, and Microsoft Store;
- invoking Git and PowerShell helpers for explicit project and desktop-layout operations;
- hosting the local application UI on loopback (`127.0.0.1`) and opening it in an embedded desktop window.

The app does not install a Windows service, driver, shell extension, browser extension, or scheduled task. It does not request administrator privileges. The Store package does not contain or invoke the legacy Inno Setup updater or uninstaller; Microsoft Store owns installation, updates, and removal.

Network access is used for user-initiated GitHub collaboration operations, Store-managed product links, and optional feedback reports. The Store build does not download or install external Codex Console or Codex World executables. Feedback content is sent only after the user submits it.

The package targets x64 Windows Desktop, minimum build 19041. It contains five wallpapers with documented Unsplash sources, no bundled music or lyric files, and no device-specific desktop layout files. The Store edition accepts user-selected local music and lyric files only; it does not expose URL, playlist, cookie, or automatic online lyric downloads.
