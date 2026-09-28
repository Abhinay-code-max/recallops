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
