#!/usr/bin/env python3
"""
seed_demo.py — Retail example demo-seeding.

Populates the monitoring dashboard with realistic demo data so the Streamlit
dashboard has something to show immediately after bootstrap:
  1. runs a health check,
  2. runs a small SV evaluation,
  3. sends sample questions to the agent (populates observability traces),
  4. aggregates traces into the monitoring tables,
  5. generates mock user feedback.

This is EXAMPLE content (not framework). bootstrap.py invokes the `seed(conn)`
entry point of the active instance's configured seed_module. All Snowflake
object names are read from the merged instance config — no hardcoded names — so
copying this example to a new domain only requires editing the config.
"""
import os
import sys
import json
import time

# Make the framework's shared utils importable when run standalone or imported
# dynamically by bootstrap. Repo root is three levels up from this file.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "evaluation"))
from utils import load_config, instance_dir, question_bank_dir, build_credits_expr  # noqa: E402


def _credits_expr(cfg: dict) -> str:
    """Cache-aware per-model credit CASE expression (see utils.build_credits_expr)."""
    return build_credits_expr(cfg.get("pricing", {}))


def seed(conn):
    """Entry point invoked by bootstrap.py for the active instance."""
    print(f"\n{'='*60}")
    print(f"  Populating Dashboard Data (health check + eval + agent queries)")
    print(f"{'='*60}")

    cfg = load_config()
    dev = cfg["environments"]["dev"]
    ev = cfg["eval"]
    db_eval = ev["database"]
    mon = ev["monitoring_schema"]
    obs = ev["observability_schema"]
    agent_fqn = dev["agent_name"]
    agent_short = dev["agent_short"]
    sv_fqn = dev["semantic_view"]
    credits_expr = _credits_expr(cfg)

    import subprocess
    python_exe = sys.executable
    child_env = {**os.environ, "SNOWFLAKE_CONNECTION_NAME": os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"}

    print("\n  [1/4] Running health check...")
    try:
        result = subprocess.run(
            [python_exe, os.path.join(_REPO_ROOT, "monitoring", "health_check.py"),
             "--environment", "dev", "--output", os.path.join(_REPO_ROOT, "health.json")],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=120, env=child_env,
        )
        healthy = result.stdout.count("[OK]")
        total = result.stdout.count("Running:")
        print(f"    Health checks: {healthy}/{total} passed")
    except Exception as e:
        print(f"    WARN: {str(e)[:100]}")

    print("\n  [2/4] Running SV evaluation (easy questions)...")
    try:
        result = subprocess.run(
            [python_exe, os.path.join(_REPO_ROOT, "evaluation", "evaluate_semantic_view.py"),
             "--environment", "dev",
             "--semantic-view", sv_fqn,
             "--categories", "easy",
             "--output", os.path.join(_REPO_ROOT, "sv_eval.json")],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=300, env=child_env,
        )
        for line in result.stdout.strip().split("\n"):
            if "Accuracy:" in line or "Result:" in line:
                print(f"    {line.strip()}")
    except Exception as e:
        print(f"    WARN: {str(e)[:100]}")

    print("\n  [3/4] Sending sample queries to agent (populates observability)...")
    import requests as req
    token = conn.rest.token
    host = conn.host.replace("_", "-").lower()
    parts = agent_fqn.split(".")
    agent_url = f"https://{host}/api/v2/databases/{parts[0]}/schemas/{parts[1]}/agents/{parts[2]}:run"
    agent_headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
    }

    sample_questions = []
    try:
        import yaml as _yaml
        agent_dir = question_bank_dir("agent")
        sv_dir = question_bank_dir("semantic_view")
        for bank_file in [
            os.path.join(agent_dir, "answerable_questions.yaml"),
            os.path.join(sv_dir, "hard_questions.yaml"),
            os.path.join(agent_dir, "adversarial_questions.yaml"),
        ]:
            with open(bank_file) as f:
                bank = _yaml.safe_load(f)
            for q in bank.get("questions", []):
                sample_questions.append(q["question"])
    except Exception:
        sample_questions = [
            "What is our total revenue?",
            "How many customers do we have?",
            "Show me top 5 products by revenue",
            "What is the return rate?",
            "Compare revenue across customer segments",
        ]
    success = 0
    for q in sample_questions:
        try:
            payload = {"messages": [{"role": "user", "content": [{"type": "text", "text": q}]}]}
            resp = req.post(agent_url, json=payload, headers=agent_headers, timeout=120, stream=True)
            has_error = False
            has_text = False
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("event: error"):
                    has_error = True
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                        if "message" in event and "code" in event:
                            has_error = True
                            print(f"    SKIP: {q} ({event['message'][:60]})")
                            break
                        if "text" in event:
                            has_text = True
                    except json.JSONDecodeError:
                        pass
            if has_text and not has_error:
                success += 1
                print(f"    OK: {q}")
            elif not has_error:
                print(f"    SKIP: {q} (no response)")
        except Exception as e:
            print(f"    SKIP: {q} ({str(e)[:60]})")

    print(f"\n    Agent queries: {success}/{len(sample_questions)} successful")
    if success > 0:
        print(f"    Observability data will appear in Snowsight under {agent_fqn}.")
        print("    Aggregating into dashboard tables (normally done by daily tasks)...")
        time.sleep(5)
        try:
            cur = conn.cursor()
            cur.execute(f'''
INSERT INTO {db_eval}.{mon}.USAGE_METRICS (
    metric_date, environment, service_type, agent_or_sv_name,
    total_requests, successful_requests, failed_requests,
    total_input_tokens, total_output_tokens, total_tokens, total_cache_read_tokens,
    estimated_credits, avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
SELECT CURRENT_DATE(), COALESCE(database_name, 'UNKNOWN'),
    CASE WHEN span_name LIKE 'ReasoningAgentStep%' THEN 'cortex_agent'
         WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst' ELSE 'other' END,
    COALESCE(agent_name, 'unknown'),
    COUNT(DISTINCT trace_id), COUNT_IF(status_code = 'STATUS_CODE_OK'), COUNT_IF(status_code != 'STATUS_CODE_OK'),
    COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0), COALESCE(SUM(cache_read_tokens),0),
    SUM({credits_expr}), AVG(planning_duration_ms),
    APPROX_PERCENTILE(planning_duration_ms,0.5), APPROX_PERCENTILE(planning_duration_ms,0.95),
    APPROX_PERCENTILE(planning_duration_ms,0.99), 0
FROM {db_eval}.{obs}.AGENT_TRACES
WHERE event_time >= DATEADD('day',-1,CURRENT_DATE()) AND event_time < CURRENT_DATE()+1
  AND agent_name = '{agent_short}'
GROUP BY 1,2,3,4
''')
            cur.execute(f'''
INSERT INTO {db_eval}.{mon}.INTERACTION_QUALITY_DAILY (
    summary_date, environment, agent_name,
    total_requests, total_threads, flagged_requests, flagged_request_pct,
    tool_looping_count, excessive_steps_count, slow_request_count,
    high_token_burn_count, planning_error_count,
    single_turn_dropoff_count, rapid_rephrasing_count, abandoned_count,
    critical_count, warning_count)
SELECT CURRENT_DATE(), COALESCE(database_name, 'UNKNOWN'), COALESCE(agent_name, 'unknown'),
    COUNT(DISTINCT trace_id), COUNT(DISTINCT thread_id),
    COUNT_IF(total_tokens > 50000 OR planning_duration_ms > 30000),
    ROUND(COUNT_IF(total_tokens > 50000 OR planning_duration_ms > 30000) * 100.0 / NULLIF(COUNT(DISTINCT trace_id),0), 2),
    0, COUNT_IF(step_number > 5), COUNT_IF(planning_duration_ms > 30000),
    COUNT_IF(total_tokens > 50000), COUNT_IF(planning_status != 'success' AND planning_status IS NOT NULL),
    0, 0, 0, COUNT_IF(total_tokens > 100000), COUNT_IF(total_tokens > 50000 AND total_tokens <= 100000)
FROM {db_eval}.{obs}.AGENT_TRACES
WHERE event_time >= DATEADD('day',-1,CURRENT_DATE()) AND event_time < CURRENT_DATE()+1
  AND agent_name = '{agent_short}' AND span_name LIKE 'ReasoningAgentStep%'
GROUP BY 1,2,3
''')
            print("    Dashboard tables populated.")
        except Exception as e:
            print(f"    WARN: Could not aggregate: {str(e)[:100]}")

    print("\n  [4/4] Generating mock user feedback...")
    _generate_mock_feedback(conn, cfg)


