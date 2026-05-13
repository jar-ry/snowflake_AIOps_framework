#!/usr/bin/env python3
"""
seed_dashboard_data.py
Populate monitoring tables with realistic synthetic data so every Streamlit
dashboard tab renders meaningful charts immediately after bootstrap.

Idempotent — truncates tables before insert.

Usage:
    SNOWFLAKE_CONNECTION_NAME=COCO_demo_connection python demo/seed_dashboard_data.py
    python demo/seed_dashboard_data.py --days 14 --env dev
    python demo/seed_dashboard_data.py --no-clean       # append instead of truncate
"""
import argparse
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

import snowflake.connector


AGENT_FQN = "RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT"
SV_FQN = "RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV"

POSITIVE_FEEDBACK = [
    "Answer was spot on, exactly what I needed.",
    "Fast and accurate, great work.",
    "Loved the breakdown by segment.",
    "Really useful for my weekly report.",
    "Saved me 30 minutes, thanks!",
]
NEUTRAL_FEEDBACK = [
    "Answer was fine but could be more detailed.",
    "Took a few tries to get what I wanted.",
    "Decent, not great.",
    "Correct numbers but the phrasing was odd.",
]
NEGATIVE_FEEDBACK = [
    "Got the wrong customer segment entirely.",
    "Returned stale data from last quarter.",
    "Refused to answer a valid question.",
    "Numbers didn't match my manual calculation.",
    "Too slow, gave up after 30 seconds.",
]
CATEGORIES = [
    "incorrect_answer",
    "slow_response",
    "refused_valid",
    "safety_concern",
    "other",
]


def get_connection():
    if os.getenv("SNOWFLAKE_ACCOUNT") and os.getenv("SNOWFLAKE_USER"):
        kwargs = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
        }
        if os.getenv("SNOWFLAKE_PASSWORD"):
            kwargs["password"] = os.getenv("SNOWFLAKE_PASSWORD")
        if os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"):
            from cryptography.hazmat.primitives import serialization
            with open(os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"), "rb") as f:
                pk = serialization.load_pem_private_key(f.read(), password=None)
            kwargs["private_key"] = pk.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        return snowflake.connector.connect(**kwargs)

    conn_name = os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    toml_path = os.path.expanduser("~/.snowflake/connections.toml")
    if os.path.exists(toml_path):
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        conn_config = config.get(conn_name, {})
        if conn_config.get("private_key_path"):
            from cryptography.hazmat.primitives import serialization
            with open(os.path.expanduser(conn_config["private_key_path"]), "rb") as f:
                pk = serialization.load_pem_private_key(f.read(), password=None)
            return snowflake.connector.connect(
                connection_name=conn_name,
                private_key=pk.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                ),
            )
    return snowflake.connector.connect(connection_name=conn_name)


def log(msg):
    print(f"  {msg}")


def truncate_tables(cur):
    log("Truncating monitoring tables...")
    tables = [
        "RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK",
        "RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS",
        "RETAIL_AI_EVAL.MONITORING.USAGE_METRICS",
        "RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS",
        "RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY",
        "RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY",
        "RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY",
        "RETAIL_AI_EVAL.RESULTS.SEMANTIC_VIEW_EVAL_RUNS",
        "RETAIL_AI_EVAL.RESULTS.AGENT_EVAL_RUNS",
    ]
    for t in tables:
        cur.execute(f"TRUNCATE TABLE IF EXISTS {t}")
    log(f"Truncated {len(tables)} tables.")


