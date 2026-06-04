#!/usr/bin/env python3
"""
seed_history.py — Retail example: 28-day demo-history backfill.

Populates the monitoring/results BASE tables with a synthetic 28-day narrative
so every dashboard tab tells a coherent "stable -> incident -> recovery" story
across the SAME calendar week:

  * stable    (oldest ~17 days): high accuracy, low flagged %, steady cost
  * incident  (T-10 .. T-7):     accuracy drop, flagged + cost + latency spike,
                                 negative feedback cluster, CRITICAL alerts
  * recovery  (T-6 .. T-0):      metrics recover, incident alerts acknowledged

It is EXAMPLE/demo content (not framework). All object names come from the
merged instance config (no hardcoding). Idempotent: each run first removes its
own rows (hist_% markers / the 28-day window) then re-inserts, so it is safe to
re-run. Does NOT touch anything outside the 28-day demo window.

NOTE: two dashboard tabs (Token Costs, Interaction Quality) must be repointed
from AGENT_TRACES (a view we cannot backdate) to USAGE_METRICS /
INTERACTION_QUALITY_DAILY for this seeded history to render — see dashboard.py.

Run:  SNOWFLAKE_CONNECTION_NAME=<conn> python examples/retail/seed/seed_history.py
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "evaluation"))
from utils import load_config, get_connection  # noqa: E402

# Day-index phase boundaries over a 28-day spine (n = 0 oldest .. 27 = today).
# incident = n in [17,20]  (T-10 .. T-7);  recovery = n >= 21  (T-6 .. T-0).
DAYS = 28

# ---- Narrative CASE fragments (keyed on spine column `n`) ---------------------
AGENT_ACCURACY = """
    CASE
        WHEN n <= 16 THEN 89 + UNIFORM(0, 2, RANDOM())
        WHEN n = 17  THEN 82
        WHEN n = 18  THEN 73
        WHEN n = 19  THEN 69
        WHEN n = 20  THEN 75
        WHEN n = 21  THEN 84
        WHEN n = 22  THEN 87
        WHEN n = 23  THEN 89
        ELSE 90 + UNIFORM(0, 2, RANDOM())
    END"""

SV_ACCURACY = """
    CASE
        WHEN n <= 16 THEN 92 + UNIFORM(0, 2, RANDOM())
        WHEN n = 17  THEN 88
        WHEN n = 18  THEN 84
        WHEN n = 19  THEN 83
        WHEN n = 20  THEN 86
        WHEN n = 21  THEN 89
        ELSE 92 + UNIFORM(0, 2, RANDOM())
    END"""

# Flagged-interaction rate (%) — the Pillar-3 incident signal.
FLAGGED_PCT = """
    CASE
        WHEN n <= 16 THEN 3 + UNIFORM(0, 2, RANDOM())
        WHEN n = 17  THEN 22
        WHEN n = 18  THEN 33
        WHEN n = 19  THEN 37
        WHEN n = 20  THEN 28
        WHEN n = 21  THEN 14
        WHEN n = 22  THEN 8
        ELSE 3 + UNIFORM(0, 2, RANDOM())
    END"""

# Per-request credit cost (cache-aware baseline ~0.13, ~2.5x spike in incident).
CRED_PER_REQ = """
    CASE
        WHEN n <= 16 THEN 0.13
        WHEN n = 17  THEN 0.21
        WHEN n = 18  THEN 0.31
        WHEN n = 19  THEN 0.34
        WHEN n = 20  THEN 0.27
        WHEN n = 21  THEN 0.17
        ELSE 0.13
    END"""

# Per-request input tokens (retries/looping inflate burn during the incident).
INPUT_PER_REQ = """
    CASE
        WHEN n BETWEEN 17 AND 20 THEN 430000
        WHEN n IN (21)           THEN 260000
        ELSE 195000
    END"""

# Request success rate (kept >= 0.84 so Overview's [80,100] chart band is fine).
SUCCESS_RATE = """
    CASE
        WHEN n <= 16 THEN 0.985
        WHEN n = 17  THEN 0.95
        WHEN n = 18  THEN 0.88
        WHEN n = 19  THEN 0.84
        WHEN n = 20  THEN 0.90
        WHEN n = 21  THEN 0.96
        ELSE 0.99
    END"""

AVG_LATENCY = """
    CASE
        WHEN n <= 16 THEN 3400 + UNIFORM(0, 400, RANDOM())
        WHEN n BETWEEN 17 AND 20 THEN 8200 + UNIFORM(0, 1500, RANDOM())
        WHEN n = 21  THEN 5200
        ELSE 3500 + UNIFORM(0, 400, RANDOM())
    END"""

# Feedback arc
NEG_PCT = """
    CASE
        WHEN n <= 16 THEN 7 + UNIFORM(0, 3, RANDOM())
        WHEN n = 17  THEN 25
        WHEN n = 18  THEN 40
        WHEN n = 19  THEN 44
        WHEN n = 20  THEN 30
        WHEN n = 21  THEN 16
        ELSE 7 + UNIFORM(0, 3, RANDOM())
    END"""

AVG_RATING = """
    CASE
        WHEN n <= 16 THEN 4.4
        WHEN n = 17  THEN 3.5
        WHEN n = 18  THEN 2.5
        WHEN n = 19  THEN 2.3
        WHEN n = 20  THEN 3.1
        WHEN n = 21  THEN 4.0
        ELSE 4.4
    END"""

AVG_SENTIMENT = """
    CASE
        WHEN n <= 16 THEN 0.45
        WHEN n BETWEEN 17 AND 20 THEN -0.20
        WHEN n = 21  THEN 0.20
        ELSE 0.45
    END"""

SPINE = f"""
    WITH spine AS (
        SELECT SEQ4() AS n,
               DATEADD('day', SEQ4() - {DAYS - 1}, CURRENT_DATE()) AS day
        FROM TABLE(GENERATOR(ROWCOUNT => {DAYS}))
    )"""


def _exec(cur, label, sql):
    cur.execute(sql)
    try:
        print(f"    {label}: {cur.rowcount} rows")
    except Exception:
        print(f"    {label}: done")


def seed(conn=None):
    cfg = load_config()
    own_conn = False
    if conn is None:
        conn = get_connection("dev")
        own_conn = True

    dev = cfg["environments"]["dev"]
    ev = cfg["eval"]
    db = ev["database"]
    mon = ev["monitoring_schema"]
    res = ev["schema"]
    env = dev["database"]          # environment label used across tables
    agent = dev["agent_short"]
    sv_name = dev["semantic_view"]

    cur = conn.cursor()
    print(f"\n{'='*60}\n  Seeding 28-day demo history ({env})\n{'='*60}")

    # ---- 1. Idempotent cleanup (own rows / 28-day window only) ---------------
    print("\n  [1/8] Clearing prior demo-history rows...")
    win = f"DATEADD('day', -{DAYS}, CURRENT_DATE())"
    _exec(cur, "agent_eval", f"DELETE FROM {db}.{res}.AGENT_EVAL_RUNS WHERE eval_run_id LIKE 'hist_%'")
    _exec(cur, "sv_eval", f"DELETE FROM {db}.{res}.SEMANTIC_VIEW_EVAL_RUNS WHERE eval_run_id LIKE 'hist_%'")
    _exec(cur, "feedback", f"DELETE FROM {db}.{mon}.FEEDBACK_DAILY_SUMMARY WHERE summary_date >= {win} AND environment = '{env}'")
    _exec(cur, "alerts", f"DELETE FROM {db}.{mon}.ALERT_HISTORY WHERE alert_id LIKE 'hist_%'")
    _exec(cur, "usage", f"DELETE FROM {db}.{mon}.USAGE_METRICS WHERE metric_date >= {win}")
    _exec(cur, "quality", f"DELETE FROM {db}.{mon}.INTERACTION_QUALITY_DAILY WHERE summary_date >= {win} AND environment = '{env}'")
    _exec(cur, "health", f"DELETE FROM {db}.{mon}.HEALTH_CHECK_RESULTS WHERE check_id LIKE 'hist_%'")

    # ---- 2. AGENT_EVAL_RUNS ---------------------------------------------------
    print("\n  [2/8] Agent eval runs (accuracy arc)...")
    _exec(cur, "AGENT_EVAL_RUNS", f"""
        INSERT INTO {db}.{res}.AGENT_EVAL_RUNS
            (eval_run_id, environment, agent_name, git_commit_sha, git_branch,
             total_questions, passed_questions, failed_questions, accuracy_pct,
             threshold_pct, passed_threshold, avg_context_relevance,
             avg_groundedness, avg_answer_relevance, run_timestamp, run_details)
        {SPINE}
        SELECT 'hist_agent_' || n, '{env}', '{agent}', 'demo' || n, 'main',
               35, ROUND(35 * acc / 100.0), 35 - ROUND(35 * acc / 100.0), acc,
               85, acc >= 85, ROUND(acc/100.0, 3), ROUND((acc+5)/100.0, 3),
               ROUND(acc/100.0, 3), DATEADD('hour', 9, day::TIMESTAMP_NTZ), NULL
        FROM (SELECT n, day, ({AGENT_ACCURACY}) AS acc FROM spine)
    """)

    # ---- 3. SEMANTIC_VIEW_EVAL_RUNS ------------------------------------------
    print("\n  [3/8] Semantic-view eval runs (milder arc)...")
    _exec(cur, "SEMANTIC_VIEW_EVAL_RUNS", f"""
        INSERT INTO {db}.{res}.SEMANTIC_VIEW_EVAL_RUNS
            (eval_run_id, environment, semantic_view_name, git_commit_sha, git_branch,
             total_questions, passed_questions, failed_questions, accuracy_pct,
             threshold_pct, passed_threshold, run_timestamp, run_details)
        {SPINE}
        SELECT 'hist_sv_' || n, '{env}', '{sv_name}', 'demo' || n, 'main',
               35, ROUND(35 * acc / 100.0), 35 - ROUND(35 * acc / 100.0), acc,
               85, acc >= 85, DATEADD('hour', 8, day::TIMESTAMP_NTZ), NULL
        FROM (SELECT n, day, ({SV_ACCURACY}) AS acc FROM spine)
    """)

    # ---- 4. FEEDBACK_DAILY_SUMMARY -------------------------------------------
    print("\n  [4/8] Feedback daily summary (sentiment arc)...")
    _exec(cur, "FEEDBACK_DAILY_SUMMARY", f"""
        INSERT INTO {db}.{mon}.FEEDBACK_DAILY_SUMMARY
            (summary_date, environment, agent_or_sv_name, total_feedback,
             positive_count, neutral_count, negative_count, avg_rating,
             avg_sentiment_score, negative_pct, feedback_categories, computed_at)
        {SPINE}
        SELECT day, '{env}', '{agent}', tot,
               GREATEST(tot - neg - 1, 0) AS pos, 1 AS neu, neg,
               rating, sent, ROUND(neg * 100.0 / NULLIF(tot, 0), 1),
               OBJECT_CONSTRUCT('accuracy', CASE WHEN neg_pct > 20 THEN neg ELSE 1 END,
                                'completeness', 1, 'presentation', 1, 'usefulness', 1),
               DATEADD('hour', 23, day::TIMESTAMP_NTZ)
        FROM (
            SELECT n, day,
                   (10 + UNIFORM(0, 5, RANDOM()))                  AS tot,
                   ({NEG_PCT})                                     AS neg_pct,
                   ({AVG_RATING})                                  AS rating,
                   ({AVG_SENTIMENT})                               AS sent,
                   GREATEST(ROUND((10 + UNIFORM(0, 5, RANDOM())) * ({NEG_PCT}) / 100.0), 0) AS neg
            FROM spine
        )
    """)

    # ---- 5. USAGE_METRICS (cache-aware, drives Overview + repointed Cost) ----
    print("\n  [5/8] Usage metrics (cost + success arc)...")
    _exec(cur, "USAGE_METRICS", f"""
        INSERT INTO {db}.{mon}.USAGE_METRICS
            (metric_date, environment, service_type, agent_or_sv_name,
             total_requests, successful_requests, failed_requests,
             total_input_tokens, total_output_tokens, total_tokens,
             total_cache_read_tokens, estimated_credits, avg_latency_ms,
             p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
        {SPINE}
        SELECT day, '{env}', 'cortex_agent', '{agent}',
               req, ROUND(req * sr), req - ROUND(req * sr),
               req * inp, req * 410, req * (inp + 410), ROUND(req * inp * 0.8),
               ROUND(req * cpr, 3), lat,
               ROUND(lat * 0.9), ROUND(lat * 1.6), ROUND(lat * 2.0),
               ROUND(req * 0.6)
        FROM (
            SELECT n, day,
                   (70 + UNIFORM(0, 30, RANDOM())) AS req,
                   ({SUCCESS_RATE})                AS sr,
                   ({CRED_PER_REQ})                AS cpr,
                   ({INPUT_PER_REQ})               AS inp,
                   ({AVG_LATENCY})                 AS lat
            FROM spine
        )
    """)

    # ---- 6. INTERACTION_QUALITY_DAILY (drives repointed Quality tab) ---------
    print("\n  [6/8] Interaction quality daily (flagged arc)...")
    _exec(cur, "INTERACTION_QUALITY_DAILY", f"""
        INSERT INTO {db}.{mon}.INTERACTION_QUALITY_DAILY
            (summary_date, environment, agent_name, total_requests, total_threads,
             flagged_requests, flagged_threads, tool_looping_count,
             excessive_steps_count, slow_request_count, high_token_burn_count,
             planning_error_count, single_turn_dropoff_count, rapid_rephrasing_count,
             abandoned_count, critical_count, warning_count, flagged_request_pct, computed_at)
        {SPINE}
        SELECT day, '{env}', '{agent}', req, ROUND(req * 0.7),
               flg, ROUND(flg * 0.6),
               ROUND(flg * 0.1),                                   -- tool_looping
               ROUND(flg * 0.2),                                   -- excessive_steps
               ROUND(flg * 0.1),                                   -- slow_request
               ROUND(flg * 0.4),                                   -- high_token_burn
               ROUND(flg * 0.3),                                   -- planning_error
               0, 0, 0,
               ROUND(flg * 0.3),                                   -- critical
               flg - ROUND(flg * 0.3),                             -- warning
               pct, DATEADD('hour', 23, day::TIMESTAMP_NTZ)
        FROM (
            SELECT n, day, req, pct,
                   GREATEST(ROUND(req * pct / 100.0), 0) AS flg
            FROM (
                SELECT n, day,
                       (70 + UNIFORM(0, 30, RANDOM())) AS req,
                       ({FLAGGED_PCT})                 AS pct
                FROM spine
            )
        )
    """)

    # ---- 7. ALERT_HISTORY (incident criticals; recovery acks; 1 residual) ----
    print("\n  [7/8] Alert history (incident + recovery)...")
    _exec(cur, "ALERT_HISTORY", f"""
        INSERT INTO {db}.{mon}.ALERT_HISTORY
            (alert_id, alert_type, severity, environment, target_name, message,
             metric_value, threshold_value, acknowledged, acknowledged_by,
             acknowledged_at, created_at)
        SELECT * FROM VALUES
            ('hist_alert_1', 'accuracy_below_threshold', 'CRITICAL', '{env}', '{agent}',
             'Agent eval accuracy 69% fell below the 85% gate', 69, 85,
             TRUE, 'oncall@demo', DATEADD('day', -6, CURRENT_TIMESTAMP()), DATEADD('day', -8, CURRENT_TIMESTAMP())),
            ('hist_alert_2', 'high_flagged_rate', 'CRITICAL', '{env}', '{agent}',
             'Flagged-interaction rate spiked to 37% (planning errors + token burn)', 37, 10,
             TRUE, 'oncall@demo', DATEADD('day', -6, CURRENT_TIMESTAMP()), DATEADD('day', -8, CURRENT_TIMESTAMP())),
            ('hist_alert_3', 'cost_spike', 'CRITICAL', '{env}', '{agent}',
             'Per-request credit cost spiked ~2.5x vs baseline', 0.34, 0.18,
             TRUE, 'oncall@demo', DATEADD('day', -5, CURRENT_TIMESTAMP()), DATEADD('day', -7, CURRENT_TIMESTAMP())),
            ('hist_alert_4', 'slow_response', 'WARNING', '{env}', '{agent}',
             'p95 planning latency exceeded 13s during the incident window', 13200, 10000,
             TRUE, 'oncall@demo', DATEADD('day', -5, CURRENT_TIMESTAMP()), DATEADD('day', -7, CURRENT_TIMESTAMP())),
            ('hist_alert_5', 'elevated_latency', 'WARNING', '{env}', '{agent}',
             'Average latency mildly elevated; monitoring', 4100, 4000,
             FALSE, NULL, NULL, DATEADD('day', -2, CURRENT_TIMESTAMP()))
    """)

    # ---- 8. HEALTH_CHECK_RESULTS (current = all HEALTHY) ---------------------
    print("\n  [8/8] Health checks (current snapshot, healthy)...")
    _exec(cur, "HEALTH_CHECK_RESULTS", f"""
        INSERT INTO {db}.{mon}.HEALTH_CHECK_RESULTS
            (check_id, check_name, environment, target_name, status, details, latency_ms, checked_at)
        SELECT * FROM VALUES
            ('hist_health_1', 'agent_availability', '{env}', '{agent}', 'HEALTHY', 'Agent responding normally', 320, CURRENT_TIMESTAMP()),
            ('hist_health_2', 'semantic_view_availability', '{env}', '{sv_name}', 'HEALTHY', 'Semantic view queryable', 210, CURRENT_TIMESTAMP()),
            ('hist_health_3', 'error_rate', '{env}', 'ALL_SERVICES', 'HEALTHY', 'Error rate: 1.2%', 0, CURRENT_TIMESTAMP()),
            ('hist_health_4', 'eval_accuracy', '{env}', '{agent}', 'HEALTHY', 'Latest accuracy 92% >= gate', 0, CURRENT_TIMESTAMP())
    """)

    conn.commit()
    print("\n  Demo history seeded. Set dashboard Time window = 'Last 30 days'.")
    if own_conn:
        conn.close()


if __name__ == "__main__":
    seed()