def _generate_mock_feedback(conn, cfg):
    dev = cfg["environments"]["dev"]
    ev = cfg["eval"]
    env_name = dev["database"]
    agent_short = dev["agent_short"]
    db_eval = ev["database"]
    mon = ev["monitoring_schema"]

    cur = conn.cursor()
    # (query, response, rating, feedback_text, category) — retail demo content.
    feedback_data = [
        ("What is our total revenue?", "Total revenue is $2.4M across all channels.", 5,
         "Great answer, exactly what I needed!", "accuracy"),
        ("Show me top products by revenue", "Here are the top 5 products by revenue...", 4,
         "Good breakdown but would be nice to see percentages too", "completeness"),
        ("How many customers do we have?", "We have 500 customers in total.", 5,
         "Quick and accurate", "accuracy"),
        ("What is the return rate?", "The overall return rate is 12.3%.", 3,
         "I expected a breakdown by product category", "completeness"),
        ("Compare revenue across segments", "Premium segment leads with 45% of revenue...", 4,
         "Useful comparison, could use a chart next time", "presentation"),
        ("What was last month revenue?", "I'm unable to determine the time period from the data.", 2,
         "It should know what last month means", "accuracy"),
        ("Show me slow-selling products", "Products with lowest sales velocity: ...", 4,
         "Helpful, saved me time writing a query", "usefulness"),
        ("Customer acquisition trend", "Monthly new customer signups show...", 1,
         "Completely wrong data, these numbers don't match our reports", "accuracy"),
        ("Average order value by store", "Store A: $85, Store B: $72, Store C: $91...", 5,
         "Perfect, exactly what the exec team asked for", "usefulness"),
        ("Which customers are at risk of churning?", "Based on order recency and frequency...", 4,
         "Good heuristic approach, would like ML-based scoring next", "completeness"),
    ]

    try:
        values_parts = []
        for i, (query, response, rating, text, category) in enumerate(feedback_data):
            eq = query.replace("'", "''")
            er = response.replace("'", "''")
            et = text.replace("'", "''")
            values_parts.append(f"""
                SELECT 'fb_demo_{i+1}', '{env_name}', 'agent', '{agent_short}',
                       '{eq}', '{er}', {rating},
                       '{et}', '{category}', NULL, 'DEMO_USER',
                       DATEADD('hour', -{(len(feedback_data)-i)*2}, CURRENT_TIMESTAMP())
            """)

        insert_sql = f"""
            INSERT INTO {db_eval}.{mon}.USER_FEEDBACK
                (feedback_id, environment, source, agent_or_sv_name, user_query,
                 agent_response, feedback_rating, feedback_text, feedback_category,
                 sentiment_score, user_name, created_at)
            {' UNION ALL '.join(values_parts)}
        """
        cur.execute(insert_sql)
        print(f"    Inserted {len(feedback_data)} feedback entries")

        cur.execute(f"""
            UPDATE {db_eval}.{mon}.USER_FEEDBACK
            SET sentiment_score = SNOWFLAKE.CORTEX.SENTIMENT(COALESCE(feedback_text,'') || ' Rating: ' || feedback_rating::STRING)
            WHERE sentiment_score IS NULL AND feedback_id LIKE 'fb_demo_%'
        """)
        print("    Sentiment analysis complete")

        cur.execute(f"""
            INSERT INTO {db_eval}.{mon}.FEEDBACK_DAILY_SUMMARY
                (summary_date, environment, agent_or_sv_name, total_feedback,
                 positive_count, neutral_count, negative_count, avg_rating,
                 avg_sentiment_score, negative_pct, feedback_categories, computed_at)
            SELECT CURRENT_DATE(), '{env_name}', '{agent_short}',
                COUNT(*),
                COUNT_IF(feedback_rating >= 4),
                COUNT_IF(feedback_rating = 3),
                COUNT_IF(feedback_rating <= 2),
                AVG(feedback_rating),
                AVG(sentiment_score),
                ROUND(COUNT_IF(feedback_rating <= 2) * 100.0 / COUNT(*), 1),
                OBJECT_CONSTRUCT('accuracy', COUNT_IF(feedback_category='accuracy'),
                                 'completeness', COUNT_IF(feedback_category='completeness'),
                                 'presentation', COUNT_IF(feedback_category='presentation'),
                                 'usefulness', COUNT_IF(feedback_category='usefulness')),
                CURRENT_TIMESTAMP()
            FROM {db_eval}.{mon}.USER_FEEDBACK
            WHERE feedback_id LIKE 'fb_demo_%'
        """)
        print("    Feedback daily summary aggregated")
    except Exception as e:
        print(f"    WARN: Feedback generation failed: {str(e)[:120]}")
