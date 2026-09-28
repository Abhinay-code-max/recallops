"""Single wrapper for all Groq LLM calls.

Scaffold only. Per CLAUDE.md, every LLM call in this app must go through this module:
retry on transient failure, strip any reasoning/thinking text from the response,
repair/parse JSON when structured output is expected, then fall back from
LLM_MODEL_PRIMARY to LLM_MODEL_FALLBACK if the primary model still fails.
No other module should import groq directly.
"""