def seed_usage_metrics(cur, days, env):
    log(f"Seeding USAGE_METRICS ({days} days x 2 services)...")
    today = date.today()
    rows = []
    for i in range(days):
        d = today - timedelta(days=days - i)
        weekday = d.weekday()
        weekend_factor = 0.4 if weekday >= 5 else 1.0
        trend = 1.0 + (i / days) * 0.5

        for service_type, target in [
            ("cortex_agent", AGENT_FQN),
            ("cortex_analyst", SV_FQN),
        ]:
            base_req = int(random.randint(80, 120) * weekend_factor * trend)
            failed = int(base_req * random.uniform(0.02, 0.08))
            success = base_req - failed
            in_tokens = base_req * random.randint(600, 900)
            out_tokens = base_req * random.randint(200, 400)
            total_tokens = in_tokens + out_tokens
            est_credits = round(total_tokens * 0.000003, 4)
            avg_lat = random.uniform(1800, 4500)
            rows.append((
                d.isoformat(), env, service_type, target,
                base_req, success, failed,
                in_tokens, out_tokens, total_tokens,
                est_credits,
                avg_lat,
                avg_lat * 0.85, avg_lat * 1.6, avg_lat * 2.2,
                random.randint(8, 25),
            ))

    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
           (metric_date, environment, service_type, agent_or_sv_name,
            total_requests, successful_requests, failed_requests,
            total_input_tokens, total_output_tokens, total_tokens,
            estimated_credits, avg_latency_ms,
            p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} USAGE_METRICS rows.")


def seed_user_feedback(cur, days, env):
    log("Seeding USER_FEEDBACK (50 rows)...")
    queries = [
        "What is our total revenue?",
        "How many customers do we have?",
        "Show top 5 products by revenue",
        "Return rate by category?",
        "Compare revenue across segments",
        "Top customers this month",
        "Shipping method performance",
        "Monthly sales trend",
    ]
    rows = []
    for _ in range(50):
        r = random.random()
        if r < 0.70:
            rating = random.choice([4, 5])
            text = random.choice(POSITIVE_FEEDBACK)
            sentiment = round(random.uniform(0.4, 0.9), 2)
            category = None
        elif r < 0.90:
            rating = 3
            text = random.choice(NEUTRAL_FEEDBACK)
            sentiment = round(random.uniform(-0.1, 0.3), 2)
            category = "other"
        else:
            rating = random.choice([1, 2])
            text = random.choice(NEGATIVE_FEEDBACK)
            sentiment = round(random.uniform(-0.9, -0.3), 2)
            category = random.choice(CATEGORIES[:3])
        created = datetime.now() - timedelta(
            days=random.randint(0, days - 1),
            hours=random.randint(0, 23),
        )
        rows.append((
            env, "agent", AGENT_FQN,
            random.choice(queries), "Agent response text...",
            rating, text, category, sentiment,
            created.strftime("%Y-%m-%d %H:%M:%S"),
        ))

    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
           (environment, source, agent_or_sv_name, user_query, agent_response,
            feedback_rating, feedback_text, feedback_category, sentiment_score,
            created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} USER_FEEDBACK rows.")


def seed_feedback_daily_summary(cur, days, env):
    log(f"Seeding FEEDBACK_DAILY_SUMMARY ({days} days)...")
    today = date.today()
    rows = []
    for i in range(days):
        d = today - timedelta(days=days - i)
        total = random.randint(4, 12)
        pos = int(total * random.uniform(0.55, 0.80))
        neg = int(total * random.uniform(0.05, 0.20))
        neu = max(0, total - pos - neg)
        neg_pct = round(neg * 100.0 / total, 2) if total else 0.0
        avg_rating = round(
            (pos * 4.5 + neu * 3.0 + neg * 1.5) / total, 2
        ) if total else 0.0
        avg_sentiment = round(random.uniform(0.2, 0.6), 2)
        categories_json = json.dumps({
            "incorrect_answer": max(0, neg - 1),
            "slow_response": 1 if neg else 0,
            "other": neu,
        })
        rows.append((
            d.isoformat(), env, AGENT_FQN,
            total, pos, neu, neg,
            avg_rating, avg_sentiment, neg_pct,
            categories_json,
        ))

    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY
           (summary_date, environment, agent_or_sv_name,
            total_feedback, positive_count, neutral_count, negative_count,
            avg_rating, avg_sentiment_score, negative_pct, feedback_categories)
           SELECT column1, column2, column3, column4, column5, column6, column7,
                  column8, column9, column10, PARSE_JSON(column11)
           FROM VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} FEEDBACK_DAILY_SUMMARY rows.")


