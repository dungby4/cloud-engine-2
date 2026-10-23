# Giftcode claim timing investigation

## Outcome and scope

Repair intermittent giftcode submission/confirmation with 36 reroll workers.
Keep all 28 codes, reuse mode, account storage, and summon behavior. User confirms
some accounts receive all 28; no evidence for an invalid code list.

Acceptance: unrelated broadcasts cannot release a pending code; ACKs after a
timeout cannot count toward another code; minimum spacing and bounded retries;
cooldown respected; incomplete claims reported accurately; reconnect retains the
same account without duplicating hero snapshots.

## Findings

- Python-only reroll path: `_reroll_single_account` in `chay_web_auto.py`.
- Old path wakes on any packet 10, advances after 0.60 s, and assigns packet 144
  to mutable `current_code`. Minimum spacing after fast ACK is only 0.08 s.
- Executed the old response handler extracted through AST, avoiding import-time
  vault writes: unrelated broadcast sets the event; delayed FIRST ACK after
  advancing current_code confirms SECOND. Both defects reproduced.
- `js/game.js`: `CG_CDK` sends 143 with string; `OB` decodes 144 without fields;
  broadcast decoder `Lt` reads two ints and string. Translation formatter uses
  `||` arguments. These are protocol evidence, not a server rate-limit measurement.

## Changes and verification

- `giftcode_claims.py`: sequential confirmation, minimum spacing, retry/backoff,
  server cooldown, timeout requiring a fresh connection, missing-code reasons.
- Caller renews auth, reconnects the same account, waits for hero snapshot,
  preserves initial inventory counting, removes competing raw giftcode retries,
  restores mail-delivery grace. Existing response fields retained; additive
  `unconfirmedCodes` and `codeErrors` diagnostics.
- Wire tests use actual loopback WebSockets, including 36 independent accounts
  and the full caller reconnect flow. No startup vault migrations run in tests.
- Original isolated repro confirmed before edit. Final full suite: 20 tests
  passed, including caller integration. Syntax and whitespace checks pass.
- Review caught send/reconnect errors escaping retries and unbounded cooldowns;
  fixed with regression tests. Optional websocket dependency fallback preserved
  and checked independently. Final review: no remaining concrete findings.
- One initial spacing assertion used server receipt time; delivery latency can
  shorten that interval even when sends are spaced correctly. Instrumented the
  actual send boundary and enforced the full configured minimum instead.

## Remaining verification

- Live server concurrency/latency behavior still requires next real reroll run;
  no game accounts, vault data, configuration, or running user process changed.
