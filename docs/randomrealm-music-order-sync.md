# RandomRealm music order sync

The RandomRealm page has one manual **Sync music order to game** button below
the existing Release Control links. It preserves the page and Music layouts.
Only the existing 17 songs' group and order are sent.

Before sending, the page flushes its pending 80 ms Music save and waits for the
actual `/api/music/state` success response. Save snapshots run serially; an
earlier rejected save does not discard a later snapshot. A page that has not
edited Music uses current server disk state instead of writing a local default.

`POST /api/randomrealm/music-order-sync` accepts `{}` from this PC only, using
the existing trusted Host/Origin checks. The server reads `MUSIC_STATE_FILE`
at the click, matches current relative audio filenames to the game's actual
`Assets/Resources/ConsoleMusic/catalog.json`, and validates all 17 identities.
It does not rewrite Music state, MP3s, lyrics, Unity Assets, or the game's
preference file. `first`, `second`, and other/unassigned tiers map to 1, 2, and 3.
Within each group, the current saved order is preserved.

The server atomically writes `ConsoleMusic/order-sync-request.json` below the
game's persistent data directory:

```json
{
  "version": 1,
  "requestId": "a fresh lowercase UUID",
  "createdUtc": "UTC ISO timestamp",
  "catalogSha256": "SHA256 of the raw catalog bytes",
  "entries": [
    { "id": "stable catalog ID", "audioSha256": "catalog audio hash", "tier": 1, "order": 0 }
  ]
}
```

`entries` must contain all 17 unique IDs and audio hashes; global orders are
0 through 16, grouped by tiers 1 through 3. The default directory is
`%USERPROFILE%/AppData/LocalLow/DefaultCompany/RandomRealm2/ConsoleMusic`;
`CODEX_CONTROL_RANDOMREALM_MUSIC_STATE_DIR` can select another actual game data
directory. `CODEX_CONTROL_RANDOMREALM_PROJECT_DIR` selects the project catalog.

Writing the file shows **Waiting for the game to apply**. Repeated clicks keep
the same unconsumed request. A later manual click after a terminal receipt
creates a fresh request even when the Console order is unchanged, since the
player may have subsequently reordered or undone it in the game.

`GET /api/randomrealm/music-order-sync?requestId=<UUID>` reports Applied only
when the game writes a matching `order-sync-receipt.json` with version 1,
the same `requestId`, and `status: "applied"`. The game writes this after its
own preference save succeeds; `status: "rejected"` reports failure. Receipt
fields `appliedUtc` and `error` are available to the runtime. Another request's
receipt is ignored. Polling is every 2 seconds only while Pending and the
RandomRealm module is visible; no model automation or update controls are used.

Source validation:

- `python tools/check-randomrealm-music-order-sync.py` exercises real backend
  functions and HTTP guards with temporary fixtures, including reversed current
  order, identity mapping, missing songs, stale receipts, pending repeat clicks,
  and file preservation. It does not import the application or migrate data.
- `node tools/check-randomrealm-music-order-ui.mjs` exercises the real frontend
  functions with deferred save responses, a newer snapshot following rejection,
  the save barrier, retry, a stale status response, and visible-module polling.
- `node tools/check-console-header-controls.mjs` verifies the desktop policy.

These checks cover source behavior. They do not establish installed Console
deployment or a real game receipt; the owning task completes that integration
and deployment separately.
