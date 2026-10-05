# Codex Console Privacy Notice

Last updated: October 6, 2026

Codex Console is a local Windows control center. Music, wallpapers, desktop layouts, Blender project settings, and other workspace data stay on the device unless the user explicitly opens or synchronizes content with a third-party service.

## Same-Wi-Fi text and image transfer

The optional phone connection sends selected text and images directly between the paired phone and this computer. Original attachments are stored locally in the selected document library's `互传` folder; history and previews are in `互传/.console-transfer`. When no library is selected, the application's local data directory is used. They are not uploaded to GitHub, the public phone website, or the feedback service. The local HTTP connection is intended for a trusted local network.

Scanning a QR code processes camera frames or the selected image locally on the phone. The pairing invitation is valid for five minutes and one use, and is removed from the address before phone requests. A remembered phone holds a 90-day HttpOnly credential cookie. The computer keeps only a hash of that credential, device name and timestamps in private application data, bound to the document library and configured network. Saved phone shortcuts contain the computer address, not a pairing secret. Users can remove remembered phones on the computer or revoke their own connection by logging out on the phone.

When enabled, local mDNS announces a pseudonymous computer name, local address, port and program version on the selected network. It does not announce document paths or credentials. Console can restore the entrance after restarting on the configured physical network and update its address after a DHCP change. Closing the phone entrance stops access and disables automatic restoration; it retains transfer history and remembered-device records until the user removes them.

## Feedback reports

Sending a feedback report is optional. A submitted report can contain:

- the category and description entered by the user;
- up to four screenshots selected by the user;
- the Codex Console version, Windows version, locale, and active module;
- a random installation identifier used to enforce abuse limits.

The feedback service transforms installation identifiers and network addresses into keyed hashes for rate limiting. Raw IP addresses are not stored. Report text and metadata are stored in Cloudflare D1, and private screenshots are stored in Cloudflare R2. Reports are visible only to the service administrator and are retained until they are no longer needed for support, abuse prevention, or service maintenance.

Codex Console does not sell personal information, show advertising, or use cross-app tracking. Users should avoid including passwords, account tokens, private documents, or unrelated personal information in reports or screenshots.

## Third-party services

The optional Sign in with ChatGPT connection sends only a newly confirmed Console discussion's frozen text, context from its originating record, and explicitly selected images to OpenAI's official Responses service. It uses the authorized account's shared plan quota according to OpenAI's usage and credits settings. Existing ChatGPT chats and memory are not imported. The request uses `store: false`; this flag does not replace OpenAI's applicable service and privacy terms. Answers and completion receipts are saved locally to the originating Console record.

The formal connection's access and refresh credentials are protected with Windows current-user DPAPI and are not exposed to the paired phone, source repository, GitHub release, or logs. Account authorization is performed by the user on OpenAI's official page. Disconnecting stops new requests and attempts to revoke that application connection; when remote revocation cannot be verified, Console reports it rather than claiming the remote grant has been removed. Old discussions, images and drafts are retained. No browser relay or subscription request is issued just because a draft is saved or the connection status is viewed.

Features that open GitHub, GitHub Desktop, Blender, Steamworks, Microsoft Store, or other external tools are governed by those services' own privacy terms. Codex Console does not receive those account passwords.

## Local data and removal

The Microsoft Store edition keeps its settings in the app's Windows package data. Windows removes that package data when the app is uninstalled. Files the user deliberately creates, imports, or places elsewhere on the device are not deleted automatically.

To ask about this notice or request removal of a feedback report, use the in-app feedback form, select `Other`, and include the report ID returned after submission.
