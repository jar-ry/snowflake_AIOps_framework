#!/usr/bin/env python3
"""
bootstrap.py
One-command setup for the AI Evaluation Framework.

Creates all Snowflake objects, seeds data, deploys DEV semantic view + agent,
runs a first evaluation, and prints next steps.

Usage:
    python setup/bootstrap.py
    SNOWFLAKE_CONNECTION_NAME=myconn python setup/bootstrap.py
    SNOWFLAKE_PRIVATE_KEY_PATH=~/.snowflake/keys/rsa_key.p8 SNOWFLAKE_ACCOUNT=xxx SNOWFLAKE_USER=yyy python setup/bootstrap.py

Prerequisites:
    pip install -r requirements.txt
    Python 3.11 or 3.12 recommended (3.14 has known connector compatibility issues)
    A Snowflake connection configured in ~/.snowflake/connections.toml
    OR SNOWFLAKE_ACCOUNT/USER + SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH
"""
import os
import re
import sys
import json
import time
import yaml
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "evaluation"))

import snowflake.connector


def load_schedule_config(profile: str = "demo") -> dict:
    config_path = os.path.join(PROJECT_ROOT, "config", "schedules.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    profiles = config.get("profiles", {})
    if profile not in profiles:
        print(f"  WARN: Schedule profile '{profile}' not found, falling back to 'demo'")
        profile = "demo"
    return profiles[profile]["tasks"]


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
            key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
            passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
            with open(key_path, "rb") as f:
                pk = serialization.load_pem_private_key(
                    f.read(),
                    password=passphrase.encode() if passphrase else None,
                )
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
            key_path = os.path.expanduser(conn_config["private_key_path"])
            with open(key_path, "rb") as f:
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


def run_sql_file(conn, filepath, description):
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  {filepath}")
    print(f"{'='*60}")

    with open(filepath) as f:
        sql = f.read()

    sql_clean = re.sub(r"(?i)^\s*USE\s+ROLE\s+\w+\s*;", "", sql, flags=re.MULTILINE)
    sql_clean = re.sub(r"(?i)^\s*USE\s+WAREHOUSE\s+\w+\s*;", "", sql_clean, flags=re.MULTILINE)
    sql_clean = re.sub(r"(?i)^\s*USE\s+DATABASE\s+\w+\s*;", "", sql_clean, flags=re.MULTILINE)
    sql_clean = re.sub(r"(?i)^\s*USE\s+SCHEMA\s+[\w.]+\s*;", "", sql_clean, flags=re.MULTILINE)

    dollar_blocks = list(re.finditer(r"\$\$.*?\$\$", sql_clean, re.DOTALL))
    dollar_ranges = [(m.start(), m.end()) for m in dollar_blocks]

    def in_dollar_block(pos):
        return any(s <= pos < e for s, e in dollar_ranges)

    statements = []
    current = []
    for i, char in enumerate(sql_clean):
        if char == ";" and not in_dollar_block(i):
            stmt = "".join(current).strip()
            if stmt and not all(line.strip().startswith("--") or not line.strip() for line in stmt.split("\n")):
                statements.append(stmt)
            current = []
        else:
            current.append(char)
    last = "".join(current).strip()
    if last and not all(line.strip().startswith("--") or not line.strip() for line in last.split("\n")):
        statements.append(last)

    cur = conn.cursor()
    success = 0
    errors = 0
    for stmt in statements:
        lines = [l for l in stmt.split("\n") if not l.strip().startswith("--")]
        clean = "\n".join(lines).strip()
        if not clean:
            continue
        try:
            cur.execute(clean)
            success += 1
        except Exception as e:
            err_msg = str(e)[:120]
            if "already exists" in err_msg.lower():
                success += 1
            else:
                errors += 1
                print(f"  WARN: {err_msg}")

    status = "OK" if errors == 0 else f"OK ({errors} warnings)"
    print(f"  {status}: {success}/{success + errors} statements")
    return errors == 0


def deploy_semantic_view(conn):
    print(f"\n{'='*60}")
    print(f"  Deploying DEV Semantic View")
    print(f"{'='*60}")
    sv_path = os.path.join(PROJECT_ROOT, "semantic_views", "dev", "retail_analytics_sv.yaml")
    with open(sv_path) as f:
        yaml_content = f.read()
    conn.cursor().execute(
        "CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML('RETAIL_AI_DEV.SEMANTIC', %s)",
        (yaml_content,),
    )
    print("  OK: RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV")


def deploy_agent(conn):
    print(f"\n{'='*60}")
    print(f"  Deploying DEV Agent")
    print(f"{'='*60}")
    agent_path = os.path.join(PROJECT_ROOT, "agents", "dev", "retail_agent.sql")
    with open(agent_path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    full_sql = "\n".join(lines).strip().rstrip(";")
    conn.cursor().execute(full_sql)
    print("  OK: RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT")


def run_first_eval(conn):
    print(f"\n{'='*60}")
    print(f"  Running First Evaluation (SV audit on DEV)")
    print(f"{'='*60}")
    try:
        audit_path = os.path.join(PROJECT_ROOT, "evaluation", "audit_semantic_view.py")
        ddl_path = os.path.join(PROJECT_ROOT, "semantic_views", "dev", "retail_analytics_sv.yaml")
        output_path = os.path.join(PROJECT_ROOT, "first_eval_audit.json")

        import subprocess
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, audit_path, "--ddl-file", ddl_path, "--output", output_path],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=120,
        )
        if result.returncode == 0:
            print("  AUDIT PASSED")
        else:
            print("  AUDIT COMPLETED WITH FINDINGS (non-blocking)")

        if result.stdout:
            for line in result.stdout.strip().split("\n")[-10:]:
                print(f"    {line}")

        if os.path.exists(output_path):
            with open(output_path) as f:
                audit = json.load(f)
            summary = audit.get("summary", {})
            print(f"  Findings: {summary.get('total_findings', 'N/A')}")
            print(f"  Blocking: {summary.get('has_blocking_issues', 'N/A')}")
            print(f"  Results saved to: first_eval_audit.json")

    except Exception as e:
        print(f"  WARN: Audit skipped ({str(e)[:100]})")


