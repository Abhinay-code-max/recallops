# Hindsight API notes

Confirmed by introspecting the installed `hindsight-client==0.10.1` package
(`inspect.signature`, reading `hindsight_client_api` source) and by running every call
below against real Hindsight Cloud — nothing here is guessed. This is what
`backend/app/memory.py` is built on; re-check this file before changing which calls it
makes, per the CLAUDE.md rule "never guess the Hindsight API."

## Package / client

- `pip install hindsight-client` (not `hindsight-api` or `hindsight-ai`).
- `from hindsight_client import Hindsight`
- `Hindsight(base_url: str, api_key: str | None = None, timeout: float = 300.0, user_agent: str | None = None, max_attempts: int = 3)`
  — a **sync** client. It also supports `with Hindsight(...) as client:` (has
  `__enter__`/`__exit__`/`close()`/`aclose()`); without a context manager or explicit
  `close()`, Python warns about an unclosed aiohttp session at interpreter exit (harmless
  in a short script, but our FastAPI app should hold one long-lived client instead of
  opening one per request — see `memory.get_client()`).
- Every sync method (`retain`, `recall`, `reflect`, ...) has an async twin prefixed with
  `a` (`aretain`, `arecall`, `areflect`).

## Banks

- `client.create_bank(bank_id, name=None, mission=None, disposition=None, ...)` →
  `BankProfileResponse`.
- **Confirmed idempotent-by-upsert**: calling `create_bank` again on an existing
  `bank_id` does **not** error — it just updates the profile fields you pass. Verified by
  creating the same bank twice with different `name` values and seeing the second call's
  name win. Safe to call unconditionally on every app startup (`memory.ensure_banks()`).
- `client.delete_bank(bank_id)` — deletes a bank outright. Used this to clean up a
  test memory during development; this is the natural building block for `POST /reset`
  later (spec section 5 lists `/reset` as a required endpoint).

## retain

`client.retain(bank_id, content, timestamp=None, context=None, document_id=None, metadata: dict[str,str]|None=None, entities=None, resolve_entities=None, tags=None, update_mode=None, retain_async=False, operation_id=None) -> RetainResponse(success, bank_id, items_count, operation_id, usage)`

- **`operation_id` is ignored by sync retain.** The method's own docstring says so
  explicitly: *"Optional caller-supplied UUID for idempotent async retries; ignored by
  sync retain."* It only provides idempotency when `retain_async=True`. I initially wrote
  `memory.retain()` to retry with a reused `operation_id`, assuming that made retries
  safe — it doesn't, in sync mode. Caught this from the method's docstring plus a
  `UserWarning` Hindsight itself raises when you pass `operation_id` without
  `retain_async=True`. Fixed: `memory.retain()` does not retry at all; a failure raises
  `MemoryUnavailableError` once rather than risking a duplicate memory.
  `retain_async=True` (with real idempotent retries) is the future path if retain needs
  to be retried.
- Confirmed live: one `retain()` call can produce **more than one** `RecallResult` on a
  later `recall()` — Hindsight splits retained content into multiple memory chunks. In a
  quick test, only the first chunk carried the `metadata` I passed; a second chunk came
  back with `metadata={}` (so `metadata.get("incident_id")` was `None` on it). Anything
  that keys off `metadata["incident_id"]` from recall results should be written expecting
  it can be missing on some chunks of the same retained item, and should be prepared to
  fall back to `document_id` (which *is* stable per retain call).
- `metadata` values must be strings (`dict[str, str]`) — not arbitrary JSON.

## recall

`client.recall(bank_id, query, types=None, max_tokens=4096, budget='mid', trace=False, query_timestamp=None, include_entities=False, max_entity_tokens=500, include_chunks=False, max_chunk_tokens=8192, include_source_facts=False, max_source_facts_tokens=4096, tags=None, tags_match='any', tag_groups=None, prefer_observations=False, min_scores=None, temporal_window=None) -> RecallResponse(results, trace, entities, chunks, source_facts, source_facts_truncated)`

- `RecallResponse.results: list[RecallResult]`. Each `RecallResult` has: `id`, `text`,
  `type`, `entities`, `context`, `occurred_start`, `occurred_end`, `mentioned_at`,
  `document_id`, `metadata`, `chunk_id`, `tags`, `source_fact_ids`, `scores`,
  `attachments`.
- **`RecallResult.scores` is a pydantic model (`RecallScores`), not a dict.** It has
  attributes `.final`, `.reranker`, `.semantic`, `.keyword` — access as `result.scores.final`,
  not `result.scores.get("final")`. Caught this by running a real recall and hitting
  `AttributeError: 'RecallScores' object has no attribute 'get'` — the `dump()`-based
  printing in `scripts/hindsight_smoke.py` shows it as a plain dict (because
  `model_dump()` recursively converts nested models to dicts), which is what led me to
  assume dict access would work on the live object. It doesn't; `model_dump()` output and
  the live object's attribute API are different things.
