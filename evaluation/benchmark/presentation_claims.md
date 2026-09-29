# Presentation claims: what the benchmark supports

Source: `report.md`, `results.json`. HEAD `05eb0cb`, model `openai/gpt-oss-120b` in both conditions, 15 cases, 10 incident patterns, 1 run each.

## Safe to say

- "With the **same model**, RecallOps named the *known* historical root cause in **13 of 15** cases (14 of 15 after hand-checking a regex miss); a stateless model did so in **0–1 of 15**." Both recognised the generic failure category (14 vs 15 of 15).
- "RecallOps put a historically successful fix in its recommendations **15/15** times, and as the **first action 15/15**; stateless: 10/15 anywhere, **1/15 first**."
- "On the 7 cases where history contains a fix that **failed** (rollback on pool exhaustion, adding partitions on Kafka lag, restarting pods on cert expiry), stateless recommended the failed fix in **6 of 7** (5 of 7 after we credit one arguable case); RecallOps avoided it **7/7** and raised an explicit warning **7/7**."
- "RecallOps identified the recurrence with the correct occurrence number in **15/15**, named a real past resolver in **15/15**, and retrieved the first expected incident as top hit **15/15**. A stateless model cannot do these (N/A)."
- "RecallOps produced **zero** invented or unsupported historical claims (0/15) — and so did the stateless model, so we make no hallucination claim."
- "Memory is not free: median end-to-end latency was **9.0s vs 4.1s** (p95 15.3s vs 5.4s)."
- All 30 requests succeeded; none degraded; no template fallbacks.

## Say only with the caveat

- **Actionability.** Do NOT claim RecallOps is more actionable. The frozen score (0.93 → 2.13) is inflated by a scorer artifact: 41 of 45 RecallOps actions are bare fix labels like `increase_postgres_pool_size`. With label-only actions treated as non-prose it reverses (A 0.93 vs B 0.33). Accurate framing: "RecallOps recommends the right lever first; Stateless writes more readable but mostly diagnostic advice." The terse label output is a product improvement to make.
- **"15 of 15 wins."** True under the frozen composite (RecallOps wins 15, ties 0, Stateless wins 0), and it held under the post-hoc prose-only variant. But: composite is our own definition, the cases are new occurrences of patterns already in memory, and n=15.
- **Retrieval quality.** "Top hit correct 15/15" but full sibling recall is 0.89 and precision 0.79. C06 (paraphrased alert) dropped to 50% recall; C13/C15 returned mostly unrelated evidence (precision 0.17).

## Do NOT say

- That RecallOps works on **novel, never-seen** incidents. There was no no-history control; every case has a matching pattern in memory (single-incident patterns C09–C15 match the very incident stored).
- That results generalise beyond one model/temperature/run, or give any statistical significance, CI or "X% better" as a population estimate.
- That the five demo alerts are independent evidence — production was calibrated on them (still, the 10 authored cases show the same direction: composite 0.465 vs 0.937).
- That memory reduces hallucination.
- That RecallOps identified the newest root cause every time: C03 cited the older INC-003 cause instead of INC-015's TTL key-prefix mismatch.
- Anything about the feedback-learning loop or reliability under load (other agents' experiments).
