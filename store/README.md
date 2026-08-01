# Microsoft Store package

`tools/build-store-msix.ps1` creates an x64 MSIX, its `.msixupload` wrapper, and a 300 x 300 listing logo from the same application bundle used by the Windows installer. The version is read from `app-manifest.json` unless `-Version` is provided.

The default identity is development-only. A Store submission must use the exact package identity copied from Partner Center:

```powershell
Copy-Item store/store-identity.example.json store/store-identity.local.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/build-store-msix.ps1 -IdentityFile store/store-identity.local.json -StoreSubmission
```

The Store build uses `installMode: store`. It does not download or launch GitHub Setup files; Microsoft Store owns acquisition, updates, and uninstall. An existing Codex World installation can still be opened, and a Store product link can be enabled later with `worldProductId`.

The Store package intentionally excludes bundled music and the two wallpapers without documented redistribution terms. It keeps the five wallpapers listed in `wallpapers/SOURCES.md`. Music and lyric import is local-file-only in the Store edition; URL, playlist, cookie, and automatic online lyric downloads are unavailable. Do not remove these filters unless redistribution licenses and service terms have been reviewed and recorded.

Submission text is prepared in `store/listing.en-US.md` and `store/listing.zh-CN.md`. The restricted-capability explanation is in `store/certification-notes.md`, and the public privacy URL is `https://github.com/tx74666/CodexControlConsole/blob/main/PRIVACY.md`.

Upload `dist-store/CodexConsole-<version>-x64.msixupload` to Partner Center. The development-identity package is for auditing only and cannot be submitted.