def create_tasks_directly(cur, schedule_profile="demo"):
    print(f"\n{'='*60}")
    print(f"  Creating tasks and stored procs (schedule profile: {schedule_profile})")
    print(f"{'='*60}")

    schedules = load_schedule_config(schedule_profile)
    config = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "environments.yaml")))
    pricing = config.get("pricing", {})
    default_in = pricing.get("default_input_credits_per_million", 1.0)
    default_out = pricing.get("default_output_credits_per_million", 1.0)
    models = pricing.get("models", {})

    case_parts = []
    for model, rates in models.items():
        in_rate = rates["input_credits_per_million"]
        out_rate = rates["output_credits_per_million"]
        case_parts.append(
            f"WHEN model_used = '{model}' THEN "
            f"COALESCE(input_tokens,0)/1000000.0*{in_rate} + COALESCE(output_tokens,0)/1000000.0*{out_rate}"
        )
    case_parts.append(
        f"ELSE COALESCE(input_tokens,0)/1000000.0*{default_in} + COALESCE(output_tokens,0)/1000000.0*{default_out}"
    )
    credits_expr = "CASE " + " ".join(case_parts) + " END"

    tasks = [
        ("TASK_DAILY_USAGE_AGGREGATION", schedules["usage_aggregation"]["schedule"], f"""
            INSERT INTO RETAIL_AI_EVAL.MONITORING.USAGE_METRICS (
                metric_date, environment, service_type, agent_or_sv_name,
                total_requests, successful_requests, failed_requests,
                total_input_tokens, total_output_tokens, total_tokens,
                estimated_credits, avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
            SELECT CURRENT_DATE(), COALESCE(database_name, 'UNKNOWN'),
                CASE WHEN span_name LIKE 'ReasoningAgentStep%' OR span_name LIKE 'CodingAgent%' THEN 'cortex_agent'
                     WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst' ELSE 'other' END,
                COALESCE(agent_name, 'unknown'),
                COUNT(DISTINCT trace_id), COUNT_IF(status_code = 'STATUS_CODE_OK'), COUNT_IF(status_code != 'STATUS_CODE_OK'),
                COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0),
                SUM({credits_expr}), AVG(planning_duration_ms),
                APPROX_PERCENTILE(planning_duration_ms,0.5), APPROX_PERCENTILE(planning_duration_ms,0.95),
                APPROX_PERCENTILE(planning_duration_ms,0.99), 0
            FROM RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES
            WHERE event_time >= DATEADD('hour',-24,CURRENT_TIMESTAMP())
              AND (span_name LIKE 'ReasoningAgentStepPlanning%' OR span_name LIKE 'CodingAgent.Step%' OR span_name ILIKE '%Analyst%')
            GROUP BY 1,2,3,4"""),
        ("TASK_DAILY_FEEDBACK_ANALYSIS", schedules["feedback_analysis"]["schedule"], """
            UPDATE RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
            SET sentiment_score = SNOWFLAKE.CORTEX.SENTIMENT(COALESCE(feedback_text,'') || ' Rating: ' || feedback_rating::STRING)
            WHERE sentiment_score IS NULL AND (feedback_text IS NOT NULL OR feedback_rating IS NOT NULL)"""),
        ("TASK_DAILY_HEALTH_CHECKS", schedules["health_checks"]["schedule"], """
            INSERT INTO RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS (check_name, environment, target_name, status, details, latency_ms)
            SELECT 'error_rate', 'prod', 'ALL_SERVICES',
                CASE WHEN ROUND(COUNT_IF(RECORD:status.code::STRING != 'STATUS_CODE_OK')*100.0/NULLIF(COUNT(*),0),2) > 20 THEN 'UNHEALTHY'
                     WHEN ROUND(COUNT_IF(RECORD:status.code::STRING != 'STATUS_CODE_OK')*100.0/NULLIF(COUNT(*),0),2) > 5 THEN 'DEGRADED'
                     ELSE 'HEALTHY' END,
                'Error rate: ' || ROUND(COUNT_IF(RECORD:status.code::STRING != 'STATUS_CODE_OK')*100.0/NULLIF(COUNT(*),0),1) || '%', 0
            FROM snowflake.local.ai_observability_events
            WHERE RECORD_TYPE = 'SPAN' AND SCOPE:name::STRING = 'snow.cortex.agent'
              AND TIMESTAMP >= DATEADD('hour',-24,CURRENT_TIMESTAMP())"""),
    ]

    for name, schedule, body in tasks:
        try:
            cur.execute(f"""CREATE OR REPLACE TASK RETAIL_AI_EVAL.MONITORING.{name}
                WAREHOUSE = RETAIL_AI_EVAL_WH SCHEDULE = '{schedule}' AS {body}""")
            cur.execute(f"ALTER TASK RETAIL_AI_EVAL.MONITORING.{name} RESUME")
            print(f"  OK: {name}")
        except Exception as e:
            print(f"  WARN: {name}: {str(e)[:100]}")

    procs = {
        "SP_WEEKLY_SV_EVAL": """
CREATE OR REPLACE PROCEDURE RETAIL_AI_EVAL.MONITORING.SP_WEEKLY_SV_EVAL()
RETURNS STRING LANGUAGE SQL EXECUTE AS CALLER AS
$$
BEGIN
    LET sv_name STRING := 'RETAIL_AI_PROD.SEMANTIC.RETAIL_ANALYTICS_SV';
    LET start_ts TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    LET status STRING := 'HEALTHY';
    LET details STRING := '';
    BEGIN
        LET result VARIANT := (SELECT SNOWFLAKE.CORTEX.COMPLETE('analyst',
            OBJECT_CONSTRUCT('messages', ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('role','user','content',
            ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('type','text','text','What is our total revenue?')))),
            'semantic_model', OBJECT_CONSTRUCT('semantic_view', :sv_name))));
        LET latency INTEGER := DATEDIFF('millisecond', :start_ts, CURRENT_TIMESTAMP());
        INSERT INTO RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        VALUES ('weekly_sv_smoke_test','prod',:sv_name,100,0,TRUE,1,1,0, PARSE_JSON('{"latency_ms":' || :latency || '}'));
        details := 'Passed in ' || :latency || 'ms';
    EXCEPTION WHEN OTHER THEN
        status := 'UNHEALTHY'; details := 'Failed: ' || SQLERRM;
        INSERT INTO RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        VALUES ('weekly_sv_smoke_test','prod',:sv_name,0,0,FALSE,1,0,1, PARSE_JSON('{"error":"' || SQLERRM || '"}'));
    END;
    INSERT INTO RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS (check_name, environment, target_name, status, details, latency_ms)
    VALUES ('weekly_sv_smoke_test','prod',:sv_name,:status,:details,0);
    RETURN :status || ': ' || :details;
END;
$$""",
        "SP_WEEKLY_AGENT_EVAL": """
CREATE OR REPLACE PROCEDURE RETAIL_AI_EVAL.MONITORING.SP_WEEKLY_AGENT_EVAL()
RETURNS STRING LANGUAGE SQL EXECUTE AS CALLER AS
$$
BEGIN
    LET agent_name STRING := 'RETAIL_AI_PROD.SEMANTIC.RETAIL_AGENT';
    LET start_ts TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    LET status STRING := 'HEALTHY';
    LET details STRING := '';
    BEGIN
        LET result STRING := (SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(:agent_name,
            '{"messages":[{"role":"user","content":[{"type":"text","text":"What is our total revenue this year?"}]}]}'));
        LET latency INTEGER := DATEDIFF('millisecond', :start_ts, CURRENT_TIMESTAMP());
        INSERT INTO RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        VALUES ('weekly_agent_smoke_test','prod',:agent_name,100,0,TRUE,1,1,0, PARSE_JSON('{"latency_ms":' || :latency || '}'));
        details := 'Passed in ' || :latency || 'ms';
    EXCEPTION WHEN OTHER THEN
        status := 'UNHEALTHY'; details := 'Failed: ' || SQLERRM;
        INSERT INTO RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        VALUES ('weekly_agent_smoke_test','prod',:agent_name,0,0,FALSE,1,0,1, PARSE_JSON('{"error":"' || SQLERRM || '"}'));
    END;
    INSERT INTO RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS (check_name, environment, target_name, status, details, latency_ms)
    VALUES ('weekly_agent_smoke_test','prod',:agent_name,:status,:details,0);
    RETURN :status || ': ' || :details;
END;
$$""",
    }

    weekly_tasks = [
        ("TASK_WEEKLY_SV_EVAL", schedules["weekly_sv_eval"]["schedule"], "CALL RETAIL_AI_EVAL.MONITORING.SP_WEEKLY_SV_EVAL()"),
        ("TASK_WEEKLY_AGENT_EVAL", schedules["weekly_agent_eval"]["schedule"], "CALL RETAIL_AI_EVAL.MONITORING.SP_WEEKLY_AGENT_EVAL()"),
    ]

    for name, sql in procs.items():
        try:
            cur.execute(sql)
            print(f"  OK: {name}")
        except Exception as e:
            print(f"  WARN: {name}: {str(e)[:100]}")

    for name, schedule, body in weekly_tasks:
        try:
            cur.execute(f"CREATE OR REPLACE TASK RETAIL_AI_EVAL.MONITORING.{name} WAREHOUSE = RETAIL_AI_EVAL_WH SCHEDULE = '{schedule}' AS {body}")
            cur.execute(f"ALTER TASK RETAIL_AI_EVAL.MONITORING.{name} RESUME")
            print(f"  OK: {name}")
        except Exception as e:
            print(f"  WARN: {name}: {str(e)[:100]}")