- `results` come back already ranked by relevance (`scores.final` descending in every
  observed response).

## reflect

`client.reflect(bank_id, query, budget='low', context=None, max_tokens=None, response_schema=None, tags=None, tags_match='any', include_facts=False, include_tool_calls=False, include_tool_call_output=True, tag_groups=None, apply_all_directives=False, fact_types=None, exclude_mental_models=False, exclude_mental_model_ids=None, reflect_search_observations_max_tokens=None, reflect_search_observations_include_entities=None) -> ReflectResponse(text, based_on, structured_output, structured_output_error, usage, trace)`

- `.text` is the natural-language answer, grounded in the bank's memories. In testing,
  it correctly answered a question about a memory retained seconds earlier in the same
  bank.
- `response_schema` exists for structured output but wasn't needed yet.

## HTTP / transport (why memory.py retries recall/reflect but not retain)

- The generated REST layer (`hindsight_client_api.rest`) uses **aiohttp** +
  **aiohttp_retry** under the hood, even for the "sync" client (it runs an event loop
  internally).
- `hindsight_client_api.rest.ALLOW_RETRY_METHODS = {DELETE, GET, HEAD, OPTIONS, PUT, TRACE}`
  — **POST is excluded.** `retain`, `recall`, and `reflect` are all POST under the hood
  (confirmed by grepping `memory_api.py` for `method=`/`resource_path=`:
  `POST /v1/default/banks/{bank_id}/memories`,
  `POST /v1/default/banks/{bank_id}/memories/recall`,
  `POST /v1/default/banks/{bank_id}/reflect`). So the client's built-in retry layer never
  retries any of our three core calls — any retry has to happen in our own wrapper.
  `memory.py` retries `recall`/`reflect` (read-only, safe to repeat) up to 3 times with a
  short backoff, and does **not** retry `retain` (see above).
- HTTP-level errors (4xx/5xx) raise `hindsight_client_api.exceptions.ApiException` or a
  subclass (`BadRequestException`, `UnauthorizedException`, `ForbiddenException`,
  `NotFoundException`, `ServiceException`). Network/timeout failures that happen before
  any HTTP response exists surface as plain `OSError`/`TimeoutError` from the aiohttp
  transport, not `ApiException`. `memory.py` catches `(ApiException, TimeoutError,
  OSError)` as the "Hindsight is unavailable or slow" case (spec section 10), and wraps
  it in `MemoryUnavailableError` for routes to catch and return a graceful response
  instead of freezing.

## What `backend/app/memory.py` actually calls

- `ensure_banks()` → `create_bank` × 4 (`incidents`, `fix-outcomes`, `team`, `baseline`).
- `retain(bank_id, content, ...)` → masks secrets in `content`, then one (non-retried)
  `client.retain(...)` call.
- `recall(bank_id, query, ...)` → up to 3 attempts of `client.recall(...)`, mapped to a
  typed `RecallHit(incident_id, date, relevance, text, metadata)` per result.
- `reflect(bank_id, query, ...)` → up to 3 attempts of `client.reflect(...)`, returns
  `.text`.

## Verified behaviours

Live-tested against real Hindsight Cloud in a throwaway bank (`smoke-verify-<random>`,
created and `delete_bank`-ed within the same run). Nothing below is inferred from docs —
every claim was observed in a script run.

### 1. `timestamp` → `occurred_start` / `mentioned_at`

Retained with `timestamp=datetime(2026, 5, 15, 14, 32, 10)`. Recall showed:
- `occurred_start = 2026-05-15T00:00:00+00:00` — **date-truncated to midnight UTC**, time
  of day is dropped.
- `mentioned_at = 2026-05-15T14:32:10+00:00` — **exact timestamp preserved**.

So the event *date* lands correctly (via `occurred_start`), but not the time. This is
why Step B keeps the full timestamp in the retained *text* regardless (via the existing
`Date: <iso> | ...` prefix) rather than relying on `occurred_start` for anything more
precise than day-level dates.

### 2. `update_mode`: allowed values, replace vs. append

Allowed values (from `hindsight_client_api.models.memory_item.py`'s
`update_mode_validate_enum`, source-read, not the docstring): **`'replace'` and
`'append'`** — no third option.

- **`replace`**: retained content A, then content B with the same `document_id` and
  `update_mode="replace"`. Recall only returned B's content — A was gone, no duplicate.
- **`append`**: same pattern with `update_mode="append"`. Recall returned **both** A's
  and B's content as separate memory chunks — duplicates by design.
- Observed in both cases: `metadata` on recall reflected the **latest** retain call's
  metadata even for the *older* chunk still present after an append (both the "ALPHA"
  and "BETA" append chunks came back with `metadata={'v': 'BETA'}`). Metadata appears to
  be associated with the `document_id`, not the individual chunk, regardless of
  `update_mode` — but see the metadata-coverage caveat in point 5 below; this wasn't
  reproduced enough times to treat as a hard guarantee.

