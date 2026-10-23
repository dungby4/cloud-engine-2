---
title: Repair giftcode confirmation timing
date: 2026-10-23
summary: "Reproduced stale ACK attribution; added paced claims, cooldown retries, reconnect and 20 passing tests."
---

# Repair giftcode confirmation timing

## What happened

Reproduced the old packet handler waking on unrelated broadcast 10 and crediting a delayed ACK 144 to the next current_code. User confirmed all 28 codes remain valid because some accounts claim all 28.

## Decision

Keep the 28-code list, 36 workers, reuse mode, and account storage unchanged. Isolate sequential claims; space sends, respect cooldowns, retry with backoff, and reconnect the same account after an ambiguous timeout because ACK 144 has no request ID. Remove the competing untracked giftcode retry loop. Restore mail delivery grace and log actual missing-code reasons.

## Evidence and next steps

20 tests passed, including actual loopback WebSockets, 36 accounts x 28 codes, send/reconnect failures, bounded cooldown handling, and the full caller reconnect without duplicated hero snapshots. Python syntax and git whitespace checks passed. Review findings resolved; final review found no remaining concrete issues. No live accounts or vault data changed. Next real run must confirm live server behavior after restarting the tool. AgentWiki publish skipped.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