def deploy_dashboard_sis():
    print(f"\n{'='*60}")
    print(f"  Deploying Monitoring Dashboard (Streamlit in Snowflake)")
    print(f"{'='*60}")
    try:
        import subprocess
        monitoring_dir = os.path.join(PROJECT_ROOT, "monitoring")
        conn_name = os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
        result = subprocess.run(
            ["snow", "streamlit", "deploy", "--replace", "--connection", conn_name],
            capture_output=True,
            text=True,
            cwd=monitoring_dir,
            timeout=120,
        )
        if result.returncode == 0:
            print("  OK: AI_MONITORING_DASHBOARD deployed to RETAIL_AI_EVAL.MONITORING")
            for line in result.stdout.strip().split("\n")[-3:]:
                print(f"    {line}")
        else:
            stderr = result.stderr.strip()
            if "snow: command not found" in stderr or "No such file" in stderr:
                print("  SKIP: Snowflake CLI (snow) not found. Install with: pip install snowflake-cli")
                print("  You can deploy manually later: cd monitoring && snow streamlit deploy --replace")
            else:
                print(f"  WARN: {stderr[:200]}")
                print("  You can deploy manually: cd monitoring && snow streamlit deploy --replace")
    except FileNotFoundError:
        print("  SKIP: Snowflake CLI (snow) not found. Install with: pip install snowflake-cli")
        print("  Deploy manually: cd monitoring && snow streamlit deploy --replace")
    except Exception as e:
        print(f"  WARN: Dashboard deploy skipped ({str(e)[:100]})")
        print("  Deploy manually: cd monitoring && snow streamlit deploy --replace")


