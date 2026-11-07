# CQA backend

FastAPI + SQLite implementation of `docs/api-contract.md`. No frontend files or contract fields are changed. Python 3.11+; one API process with two asynchronous evaluation workers. All API paths start `/api/v1`. Browser API documentation is at `http://127.0.0.1:8000/docs` once started.

## Install and run (from repository root)

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
# Edit backend/.env locally; keep credentials private.
backend/.venv/bin/python -m uvicorn backend.app.server:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Windows: substitute `backend\.venv\Scripts\python.exe` for `backend/.venv/bin/python`; copy `.env.example` with your editor or PowerShell `Copy-Item`. Shell activation is optional. The server reads `backend/.env` without overriding already configured environment variables. Use a persistent local filesystem for DATABASE_PATH, not a temporary container layer. Defaults assume running from the repository root. Vite's default `http://localhost:5173` origin is enabled; set CORS_ORIGINS to a comma-separated exact-origin list if needed.

For OpenAI evaluation, OPENAI_API_KEY is required. Default OPENAI_MODEL is `gpt-5.4-mini-2026-03-17` against OpenAI's HTTPS Chat Completions endpoint. It supports structured outputs. No mock provider can be enabled by environment variables. The previous candidate GPT-4.1 mini is marked deprecated in current official docs, so it is not the default. Unsupported models fail explicitly, never trigger an automatic model switch. The model ID saved in the Evaluation is the requested model; the actual returned model, request ID, raw response, and usage are retained in private `provider_calls` audit records.

### Free local evaluation with Ollama on Windows