def seed_eval_runs(cur, env):
    log("Seeding SEMANTIC_VIEW_EVAL_RUNS (3 runs)...")
    today = date.today()
    sv_rows = []
    for i, (days_ago, acc) in enumerate([(14, 80.0), (7, 85.0), (1, 87.5)]):
        ts = datetime.now() - timedelta(days=days_ago)
        passed = int(30 * acc / 100)
        sv_rows.append((
            env, SV_FQN, "demo-commit-" + str(i), "main",
            30, passed, 30 - passed, acc, 60.0, acc >= 60.0,
            ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.RESULTS.SEMANTIC_VIEW_EVAL_RUNS
           (environment, semantic_view_name, git_commit_sha, git_branch,
            total_questions, passed_questions, failed_questions,
            accuracy_pct, threshold_pct, passed_threshold, run_timestamp)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        sv_rows,
    )

    log("Seeding AGENT_EVAL_RUNS (3 runs)...")
    agent_rows = []
    for i, (days_ago, acc) in enumerate([(14, 82.0), (7, 86.0), (1, 87.6)]):
        ts = datetime.now() - timedelta(days=days_ago)
        passed = int(35 * acc / 100)
        agent_rows.append((
            env, AGENT_FQN, "demo-commit-" + str(i), "main",
            35, passed, 35 - passed, acc, 60.0, acc >= 60.0,
            round(random.uniform(0.80, 0.92), 3),
            round(random.uniform(0.85, 0.95), 3),
            round(random.uniform(0.82, 0.90), 3),
            ts.strftime("%Y-%m-%d %H:%M:%S"),
        ))
    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.RESULTS.AGENT_EVAL_RUNS
           (environment, agent_name, git_commit_sha, git_branch,
            total_questions, passed_questions, failed_questions,
            accuracy_pct, threshold_pct, passed_threshold,
            avg_context_relevance, avg_groundedness, avg_answer_relevance,
            run_timestamp)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        agent_rows,
    )
    log(f"Inserted {len(sv_rows)} SV + {len(agent_rows)} Agent eval runs.")


def seed_health_checks(cur, days, env):
    log(f"Seeding HEALTH_CHECK_RESULTS ({days} days x 3 checks)...")
    checks = [
        ("agent_responds", AGENT_FQN),
        ("analyst_generates_sql", SV_FQN),
        ("error_rate", "ALL_SERVICES"),
    ]
    today_dt = datetime.now()
    rows = []
    for i in range(days):
        for check_name, target in checks:
            ts = today_dt - timedelta(days=days - i, hours=random.randint(0, 5))
            r = random.random()
            if r < 0.85:
                status, details = "HEALTHY", f"{check_name} OK"
            elif r < 0.95:
                status, details = "DEGRADED", f"{check_name} elevated latency"
            else:
                status, details = "UNHEALTHY", f"{check_name} intermittent failures"
            rows.append((
                check_name, env, target, status, details,
                random.randint(150, 2500),
                ts.strftime("%Y-%m-%d %H:%M:%S"),
            ))

    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS
           (check_name, environment, target_name, status, details, latency_ms, checked_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} HEALTH_CHECK_RESULTS rows.")


