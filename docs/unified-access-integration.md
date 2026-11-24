# Unified access integration — phase 1

Baseline: Console main 6c6c6cf5f1e56b11f61d81d0ba74eb479c411639; Vision main 43ad77c7cfbdfb7f2a0c2501245a09d5266b07c1 (observed 2026-11-24).

## Product contract
One Windows product: Console owns desktop/mobile UX, workspaces and release lifecycle; Vision supplies a local capability broker. Keep legacy installations and data intact until migration is tested. Do not copy private settings, credentials, or source between repositories without ownership/licensing review.

## Installer and update
Reuse Console release pipeline, manifest and installer. A one-command bootstrap must resolve an approved release, verify a pinned digest and trusted publisher signature, then invoke Setup with explicit user consent. No remote script piped to Invoke-Expression. No automatic authorization of external AI clients. Stable and development channels must have separate approved artifacts; do not install arbitrary main commits. Update only when work is idle; back up data, verify version and runtime health, and roll back on failed health checks. Preserve existing Console-only update/settings placement. No production release from this branch.

## Broker boundary
Versioned capability discovery and health protocol, initially read-only. Local authenticated IPC, default-deny grants per device/client/capability; no LAN exposure by default. Screen, UI control, browser, filesystem and shell permissions separate. Explicit approvals for sensitive actions; logs redact secrets. ChatGPT Normal Chat, Work and Codex are independent client integrations; platform availability and approval cannot be overridden.

## First acceptance gates
1. Reconcile Console commit label 1.2.0, source manifest 1.1.52, and latest released tag v1.1.51; confirm intentional version policy before publishing.
2. Reconcile Vision installer target v1.0.0 and required plugin manifest 1.5.0; verify existing installation compatibility.
3. Test bootstrap rejection of missing digest, invalid digest, mismatched signature, wrong publisher, and unsupported Windows architecture.
4. Verify clean install, upgrade with existing data, busy-work deferral, interrupted install, rollback, and uninstall on isolated test profiles.
5. Test broker discovery without executing commands, then permission denial/revocation and each explicitly granted capability.
6. Verify independently in each supported AI client; record unsupported routes honestly.
7. Run existing Console quality and security suites plus Vision tests before any merge.

## Team workflow
Use separate feature branches and reviewed pull requests; preserve main. Console maintainer owns release/UX review, Vision maintainer owns broker contract, QA owns 0Ping isolated acceptance. Ownership assignments are proposed pending team agreement. No public redistribution of the other project's code until licensing is agreed.