Ollama runs locally and uses the NVIDIA GPU, so it needs no API key or per-call payment. Install [Ollama for Windows](https://ollama.com/download/windows), then open a new PowerShell window and download the recommended model:

```powershell
ollama pull qwen3:8b
```

The model is approximately 5.2 GB and supports more than 100 languages and dialects. It fits this project's 16 GB RAM / RTX 4050 development machine, though local quality and speed must be measured against representative RU, KZ and EN transcripts. Keep Ollama running in the system tray. Confirm it is available with `ollama list`.

Set these values in `backend/.env`:

```env
MODEL_PROVIDER=ollama
OPENAI_API_KEY=
OPENAI_MODEL=qwen3:8b
OPENAI_BASE_URL=http://127.0.0.1:11434
PROVIDER_TIMEOUT_SECONDS=120
MAX_OUTPUT_TOKENS=8000
```

Restart the backend after changing `.env`, then run the same smoke command. The adapter calls Ollama's native `/api/chat` with a JSON schema, disables thinking for predictable structured output, records token counts, and reports estimated cost as null because local inference has no provider token charge. For security, `MODEL_PROVIDER=ollama` accepts plain HTTP only on `127.0.0.1` or `localhost`; it cannot send transcripts to a remote HTTP host. Official references: [Windows support](https://docs.ollama.com/windows), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), and [Qwen3 8B](https://ollama.com/library/qwen3:8b).

Required only for organizer imports: ORGANIZER_DATASET_URL. Copy the exact signed button hyperlink from student-guide PDF p. 3 into the server-side secret, never a frontend variable or tracked file. The adapter preserves query values and changes only group_id; it does not guess organizer routes. Import is a server-side GET, solving browser CORS. The supplied DEV description is not used as a hardcoded record-count restriction.

## First end-to-end evaluation

After configuring the key and starting the server:

```bash
backend/.venv/bin/python backend/scripts/smoke.py --new-criterion
```

This command uses synthetic fixture text, saves a checklist containing a new criterion, uploads a transcript, requests a **real** model evaluation, polls to completion, submits an appeal, and confirms the original judgment with a reviewer reason. It checks original preservation and that an appeal alone cannot change scores. It prints only IDs/status/model/total and exits nonzero on failure. This spends model tokens (one call normally, two maximum). It does not assume a particular AI score. To use exactly the seed, omit `--new-criterion`. For an existing evaluation or organizer dataset, use the interactive `/docs` page or the exact requests in the committed API contract.

The separate paid integration test is opt-in:

```bash
cd backend
RUN_LIVE_MODEL_TEST=1 .venv/bin/python -m pytest tests/test_live.py -q
```

On Windows set RUN_LIVE_MODEL_TEST in your process environment first. Run this only with either a configured OpenAI key or the local Ollama settings above; failures stay failures. Offline tests use HTTP mock transports injected by Python tests only, not an application fallback.

## Tests

From repository root:

```bash
cd backend
.venv/bin/python -m pytest -q
```

Focused tests cover persisted source/message identity, timestamp preservation, atomic import rollback, exact seed, immutable versions, scale/N/A validation, Decimal normalization/half-up rounding, zero versus null totals, gross-error isolation, evidence references/ranges, newly configured criteria, provider HTTP failures/timeouts/repair limits, original/raw-output persistence, appeals, concurrent revision conflicts and reviewer recalculation. The live test is skipped by default and must not be described as a successful paid-model evaluation when skipped.

## Execution and validation details

- `POST /evaluations` persists queued state and returns 202 before a worker can finish. Poll the Location header. Two workers bound provider concurrency; pending IDs are held in memory with their attempts persisted in SQLite.
- Each evaluation has a shared **two-call budget**: initial call, then either one transport retry or one repair for malformed/invalid judgments. No SDK/HTTP retries beyond these. Auth errors and nonretryable request errors fail immediately. One failure does not kill the worker.
- Each provider attempt has a configurable wall-clock deadline (default 45 seconds, capped at 180), plus HTTP timeouts. Use 120 seconds for the recommended local model because first load is slower. A 0.25-second delay normally separates calls. Retry-After is honored up to two seconds; a longer value stops the attempt with an explicit retryable failure instead of retrying too early. No unbounded Retry-After sleeps or credential rotation. Organizer requests use a 20-second wall-clock deadline and HTTP timeout (configurable up to 60), zero retries and no redirects.
- The exact saved checklist snapshot, including arbitrary new criteria, scale anchors and N/A conditions, goes to the provider. All transcript roles remain evidence; the operator alone is evaluated. Transcript and rejected-provider content are separate untrusted JSON user data. The adapter has no tools or URL fetching.
- Validate criterion completeness/uniqueness, answer type, exact numeric step, N/A permission, nonblank rationale, evidence existence and ordered inclusive ranges. For missing actions, the prompt requires an inspected range. Whether the rationale truly establishes an omission/N/A condition or proves a factual consultation is a semantic judgment for the model/reviewer, not something ID validation can prove. No confidence or invented business-policy database is supplied.
- Scoring is a separate Decimal function; provider JSON cannot supply totals. Reviewer changes invoke the same calculator pinned to the original checklist version. No special handling of c01–c08 is used in the calculator.
- Only one server process (`--workers 1`) may own this prototype database. On startup/shutdown interrupted queued/running attempts become failed, with null results and an explicit provider_unavailable error. No potentially billed request is replayed automatically; submit a new evaluation to retry. Completed evaluations and reviews persist. Do not run multiple API processes against this database.
- SQLite schema_version is 1. Startup creates the schema and seeds only if absent; it does not overwrite existing seed versions or unarchive them. Foreign keys, unique source/appeal keys and BEGIN IMMEDIATE transactions protect writes and compare-and-save revisions. No database lock is held across provider calls.
- Original AI score/judgments and raw provider envelopes remain unchanged after reviews. Every provider call, including rejected output and repairs, has a private audit entry. Read metadata locally using the command below; no extra public metadata route or contract fields were added.

## Model identity, usage and estimated cost

Local Ollama inference has **$0 provider token cost**; electricity and hardware use are not estimated. For the optional OpenAI path, pricing was verified **2026-11-07** against the [official GPT-5.4 mini model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini) and [OpenAI pricing](https://developers.openai.com/api/docs/pricing): standard text rates per million tokens are **$0.75 input**, **$0.075 cached input**, **$4.50 output**. Default OpenAI snapshot: `gpt-5.4-mini-2026-03-17`. These are standard global endpoint estimates; no Batch/Flex/priority/regional surcharges are assumed. Reverify rates before the demonstration if pricing or provider changes.

For every call, cost = `((prompt_tokens - cached_tokens)*0.75 + cached_tokens*0.075 + completion_tokens*4.50)/1_000_000`. Sum **all calls**, including rejected generations, retries with usage, and repair. Completion usage includes any billed reasoning tokens; do not add them again. Unknown usage, unknown models, custom base URLs or calls interrupted without reported usage give null cost, never fabricated zero. Partial known costs do not establish a complete evaluation bill.

Illustrative budget, not measured usage: 6,000 uncached prompt + 1,500 completion tokens ≈ **$0.01125/evaluation**. If repair uses another 8,000 prompt + 1,500 completion tokens, the combined estimate is **$0.02400/evaluation**. 65 such evaluations ≈ $0.73 without repairs or $1.56 if all need that repair. Real transcript lengths/output lengths vary and a failed network request may still have been billed. This is not a spending cap. No model cost has been measured until a real configured run completes.

```bash
backend/.venv/bin/python -m backend.app.audit EVALUATION_ID --database backend/data/cqa.sqlite3
```

The summary includes per-call requested/returned model, usage and combined estimated cost. For compatibility, rates for the deprecated GPT-4.1 mini snapshot/alias are also recorded ($0.40/$0.10/$1.60 per million input/cached/output tokens), verified against its official model page; no other model price is guessed.

## Private data and prototype boundary

`backend/.env`, `backend/data/`, SQLite files and local caches are ignored by Git. Do not put imports, real transcripts, audio, provider outputs or credentials in source control. Keep the database on private storage; its audit rows contain model output and may contain personal information. Run with no access log; application errors never return upstream response bodies, signed URLs, stack traces, API keys or transcript inputs. OpenAI mode sends transcripts to OpenAI with `store=false`; provider retention policies still apply. Ollama mode keeps model inference on the local machine. No audio is downloaded: audio_url is returned as source data, and ISO timestamps are never treated as seek offsets.

The PDF explicitly requires no demo authentication. Default bind is loopback; deployment/authentication/production queueing are outside this backend implementation. The code does not publish a website or send organizer messages. The public GitHub repository contains only synthetic fixtures and implementation files.