def seed_alert_history(cur, env):
    log("Seeding ALERT_HISTORY (4 sample alerts)...")
    now = datetime.now()
    rows = [
        ("cost_anomaly", "CRITICAL", env, AGENT_FQN,
         "Daily cost 3.2x above 7-day avg: $12.40 (avg $3.90)", 12.40, 7.80,
         (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")),
        ("latency_degradation", "WARNING", env, AGENT_FQN,
         "P95 latency 35s (threshold 30s)", 35000.0, 30000.0,
         (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")),
        ("negative_feedback_spike", "WARNING", env, AGENT_FQN,
         "28% negative feedback in last 24h (5 of 18)", 28.0, 25.0,
         (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")),
        ("interaction_quality", "WARNING", env, AGENT_FQN,
         "Tool looping detected: 3 of 42 requests", 7.1, 5.0,
         (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
           (alert_type, severity, environment, target_name, message,
            metric_value, threshold_value, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} ALERT_HISTORY rows.")


def seed_interaction_quality(cur, days, env):
    log(f"Seeding INTERACTION_QUALITY_DAILY ({days} days)...")
    today = date.today()
    rows = []
    for i in range(days):
        d = today - timedelta(days=days - i)
        total_req = random.randint(40, 120)
        total_thr = int(total_req * random.uniform(0.3, 0.5))
        tool_looping = random.choice([0, 0, 0, 1, 2])
        excessive_steps = random.choice([0, 0, 1, 2])
        slow_request = random.randint(0, 3)
        high_burn = random.choice([0, 0, 1])
        plan_errors = random.choice([0, 0, 0, 1])
        single_drops = random.randint(0, 4)
        rapid_rephrase = random.choice([0, 0, 1, 2])
        abandoned = random.choice([0, 0, 1])
        flagged_req = tool_looping + excessive_steps + slow_request + high_burn + plan_errors
        flagged_thr = single_drops + rapid_rephrase + abandoned
        critical = (1 if plan_errors else 0) + (1 if tool_looping and high_burn else 0)
        warning = max(0, flagged_req + flagged_thr - critical)
        pct = round(flagged_req * 100.0 / total_req, 2) if total_req else 0.0

        rows.append((
            d.isoformat(), env, AGENT_FQN,
            total_req, total_thr, flagged_req, flagged_thr,
            tool_looping, excessive_steps, slow_request, high_burn, plan_errors,
            single_drops, rapid_rephrase, abandoned,
            critical, warning, pct,
        ))

    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY
           (summary_date, environment, agent_name,
            total_requests, total_threads, flagged_requests, flagged_threads,
            tool_looping_count, excessive_steps_count, slow_request_count,
            high_token_burn_count, planning_error_count,
            single_turn_dropoff_count, rapid_rephrasing_count, abandoned_count,
            critical_count, warning_count, flagged_request_pct)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} INTERACTION_QUALITY_DAILY rows.")


def seed_scheduled_eval_runs(cur, env):
    log("Seeding SCHEDULED_EVAL_RUNS (2 runs)...")
    now = datetime.now()
    rows = [
        ("weekly_sv_smoke_test", env, SV_FQN,
         100.0, 0.0, True, 1, 1, 0,
         json.dumps({"latency_ms": 2300}),
         (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")),
        ("weekly_agent_smoke_test", env, AGENT_FQN,
         100.0, 0.0, True, 1, 1, 0,
         json.dumps({"latency_ms": 4100}),
         (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S")),
    ]
    cur.executemany(
        """INSERT INTO RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS
           (run_type, environment, target_name,
            accuracy_pct, threshold_pct, passed_threshold,
            total_questions, passed_questions, failed_questions,
            run_details, run_timestamp)
           SELECT column1, column2, column3, column4, column5, column6,
                  column7, column8, column9, PARSE_JSON(column10), column11
           FROM VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        rows,
    )
    log(f"Inserted {len(rows)} SCHEDULED_EVAL_RUNS rows.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14, help="History depth (default 14)")
    ap.add_argument("--env", default="dev", help="Environment tag (default dev)")
    ap.add_argument("--no-clean", action="store_true", help="Do not truncate before insert")
    args = ap.parse_args()

    random.seed(42)

    print("=" * 60)
    print("  SEED DASHBOARD DATA")
    print("=" * 60)
    print(f"  Days: {args.days} | Env: {args.env} | Clean: {not args.no_clean}")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("USE WAREHOUSE RETAIL_AI_EVAL_WH")

        if not args.no_clean:
            truncate_tables(cur)

        env = args.env
        seed_usage_metrics(cur, args.days, env)
        seed_user_feedback(cur, args.days, env)
        seed_feedback_daily_summary(cur, args.days, env)
        seed_eval_runs(cur, env)
        seed_scheduled_eval_runs(cur, env)
        seed_health_checks(cur, args.days, env)
        seed_alert_history(cur, env)
        seed_interaction_quality(cur, args.days, env)

        conn.commit()
    finally:
        conn.close()

    print()
    print("  DONE — open the dashboard:")
    print("  Projects -> Streamlit -> AI_MONITORING_DASHBOARD")
    print("=" * 60)


if __name__ == "__main__":
    main()
