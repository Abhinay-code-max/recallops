"""Builds cases.json + ground_truth.json for the memory-vs-stateless benchmark.

Ground truth is DERIVED from backend/data/seed_incidents.json (fix outcomes, resolvers,
pattern pools, prior-occurrence counts). The only hand-written parts are (a) the 10 authored
alert texts (new occurrences of seeded patterns, not copies of seed log lines), and (b) the
regex matchers that let scoring.py recognise a fix / root-cause concept in free text. Both
are written BEFORE any model output is observed and frozen by hash (see freeze.py).
Model output is never an input to this file.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent.parent / "backend" / "data"
seed = json.loads((DATA / "seed_incidents.json").read_text(encoding="utf-8"))
demo = {a["alert_id"]: a for a in json.loads((DATA / "demo_alerts.json").read_text(encoding="utf-8"))}
by_id = {i["incident_id"]: i for i in seed}

# ---------------------------------------------------------------- fix matchers (free text)
# key = seed fix_type. Regexes are matched case-insensitively against a single action string.
FIX_MATCHERS = {
    "increase_postgres_pool_size": r"(increas|rais|resiz|bump|expand|grow|enlarg).{0,40}(pool|max[_ ]?connections|maximumpoolsize|connection limit)|pool size|max pool",
    "kill_idle_db_connections": r"(kill|terminat|close|drop|clear|free|reap|release).{0,40}(idle|stale|leak|orphan|stuck).{0,30}(connection|session)|pg_terminate_backend",
    "rollback_to_previous_deploy": r"roll ?back|revert (the |this )?(deploy|release|change|version)|redeploy (the )?(previous|prior|last)|previous (version|release|deploy)",
    "restart_payments_pods": r"restart.{0,30}(pod|service|app|instance)|rolling restart|bounce",
    "manual_flush_stale_keys": r"(flush|purge|delete|clear).{0,30}(key|cache|stale|redis)",
    "restart_redis_and_set_eviction_policy": r"eviction|maxmemory-policy|allkeys-lru|volatile-lru",
    "add_ttl_to_job_result_keys": r"\bttl\b|expire|expiry|expiration",
    "fix_ttl_key_prefix_mismatch": r"prefix|ttl.{0,50}(filter|mismatch|cover|miss|exclud)|(filter|mismatch|exclud).{0,50}ttl|dead-?letter",
    "scale_consumer_replicas": r"(scal|add|increas|bump|spin).{0,30}(consumer|replica|instance|worker)|more consumers",
    "increase_topic_partition_count_live": r"(increas|add|expand|repartition|raise).{0,30}partition",
    "manually_renew_and_deploy_certificate": r"renew|rotat.{0,25}(cert|token|credential)|(issue|install|deploy|replace|reissue).{0,25}cert|new cert|cert-manager|certbot",
    "restart_auth_pods": r"restart.{0,30}(pod|service|auth|instance)|rolling restart|bounce",
    "flush_expired_and_stale_sessions": r"(flush|delete|purge|evict|expire|remove|clear|prune|reclaim).{0,40}(session|stale|expired|old key)",
    "set_explicit_session_ttl_cap": r"ttl.{0,30}(cap|limit|max)|(cap|limit).{0,30}ttl|explicit ttl",
    "rollback_image_resize_library_version": r"(roll ?back|revert|pin|downgrad).{0,50}(librar|resize|dependenc|version|image|thumbnail|package)|previous (library|version|dependency)",
    "reindex_with_keyword_subfield_restored": r"reindex|re-index|keyword sub-?field|restore.{0,30}(mapping|field)|(fix|correct|add).{0,20}mapping",
    "reroute_unassigned_shards": r"reroute|retry_failed|allocation.{0,20}retry|retry.{0,20}allocation",
    "disable_feature_flag": r"(disabl|turn(ing)? off|flip.{0,10}off|kill).{0,40}(flag|feature|toggle|rerank|rollout)|(roll ?back|reduc|lower|revert).{0,25}(flag|rollout|percent)|flag.{0,30}(off|0%)",
    "update_webhook_secret_from_vault": r"(updat|rotat|refresh|pull|fetch|sync|replac|load).{0,40}(secret|signing|webhook key|vault)",
}

# ---------------------------------------------------------------- root-cause concept specs
# generic  = coarse symptom-level category (what any competent responder would say from the alert alone)
# specific = the KNOWN root cause recorded in the seed data (needs history or deep insight)
# specific hit: all `required` group indices matched AND >= min_groups groups matched.
RC = {
    "postgres_pool_exhaustion": dict(
        generic=r"pool.{0,40}(exhaust|saturat|full|deplet|starv)|exhaust.{0,40}(pool|connection)|connection.{0,30}(exhaust|slots|limit|leak)|max_connections|too many connections|hikari",
        groups=[r"leak|not (being )?(released|closed|returned)|without releas|never (released|closed|returned)|unreleased|orphan|not releas",
                r"retry|retries",
                r"order[- ]confirmation"],
        required=[0], min_groups=2),
    "redis_oom": dict(
        generic=r"redis.{0,60}(memory|oom|maxmemory|full)|out of memory|maxmemory|used memory",
        groups=[r"\bttl\b|never expire|no expir|without expir|no expiry|expire",
                r"prefix|dead-?letter|order-retry|retry:",
                r"idempotency|retry.?queue|job.?result"],
        required=[0], min_groups=2),
    "kafka_consumer_lag": dict(
        generic=r"consumer.{0,40}(lag|behind|slow|backlog)|lag|backlog|throughput",
        groups=[r"consumer.{0,60}(capacity|throughput|pace|too few|insufficient|not enough|under-?provision|limit|replica)|(replica|consumer).{0,20}(count|number)|parallelism",
                r"traffic|volume|produce rate|producer|surge|spike|load|sale|peak|4x",
                r"autoscal|pre-?scal|scale.{0,15}(ahead|late|delay|slow|in advance)"],
        required=[0], min_groups=2),
    "tls_cert_expired": dict(
        generic=r"cert(ificate)?.{0,30}expir|expired.{0,30}cert|tls|ssl",
        groups=[r"cert-manager|renewal|auto-?renew|renew.{0,30}(fail|broke|stopp|not)|rotation job",
                r"dns-?01|dns challenge|challenge (api )?token|api token|dns api|dns provider"],
        required=[], min_groups=2),
    "redis_oom_session_store": dict(
        generic=r"redis.{0,60}(memory|oom|maxmemory|full)|out of memory|maxmemory|session.{0,20}(store|redis)",
        groups=[r"remember[- ]?me|ttl cap|uncapped|no (explicit )?ttl|without (a |an )?(ttl|expir)|never expir|no expir|unbounded ttl|long-?lived",
                r"accumulat|stale|old(er)? sessions|unbounded|grew|growth|(session )?keys? (grow|build|pile)"],
        required=[0], min_groups=2),
    "k8s_oom_killed_memory_leak": dict(
        generic=r"oom.?kill|memory.{0,30}(leak|growth|exceed|limit)|out of memory",
        groups=[r"leak",
                r"librar|dependenc|resize|thumbnail|native (memory|buffer)|image[- ]?(resize|process)"],
        required=[0], min_groups=2),
    "search_slow_query_missing_index": dict(
        generic=r"(slow|latency).{0,40}(query|search)|mapping|index",
        groups=[r"keyword|sub-?field|not[- ]analy[sz]ed|\.raw|exact-?match field|multi-?field",
                r"mapping",
                r"script|scripted|full[- ]?(index )?scan|fallback|term filter|filter.{0,20}(field|removed|missing)"],
        required=[0], min_groups=2),
    "opensearch_shard_allocation_failed": dict(
        generic=r"shard|unassigned|cluster.{0,20}red|allocation",
        groups=[r"retr(y|ies).{0,40}(exhaust|limit|max)|max_retries|allocation retry|retry limit|retries? (were |was )?exhaust",
                r"transient|prior failure|earlier failure|previous(ly)? failed"],
        required=[0], min_groups=1),
    "bad_feature_flag_regression": dict(
        generic=r"flag|rollout|feature",
        groups=[r"flag|rollout|feature",
                r"expens|heavy|costly|compute|cpu|overload|timeout|latency budget|30\s?s|slow(er)? (query|path|code)"],
        required=[0], min_groups=2),
    "webhook_signature_mismatch": dict(
        generic=r"signature|webhook|secret",
        groups=[r"rotat",
                r"old secret|stale|cached|outdated|previous secret|still (validating|using|verifying)|not (been )?updated"],
        required=[0, 1], min_groups=2),
}

# pattern families that are "related" (same technology, different signature) -- used only to avoid
# penalising evidence precision for sensible neighbours.
RELATED_SIGNATURES = {
    "redis_oom": ["redis_oom_session_store"],
    "redis_oom_session_store": ["redis_oom"],
}

# ---------------------------------------------------------------- authored alerts (10)
AUTHORED = [
    dict(case_id="C06", signature="postgres_pool_exhaustion", service="payments-api", severity="SEV1",
         submitted_at="2026-09-27T15:12:00Z",
         title="Payment confirmations timing out right after the v2.6.3 release",
         symptoms="Since about 12 minutes after the v2.6.3 Friday-afternoon release, payment confirmation calls are timing out and roughly 21% of checkout attempts fail; the API pods are up but requests queue for the database.",
         error_message="HikariPool-1 - Connection is not available, request timed out after 30000ms",
         log_snippet="2026-09-27T15:12:00Z ERROR payments-api [checkout] HikariPool-1 - Connection is not available, request timed out after 30000ms\nactive=20 idle=0 waiting=57 deploy=v2.6.3 (12 min ago)"),
    dict(case_id="C07", signature="redis_oom", service="order-worker", severity="SEV2",
         submitted_at="2026-09-28T06:41:00Z",
         title="Background jobs stalling because Redis keeps refusing writes",
         symptoms="Order-worker jobs are piling up (backlog over 39k) and Redis is rejecting new writes; memory sits near its limit even though the eviction policy was tuned in the past. Delayed order emails are being reported by support.",
         error_message="OOM command not allowed when used memory > 'maxmemory'",
         log_snippet="2026-09-28T06:41:00Z ERROR order-worker [redis-client] OOM command not allowed when used memory > 'maxmemory'.\nredis_used_memory_pct=99.0% queue_depth=39210 maxmemory_policy=allkeys-lru"),
    dict(case_id="C08", signature="kafka_consumer_lag", service="order-worker", severity="SEV1",
         submitted_at="2026-09-28T20:05:00Z",
         title="Order status updates lagging behind purchases during the midnight flash drop",
         symptoms="The flash drop started minutes ago and confirmations are arriving 15+ minutes late; the order-events consumer group cannot keep up with the publish rate. The on-call is considering adding partitions to the order-events topic right now.",
         error_message="consumer group order-processing lag increasing on topic order-events",
         log_snippet="2026-09-28T20:05:00Z WARN order-worker [kafka-consumer-group=order-processing] consumer lag detected partition=2 lag=27400 messages\nthroughput_msgs_sec=610 target_msgs_sec=1500 topic=order-events"),
    dict(case_id="C09", signature="tls_cert_expired", service="auth-service", severity="SEV1",
         submitted_at="2026-09-27T02:44:00Z",
         title="All logins failing with TLS handshake errors on the auth endpoint",
         symptoms="Every client, web and mobile, fails to connect to the auth endpoint with certificate errors since about 02:40 UTC; login and token refresh success rate is 0%.",
         error_message="SSLHandshakeException: PKIX path validation failed: certificate expired",
         log_snippet="2026-09-27T02:44:00Z ERROR auth-service [tls-handshake] javax.net.ssl.SSLHandshakeException: PKIX path validation failed: certificate expired\nendpoint=auth.shipfast.example error_rate=100.0%"),
    dict(case_id="C10", signature="redis_oom_session_store", service="auth-service", severity="SEV1",
         submitted_at="2026-09-28T03:58:00Z",
         title="Users being logged out en masse; session lookups failing overnight",
         symptoms="Auth-service session reads and writes are failing and users are getting signed out; the session Redis instance is at its memory ceiling. This is not Monday morning and no deploy went out.",
         error_message="OOM command not allowed when used memory > 'maxmemory' (session-store)",
         log_snippet="2026-09-28T03:58:00Z ERROR auth-service [session-store] OOM command not allowed when used memory > 'maxmemory'.\nredis_used_memory_pct=100.0% session_keys_total=4390112 oldest_session_age_days=436"),
    dict(case_id="C11", signature="k8s_oom_killed_memory_leak", service="order-worker", severity="SEV1",
         submitted_at="2026-09-27T18:30:00Z",
         title="Worker pods restarting in a loop after a dependency bump",
         symptoms="Since a deploy about 90 minutes ago that bumped the image-processing dependency, order-worker pods are OOMKilled every 20-30 minutes and job throughput is down by more than half.",
         error_message="Pod order-worker OOMKilled: container memory working set reached its limit",
         log_snippet="2026-09-27T18:30:00Z WARN kubernetes [kubelet] Pod order-worker-5d7c OOMKilled reason=Evicted container_memory_working_set_bytes=2147483648\nrestart_count=11 image_resize_lib=v4.3.0"),
    dict(case_id="C12", signature="search_slow_query_missing_index", service="search-api", severity="SEV3",
         submitted_at="2026-09-28T09:20:00Z",
         title="Product listing search suddenly slow after the index mapping migration",
         symptoms="p95 latency for /search/products went from about 110ms to 2.1s right after the catalog mapping migration finished; category pages time out intermittently.",
         error_message="slow_query on catalog index: filter falling back to script_score",
         log_snippet="2026-09-28T09:20:00Z WARN search-api [query-executor] slow_query index=catalog-v3 duration_ms=2144 filter=brand_id:null fallback=script_score\np95_latency=2100ms error_rate=1.5%"),
    dict(case_id="C13", signature="opensearch_shard_allocation_failed", service="search-api", severity="SEV2",
         submitted_at="2026-09-27T13:10:00Z",
         title="Search cluster went RED after a data node restart",
         symptoms="After maintenance restarted one data node, the search cluster status is RED, several primary shards remain unassigned, and about 12% of search requests return partial results.",
         error_message="cluster_status=RED unassigned_shards=4 reason=ALLOCATION_FAILED",
         log_snippet="2026-09-27T13:10:00Z ERROR search-api [opensearch-cluster] cluster_status=RED unassigned_shards=4 index=catalog-v3 reason=ALLOCATION_FAILED"),
    dict(case_id="C14", signature="bad_feature_flag_regression", service="search-api", severity="SEV2",
         submitted_at="2026-09-28T11:15:00Z",
         title="Search timeouts and errors spiked once a new ranking flag reached full rollout",
         symptoms="Right after the enable_semantic_rerank flag was ramped to 100%, search p99 latency exceeded 25s and error rate hit about 38%; traffic levels are normal.",
         error_message="query-executor timeout while feature flag enable_semantic_rerank is active",
         log_snippet="2026-09-28T11:15:00Z ERROR search-api [query-executor] feature_flag=enable_semantic_rerank timeout after 30000ms\np99_latency=25800ms error_rate=38.4% flag_rollout=100%"),
    dict(case_id="C15", signature="webhook_signature_mismatch", service="payments-api", severity="SEV2",
         submitted_at="2026-09-27T09:05:00Z",
         title="Payment gateway callbacks all rejected and orders stuck in pending",
         symptoms="Since about 09:00 UTC every callback from the payment gateway is rejected with a signature verification error; orders remain in 'pending' even though customers were charged.",
         error_message="SignatureVerificationError: webhook signature mismatch",
         log_snippet="2026-09-27T09:05:00Z ERROR payments-api [webhook-handler] SignatureVerificationError: webhook signature mismatch provider=gatewaypay\nrejected_events=188 error_rate=100.0%"),
]

DEMO_MAP = [("C01", "DEMO-1"), ("C02", "DEMO-2"), ("C03", "DEMO-3"), ("C04", "DEMO-4"), ("C05", "DEMO-5")]


def pool_for(signature: str) -> list[dict]:
    return sorted((i for i in seed if i["error_signature"] == signature), key=lambda i: i["timestamp"])


def build() -> tuple[list[dict], dict]:
    cases: list[dict] = []
    for case_id, demo_id in DEMO_MAP:
        a = demo[demo_id]
        cases.append(dict(
            case_id=case_id, source=f"backend/data/demo_alerts.json:{demo_id}",
            demo_tuned=True, pattern_signature=a["error_signature"],
            alert={k: a[k] for k in ("title", "service", "severity", "submitted_at", "symptoms", "error_message", "log_snippet")},
        ))
    for a in AUTHORED:
        cases.append(dict(
            case_id=a["case_id"], source="authored new occurrence of seeded pattern (see build_data.py)",
            demo_tuned=False, pattern_signature=a["signature"],
            alert={k: a[k] for k in ("title", "service", "severity", "submitted_at", "symptoms", "error_message", "log_snippet")},
        ))

    gt: dict = {}
    for c in cases:
        sig = c["pattern_signature"]
        pool = pool_for(sig)
        fix_outcomes: dict[str, dict[str, int]] = {}
        resolvers_worked: dict[str, int] = {}
        for inc in pool:
            for f in inc["fix_attempts"]:
                fo = fix_outcomes.setdefault(f["fix_type"], {"worked": 0, "partial": 0, "failed": 0})
                fo[f["outcome"]] += 1
                if f["outcome"] == "worked":
                    resolvers_worked[f["resolver"]] = resolvers_worked.get(f["resolver"], 0) + 1
        worked = [t for t, o in fix_outcomes.items() if o["worked"] > 0]
        failed = [t for t, o in fix_outcomes.items() if o["failed"] > 0 and o["worked"] == 0]
        related = sorted(i["incident_id"] for s in RELATED_SIGNATURES.get(sig, []) for i in pool_for(s))
        rc = RC[sig]
        gt[c["case_id"]] = dict(
            pattern_signature=sig,
            service=c["alert"]["service"],
            expected_incident_ids=[i["incident_id"] for i in pool],
            related_incident_ids=related,
            prior_occurrences=len(pool),
            expected_occurrence_number=len(pool) + 1,
            known_root_causes={i["incident_id"]: i["root_cause"] for i in pool},
            worked_fixes={t: FIX_MATCHERS[t] for t in worked},
            failed_fixes={t: FIX_MATCHERS[t] for t in failed},
            fix_outcomes=fix_outcomes,
            resolvers_with_worked_fix=sorted(resolvers_worked, key=lambda r: -resolvers_worked[r]),
            primary_resolver=max(resolvers_worked, key=resolvers_worked.get),
            root_cause_generic=rc["generic"],
            root_cause_specific=dict(groups=rc["groups"], required=rc["required"], min_groups=rc["min_groups"]),
        )
    return cases, gt


if __name__ == "__main__":
    cases, gt = build()
    (HERE / "cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    (HERE / "ground_truth.json").write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"wrote {len(cases)} cases")
