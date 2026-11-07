# Backend delivery checkpoints

The implementation branch is based on the committed contract. Only backend/ is changed; frontend/, docs/ and shared fixtures remain untouched.

| Checkpoint | Commit | Runnable behavior | Checks at checkpoint | Blocker |
|---|---|---|---|---|
| 1 | 6a10cd0 | SQLite, uploads/retrieval, stable IDs, atomic organizer normalization | 4 passed | Private signed organizer URL needed for live dataset GET |
| 2 | 2050981 | Exact committed seed; create/edit/version/archive checklists | 6 passed | None for local CRUD |
| 3 | b747cbf | Decimal normalization, N/A/gross-error handling, evidence validation | 19 passed | None for deterministic scores |
| 4 | a2f945d | Real provider adapter, strict structured judgments, bounded repair, queued evaluations, private raw/usage audit | 26 passed with controlled HTTP responses | OPENAI_API_KEY needed for paid call |
| 5 | 38a4177 | Appeals, reviewer reasons, atomic decisions/recalculation, preserved original | 31 passed | None for local review flow |

Final offline validation: **37 passed, 1 live test skipped**; compileall, dependency checks, diff whitespace checks and running Uvicorn HTTP checks also passed. Final operating instructions are in README.md. Additional checks cover malformed provider envelopes, long Retry-After, interrupted evaluations, replacement-criterion configuration and error formatting. Offline HTTP transports exist only in tests; the runtime never substitutes synthetic judgments. A live Uvicorn smoke attempt without a key reached provider_auth and returned no result. This is a confirmed failure path, not a successful paid-model evaluation.

Remaining live verification: configure OPENAI_API_KEY privately, restart the server and run scripts/smoke.py --new-criterion. Configure ORGANIZER_DATASET_URL privately to verify the actual dataset import. No signed URL, real dataset, model response or credential is committed.
