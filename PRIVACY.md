# Codex Console Privacy Notice

Last updated: August 1, 2026

Codex Console is a local Windows control center. Music, wallpapers, desktop layouts, Blender project settings, and other workspace data stay on the device unless the user explicitly opens or synchronizes content with a third-party service.

## Feedback reports

Sending a feedback report is optional. A submitted report can contain:

- the category and description entered by the user;
- up to four screenshots selected by the user;
- the Codex Console version, Windows version, locale, and active module;
- a random installation identifier used to enforce abuse limits.

The feedback service transforms installation identifiers and network addresses into keyed hashes for rate limiting. Raw IP addresses are not stored. Report text and metadata are stored in Cloudflare D1, and private screenshots are stored in Cloudflare R2. Reports are visible only to the service administrator and are retained until they are no longer needed for support, abuse prevention, or service maintenance.

Codex Console does not sell personal information, show advertising, or use cross-app tracking. Users should avoid including passwords, account tokens, private documents, or unrelated personal information in reports or screenshots.

## Third-party services

Features that open GitHub, GitHub Desktop, Blender, Steamworks, Microsoft Store, or other external tools are governed by those services' own privacy terms. Codex Console does not receive those account passwords.

## Local data and removal

The Microsoft Store edition keeps its settings in the app's Windows package data. Windows removes that package data when the app is uninstalled. Files the user deliberately creates, imports, or places elsewhere on the device are not deleted automatically.

To ask about this notice or request removal of a feedback report, use the in-app feedback form, select `Other`, and include the report ID returned after submission.
