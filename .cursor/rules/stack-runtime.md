# Zero-Bloat Stack Runtime (Cursor)

## Core Workflow
- Follow lifecycle in order: spec -> plan -> build -> test -> review -> ship.
- Keep responses concise and implementation-first.
- Prefer small diffs and verifiable steps.

## Tooling Rules
- **All shell commands** (terminal, README, SPEC, Cursor agent runs): MUST invoke via `rtk` as the outer prefix unless the executable *is* `rtk` (e.g. `rtk docker compose up …`, `rtk pytest …`, `rtk bash -lc '…'` when one shell session is intentional). Agents must not omit `rtk`; if `rtk` is missing locally, capture that as a blocker instead of stripping the prefix doc-side.
- Use `n2-qln`, `context-mode`, and `graphify` if installed.
- For architecture questions, refresh graph via `graphify update .`.

## Validation Rules
- Run tests or smoke checks before final response.
- Call out unknowns and failed checks explicitly.