def populate_dashboard(conn):
    print(f"\n{'='*60}")
    print(f"  Populating Dashboard Data (health check + eval + agent queries)")
    print(f"{'='*60}")

    config = yaml.safe_load(open(os.path.join(PROJECT_ROOT, "config", "environments.yaml")))
    pricing = config.get("pricing", {})
    default_in = pricing.get("default_input_credits_per_million", 1.0)
    default_out = pricing.get("default_output_credits_per_million", 1.0)
    models = pricing.get("models", {})
    case_parts = []
    for model, rates in models.items():
        case_parts.append(
            f"WHEN model_used = '{model}' THEN "
            f"COALESCE(input_tokens,0)/1000000.0*{rates['input_credits_per_million']} + COALESCE(output_tokens,0)/1000000.0*{rates['output_credits_per_million']}"
        )
    case_parts.append(f"ELSE COALESCE(input_tokens,0)/1000000.0*{default_in} + COALESCE(output_tokens,0)/1000000.0*{default_out}")
    credits_expr = "CASE " + " ".join(case_parts) + " END"

    import subprocess
    python_exe = sys.executable

    print("\n  [1/3] Running health check...")
    try:
        result = subprocess.run(
            [python_exe, os.path.join(PROJECT_ROOT, "monitoring", "health_check.py"),
             "--environment", "dev", "--output", os.path.join(PROJECT_ROOT, "health.json")],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=120,
            env={**os.environ, "SNOWFLAKE_CONNECTION_NAME": os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"},
        )
        healthy = result.stdout.count("[OK]")
        total = result.stdout.count("Running:")
        print(f"    Health checks: {healthy}/{total} passed")
    except Exception as e:
        print(f"    WARN: {str(e)[:100]}")

    print("\n  [2/3] Running SV evaluation (easy questions)...")
    try:
        result = subprocess.run(
            [python_exe, os.path.join(PROJECT_ROOT, "evaluation", "evaluate_semantic_view.py"),
             "--environment", "dev",
             "--semantic-view", "RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV",
             "--categories", "easy",
             "--output", os.path.join(PROJECT_ROOT, "sv_eval.json")],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=300,
            env={**os.environ, "SNOWFLAKE_CONNECTION_NAME": os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"},
        )
        for line in result.stdout.strip().split("\n"):
            if "Accuracy:" in line or "Result:" in line:
                print(f"    {line.strip()}")
    except Exception as e:
        print(f"    WARN: {str(e)[:100]}")

    print("\n  [3/3] Sending sample queries to agent (populates observability)...")
    import requests as req
    token = conn.rest.token
    host = conn.host.replace("_", "-").lower()
    agent_url = f"https://{host}/api/v2/databases/RETAIL_AI_DEV/schemas/SEMANTIC/agents/RETAIL_AGENT:run"
    agent_headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
    }

    sample_questions = []
    try:
        import yaml as _yaml
        for bank_file in [
            os.path.join(PROJECT_ROOT, "question_banks", "agent", "answerable_questions.yaml"),
            os.path.join(PROJECT_ROOT, "question_banks", "semantic_view", "hard_questions.yaml"),
            os.path.join(PROJECT_ROOT, "question_banks", "agent", "adversarial_questions.yaml"),
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
            payload = {
                "messages": [{"role": "user", "content": [{"type": "text", "text": q}]}],
            }
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
        print("    Observability data will appear in Snowsight under RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT.")
        print("    Aggregating into dashboard tables (normally done by daily tasks)...")
        time.sleep(5)
        try:
            cur = conn.cursor()
            cur.execute(f'''
INSERT INTO RETAIL_AI_EVAL.MONITORING.USAGE_METRICS (
    metric_date, environment, service_type, agent_or_sv_name,
    total_requests, successful_requests, failed_requests,
    total_input_tokens, total_output_tokens, total_tokens,
    estimated_credits, avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
SELECT CURRENT_DATE(), COALESCE(database_name, 'UNKNOWN'),
    CASE WHEN span_name LIKE 'ReasoningAgentStep%' THEN 'cortex_agent'
         WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst' ELSE 'other' END,
    COALESCE(agent_name, 'unknown'),
    COUNT(DISTINCT trace_id), COUNT_IF(status_code = 'STATUS_CODE_OK'), COUNT_IF(status_code != 'STATUS_CODE_OK'),
    COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0),
    SUM({credits_expr}), AVG(planning_duration_ms),
    APPROX_PERCENTILE(planning_duration_ms,0.5), APPROX_PERCENTILE(planning_duration_ms,0.95),
    APPROX_PERCENTILE(planning_duration_ms,0.99), 0
FROM RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES
WHERE event_time >= DATEADD('day',-1,CURRENT_DATE()) AND event_time < CURRENT_DATE()+1
  AND agent_name = 'RETAIL_AGENT'
GROUP BY 1,2,3,4
''')
            cur.execute('''
INSERT INTO RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY (
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
FROM RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES
WHERE event_time >= DATEADD('day',-1,CURRENT_DATE()) AND event_time < CURRENT_DATE()+1
  AND agent_name = 'RETAIL_AGENT' AND span_name LIKE 'ReasoningAgentStep%'
GROUP BY 1,2,3
''')
            print("    Dashboard tables populated.")
        except Exception as e:
            print(f"    WARN: Could not aggregate: {str(e)[:100]}")

    print("\n  [4/4] Generating mock user feedback...")
    generate_mock_feedback(conn)


def generate_mock_feedback(conn):
    cur = conn.cursor()
    feedback_data = [
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "What is our total revenue?",
         "Total revenue is $2.4M across all channels.", 5,
         "Great answer, exactly what I needed!", "accuracy"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "Show me top products by revenue",
         "Here are the top 5 products by revenue...", 4,
         "Good breakdown but would be nice to see percentages too", "completeness"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "How many customers do we have?",
         "We have 500 customers in total.", 5,
         "Quick and accurate", "accuracy"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "What is the return rate?",
         "The overall return rate is 12.3%.", 3,
         "I expected a breakdown by product category", "completeness"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "Compare revenue across segments",
         "Premium segment leads with 45% of revenue...", 4,
         "Useful comparison, could use a chart next time", "presentation"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "What was last month revenue?",
         "I'm unable to determine the time period from the data.", 2,
         "It should know what last month means", "accuracy"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "Show me slow-selling products",
         "Products with lowest sales velocity: ...", 4,
         "Helpful, saved me time writing a query", "usefulness"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "Customer acquisition trend",
         "Monthly new customer signups show...", 1,
         "Completely wrong data, these numbers don't match our reports", "accuracy"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "Average order value by store",
         "Store A: $85, Store B: $72, Store C: $91...", 5,
         "Perfect, exactly what the exec team asked for", "usefulness"),
        ("RETAIL_AI_DEV", "agent", "RETAIL_AGENT", "Which customers are at risk of churning?",
         "Based on order recency and frequency...", 4,
         "Good heuristic approach, would like ML-based scoring next", "completeness"),
    ]

    try:
        values_parts = []
        for i, (env, src, agent, query, response, rating, text, category) in enumerate(feedback_data):
            escaped_query = query.replace("'", "''")
            escaped_response = response.replace("'", "''")
            escaped_text = text.replace("'", "''")
            values_parts.append(f"""
                SELECT 'fb_demo_{i+1}', '{env}', '{src}', '{agent}',
                       '{escaped_query}', '{escaped_response}', {rating},
                       '{escaped_text}', '{category}', NULL, 'DEMO_USER',
                       DATEADD('hour', -{(len(feedback_data)-i)*2}, CURRENT_TIMESTAMP())
            """)

        insert_sql = f"""
            INSERT INTO RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
                (feedback_id, environment, source, agent_or_sv_name, user_query,
                 agent_response, feedback_rating, feedback_text, feedback_category,
                 sentiment_score, user_name, created_at)
            {' UNION ALL '.join(values_parts)}
        """
        cur.execute(insert_sql)
        print(f"    Inserted {len(feedback_data)} feedback entries")

        cur.execute("""
            UPDATE RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
            SET sentiment_score = SNOWFLAKE.CORTEX.SENTIMENT(COALESCE(feedback_text,'') || ' Rating: ' || feedback_rating::STRING)
            WHERE sentiment_score IS NULL AND feedback_id LIKE 'fb_demo_%'
        """)
        print("    Sentiment analysis complete")

        cur.execute(f"""
            INSERT INTO RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY
                (summary_date, environment, agent_or_sv_name, total_feedback,
                 positive_count, neutral_count, negative_count, avg_rating,
                 avg_sentiment_score, negative_pct, feedback_categories, computed_at)
            SELECT CURRENT_DATE(), 'RETAIL_AI_DEV', 'RETAIL_AGENT',
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
            FROM RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
            WHERE feedback_id LIKE 'fb_demo_%'
        """)
        print("    Feedback daily summary aggregated")
    except Exception as e:
        print(f"    WARN: Feedback generation failed: {str(e)[:120]}")


def print_summary():
    print(f"\n{'='*60}")
    print(f"  SETUP COMPLETE")
    print(f"{'='*60}")
    print("""
  What was created:
    Databases:    RETAIL_AI_DEV, RETAIL_AI_PROD, RETAIL_AI_EVAL
    Tables:       6 retail tables (500 customers, 5K orders, etc.) in DEV + PROD
    RBAC:         4 roles (ANALYST, REVIEWER, DEPLOYER, ADMIN)
    Observability: 4 views over ai_observability_events
    Eval dataset: 15 ground truth questions in DEV + PROD
    Monitoring:   7 tables, 7 views, 5 tasks (running), 7 alerts (active)
    Dashboard:    RETAIL_AI_EVAL.MONITORING.AI_MONITORING_DASHBOARD (SiS)
    Semantic View: RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV
    Agent:        RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT

  PROD is empty — SV and agent are deployed on merge via CD pipeline.

  Next steps:
    1. Open the dashboard in Snowsight:
       Projects → Streamlit → AI_MONITORING_DASHBOARD
    2. Chat with the agent in Snowsight:
       AI & ML → Agents → RETAIL_AGENT
    3. Push to GitHub and open a PR to test CI/CD
""")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap the AI Evaluation Framework")
    parser.add_argument("--skip-sql", action="store_true", help="Skip SQL setup (if already run)")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip SV/agent deployment")
    parser.add_argument("--skip-eval", action="store_true", help="Skip first evaluation")
    parser.add_argument("--skip-populate", action="store_true", help="Skip dashboard population (health check + eval + agent queries)")
    parser.add_argument("--schedule-profile", default="demo", choices=["demo", "prod"],
                        help="Task schedule profile: 'demo' (every 15 min) or 'prod' (realistic daily/weekly)")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  AI EVALUATION FRAMEWORK — BOOTSTRAP")
    print("="*60)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE()")
    account, user, role = cur.fetchone()
    print(f"  Account:  {account}")
    print(f"  User:     {user}")
    print(f"  Role:     {role}")

    if not args.skip_sql:
        sql_scripts = [
            ("setup/01_create_databases.sql", "Step 1/11: Create databases and eval tables"),
            ("setup/02_create_tables.sql", "Step 2/11: Create retail tables"),
            ("setup/03_seed_data.sql", "Step 3/11: Seed mock data (500 customers, 5K orders)"),
            ("setup/04_rbac_setup.sql", "Step 4/11: Create RBAC roles and grants"),
            ("setup/05_observability_setup.sql", "Step 5/11: Create observability views"),
            ("setup/06_eval_dataset_setup.sql", "Step 6/11: Create evaluation datasets"),
            ("setup/07_monitoring_tables.sql", "Step 7/11: Create monitoring tables"),
            ("setup/08_monitoring_tasks.sql", "Step 8/11: Create monitoring tasks"),
            ("setup/09_monitoring_views.sql", "Step 9/11: Create monitoring views"),
            ("setup/10_monitoring_alerts.sql", "Step 10/11: Create monitoring alerts"),
            ("setup/11_interaction_quality_engine.sql", "Step 11/11: Create interaction quality engine"),
        ]

        cur.execute("CREATE WAREHOUSE IF NOT EXISTS RETAIL_AI_EVAL_WH WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE")
        cur.execute("USE WAREHOUSE RETAIL_AI_EVAL_WH")

        for script, desc in sql_scripts:
            filepath = os.path.join(PROJECT_ROOT, script)
            if os.path.exists(filepath):
                run_sql_file(conn, filepath, desc)
            else:
                print(f"  SKIP: {script} (not found)")

        create_tasks_directly(cur, schedule_profile=args.schedule_profile)
    else:
        print("\n  Skipping SQL setup (--skip-sql)")
        cur.execute("USE WAREHOUSE RETAIL_AI_EVAL_WH")

    if not args.skip_sql:
        cur.execute(f"ALTER USER {user} SET DEFAULT_WAREHOUSE = 'RETAIL_AI_EVAL_WH'")

    if not args.skip_deploy:
        try:
            deploy_semantic_view(conn)
        except Exception as e:
            print(f"  WARN: SV deploy: {str(e)[:120]}")
        try:
            deploy_agent(conn)
        except Exception as e:
            print(f"  WARN: Agent deploy: {str(e)[:120]}")

    if not args.skip_eval:
        run_first_eval(conn)

    if not args.skip_populate:
        populate_dashboard(conn)

    conn.close()

    if not args.skip_deploy:
        deploy_dashboard_sis()

    print_summary()


if __name__ == "__main__":
    main()
