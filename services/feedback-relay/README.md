# Codex Console Feedback Relay

Cloudflare Worker used by Codex Console to accept public feedback without exposing the owner's PC.

## Storage and limits

- D1 stores report text, status, app metadata, and hashed device identifiers.
- R2 stores private PNG/JPEG/WebP screenshots up to 5 MB.
- Raw IP addresses are never stored. An HMAC hash is used only for auxiliary abuse limits.
- Each installation can submit 10 reports per UTC day by default. Each network is capped at 30.
- Turnstile validation is required in production.

## Deploy

1. Run `npm install`.
2. Create a D1 database and R2 bucket, then put their IDs/names in `wrangler.jsonc`.
3. Run `npm run db:remote`.
4. Add Worker secrets with `npx wrangler secret put ADMIN_TOKEN`, `RATE_LIMIT_SECRET`, and `TURNSTILE_SECRET_KEY`.
5. Put the Turnstile public site key in `TURNSTILE_SITE_KEY`.
6. Run `npm run deploy`.
7. Add the resulting HTTPS Worker URL to `feedbackEndpoint` in the public app manifest.

For local development only, set `ALLOW_UNVERIFIED_REPORTS` to `true` in `.dev.vars`. Never use that setting for a public deployment.
