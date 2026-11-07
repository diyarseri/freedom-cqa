# Ownership and handoff

Backend owner (this agent): `backend/` — FastAPI, SQLite migrations/repository, organizer adapter, transcript validation/identity, immutable checklist versions, provider adapter, deterministic scoring, evaluations, appeals/reviews. This commit contains the contract only; backend code comes later.

Frontend owner (teammate using Claude Code): `frontend/` — React + TypeScript + Vite, transcript/import controls, checklist editor including scales and N/A conditions, result list/card, evidence navigation, call recording link/player, appeal form and separate reviewer action. No frontend files were created or modified by the backend owner.

Shared interface: `docs/` and `fixtures/`. Coordinate changes to API shape before implementation; backend owns compatibility and the seed, frontend can develop against frozen fixtures now. Do not rename fields/enums in only one implementation. No login screens required. Backend may later configure development CORS for the teammate's Vite origin; organizer calls stay server-side.

Read in this order:
1. `docs/requirements.md` — PDF obligations versus our implementation decisions and unresolved inputs.
2. `docs/api-contract.md` — exact wire types, routes, scores, versioning, failures and review concurrency.
3. `fixtures/README.md` — fixture usage and scenarios.
4. `fixtures/checklist.json`, `fixtures/conversation.json`, `fixtures/evaluation-original.json`, `fixtures/evaluation-reviewed.json`, `fixtures/evaluation-failed.json` — main rendering data.
5. `fixtures/upload-request.json`, `fixtures/organizer-response.json`, `fixtures/error.json` — input/adapter/error shapes.

Teammate may copy fixtures to their mock server; fixtures are shared data, not production results. Use backend IDs for anchors and persist timestamps as strings. Do not implement independent score judgments in the frontend; show server-computed scores. A mock may select the precomputed scenarios. All fixture examples are invented demonstration data, not supplied DEV conversations or verified advice.