**Step B uses `update_mode="replace"`** for seeding so `POST /seed` is idempotent
without needing to delete/recreate banks (see below).

### 3. No single-document/memory delete

Confirmed by introspecting both the friendly `Hindsight` class and the raw
`MemoryApi` (`hindsight_client_api.api.memory_api`): no `delete_document`,
`delete_memory`, or anything with a `memory_id`/`document_id` delete parameter exists.
The only deletion-shaped calls are:
- `delete_bank(bank_id)` — deletes an entire bank.
- `clear_bank_memories(bank_id, type=None)` — bulk-clears a bank's memories, optionally
  filtered by fact `type` (`world`/`experience`/`observation`) only — **no document_id or
  memory_id filter**, so it can't target one document either.

This directly drives Step B: **live-created memories (feedback, chat, postmortems) go in
a separate `recallops-live` bank**, since there's no way to delete just the live ones out
of a mixed bank; `POST /reset` deletes and recreates that one bank, `recall` merges its
results with the seeded banks.

### 4. Latency (seconds, single real-Hindsight-Cloud run; expect variance)

| call | observed |
|---|---|
| `retain` (one incident-sized text) | 1.97s (another run: 8.03s) |
| `recall(budget="low")` | 1.24s (another run: 4.32s, 0.38s) |
| `recall(budget="mid")` | 0.38s (another run: 0.46s, 0.37s) |
| `reflect` | 3.22s (another run: 3.61s, 3.73s) |

Latency is noticeably variable run-to-run (retain ranged ~2–8s), so `memory.py`'s ~12s
total-including-retries cap (Step B) is deliberately generous relative to a single
typical call.

**Concurrency — this is the important finding.** 4 concurrent `retain()` calls:

- **Raw `ThreadPoolExecutor` sharing ONE sync `Hindsight` client instance: fails every
  time**, reproduced twice: `RuntimeError: Timeout context manager should be used inside
  a task`. Root cause, confirmed by reading `hindsight_client.hindsight_client._run_async`
  source (not guessed): the sync wrapper does
  `loop = asyncio.get_event_loop(); loop.run_until_complete(coro)` on every call, and the
  underlying aiohttp `ClientSession` is created lazily, bound to whichever event loop is
  "current" the first time it's used. **This isn't just a thread-pool problem** — in one
  run, a sync `client` that had already been used successfully for several synchronous
  calls broke on a *later* call with the exact same error, purely because `asyncio.run()`
  had been called elsewhere in the same process in between (which creates, uses, and
  tears down its own loop). Any time the process's "current" event loop changes out from
  under a previously-used sync client, that client's session can break.
- **`ThreadPoolExecutor`, one fresh `Hindsight` client instance per thread: works.**
  4/4 succeeded, 2.29–3.14s each, 3.15s wall clock.
- **`asyncio.gather` over the native async twins (`aretain`), one client instance, all
  within a single `asyncio.run()`/event loop: works cleanly.** 4/4 succeeded,
  2.01–3.29s each, 3.30s wall clock.

**Step B/`memory.py` uses the async twins (`aretain`/`arecall`/`areflect`) with
`asyncio.gather`**, not a thread pool: FastAPI already runs one event loop per worker, so
this is the natural fit, avoids the cross-loop breakage above entirely, and doesn't
throw away connection pooling the way "new client per thread" does.

### 5. Metadata coverage across chunks; `document_id` fallback

Retained one structured incident text (~10 lines, matching the real seed `text` shape) —
it split into 3 memory chunks on recall. **All 3 chunks carried the full `metadata` dict**
passed at retain time (`incident_id`, `service`, `severity` all present on each). Two
other test documents retained *without* an `incident_id` key in their metadata correctly
showed `metadata.get("incident_id") is None` on recall, and **`document_id` was present
and correct on every single result across every test in this run, with no exceptions** —
confirming `document_id` (stripping the `"incident-"` prefix) is a fully reliable
fallback for mapping a recall hit back to an incident ID.

Caveat: an earlier, less rigorous ad-hoc check (2-sentence content, 2 resulting chunks)
saw one chunk come back with `metadata={}` while the other had the full dict — so
metadata-per-chunk propagation is *not* guaranteed 100% of the time in every case, even
though this run's more realistic (longer, structured) content didn't reproduce it. The
practical rule either way: **prefer `metadata.get("incident_id")`, always fall back to
`document_id`, never assume metadata is present.**

### 6. `delete_bank` consistency

Not perfectly immediate in one observation: a `recall` against a bank issued right after
`delete_bank` on that same bank returned successfully (no error) in one run. A separate,
isolated check with a couple of real calls in between `delete_bank` and the next `recall`
correctly raised `hindsight_client_api.exceptions.NotFoundException` (`404`,
`"Bank '<id>' not found"`). Treat `delete_bank` as not-guaranteed-instantly-consistent:
code that deletes-then-immediately-recreates a bank (like `/reset`) shouldn't assume the
delete is visible to the very next call.
