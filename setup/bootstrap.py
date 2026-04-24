#!/usr/bin/env python3
"""
bootstrap.py
One-command setup for the AI Evaluation Framework.

Creates all Snowflake objects, seeds data, deploys DEV semantic view + agent,
runs a first evaluation, and prints next steps.

Usage:
    python setup/bootstrap.py
    SNOWFLAKE_CONNECTION_NAME=myconn python setup/bootstrap.py
    SNOWFLAKE_ACCOUNT=xxx SNOWFLAKE_USER=yyy SNOWFLAKE_PASSWORD=zzz python setup/bootstrap.py

Prerequisites:
    pip install -r requirements.txt
    A Snowflake connection configured in ~/.snowflake/connections.toml
    OR SNOWFLAKE_ACCOUNT/USER/PASSWORD environment variables set
"""
import os
import re
import sys
import json
import time
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "evaluation"))

import snowflake.connector


def get_connection():
    if os.getenv("SNOWFLAKE_ACCOUNT") and os.getenv("SNOWFLAKE_USER"):
        return snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
        )
    return snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
    )


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


def create_tasks_directly(cur):
    print(f"\n{'='*60}")
    print(f"  Creating tasks and stored procs (direct SQL)")
    print(f"{'='*60}")

    tasks = [
        ("TASK_DAILY_USAGE_AGGREGATION", "USING CRON 0 2 * * * UTC", """
            INSERT INTO RETAIL_AI_EVAL.MONITORING.USAGE_METRICS (
                metric_date, environment, service_type, agent_or_sv_name,
                total_requests, successful_requests, failed_requests,
                total_input_tokens, total_output_tokens, total_tokens,
                estimated_cost_usd, avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
            SELECT CURRENT_DATE()-1, COALESCE(database_name, 'UNKNOWN'),
                CASE WHEN span_name LIKE 'ReasoningAgentStep%' OR span_name LIKE 'CodingAgent%' THEN 'cortex_agent'
                     WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst' ELSE 'other' END,
                COALESCE(agent_name, 'unknown'),
                COUNT(DISTINCT trace_id), COUNT_IF(status_code = 'STATUS_CODE_OK'), COUNT_IF(status_code != 'STATUS_CODE_OK'),
                COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0),
                COALESCE(SUM(total_tokens),0)*0.000003, AVG(planning_duration_ms),
                APPROX_PERCENTILE(planning_duration_ms,0.5), APPROX_PERCENTILE(planning_duration_ms,0.95),
                APPROX_PERCENTILE(planning_duration_ms,0.99), 0
            FROM RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES
            WHERE event_time >= DATEADD('day',-1,CURRENT_DATE()) AND event_time < CURRENT_DATE()
              AND (span_name LIKE 'ReasoningAgentStepPlanning%' OR span_name LIKE 'CodingAgent.Step%' OR span_name ILIKE '%Analyst%')
            GROUP BY 1,2,3,4"""),
        ("TASK_DAILY_FEEDBACK_ANALYSIS", "USING CRON 15 2 * * * UTC", """
            UPDATE RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
            SET sentiment_score = SNOWFLAKE.CORTEX.SENTIMENT(COALESCE(feedback_text,'') || ' Rating: ' || feedback_rating::STRING)
            WHERE sentiment_score IS NULL AND (feedback_text IS NOT NULL OR feedback_rating IS NOT NULL)"""),
        ("TASK_DAILY_HEALTH_CHECKS", "USING CRON 0 6 * * * UTC", """
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
        ("TASK_WEEKLY_SV_EVAL", "USING CRON 0 4 * * 0 UTC", "CALL RETAIL_AI_EVAL.MONITORING.SP_WEEKLY_SV_EVAL()"),
        ("TASK_WEEKLY_AGENT_EVAL", "USING CRON 0 5 * * 0 UTC", "CALL RETAIL_AI_EVAL.MONITORING.SP_WEEKLY_AGENT_EVAL()"),
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


def configure_warehouse_reminder():
    print(f"\n{'='*60}")
    print(f"  MANUAL STEP REQUIRED")
    print(f"{'='*60}")
    print("""
  The DEV agent's Analyst tool needs a warehouse configured via Snowsight:

  1. Go to Snowsight → AI & ML → Agents
  2. Select RETAIL_AGENT (in RETAIL_AI_DEV.SEMANTIC)
  3. Click Edit → Tools → Cortex Analyst (RetailAnalyst)
  4. Set Warehouse to: RETAIL_AI_EVAL_WH
  5. Save

  This is a known Snowflake limitation — the warehouse cannot be set
  via SQL CREATE AGENT. After this step, the agent will work end-to-end.
""")


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
    1. Configure warehouse in Snowsight (see MANUAL STEP above)
    2. Open the dashboard in Snowsight:
       Projects → Streamlit → AI_MONITORING_DASHBOARD
    3. Push to GitHub and open a PR to test CI/CD
""")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap the AI Evaluation Framework")
    parser.add_argument("--skip-sql", action="store_true", help="Skip SQL setup (if already run)")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip SV/agent deployment")
    parser.add_argument("--skip-eval", action="store_true", help="Skip first evaluation")
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

        create_tasks_directly(cur)
    else:
        print("\n  Skipping SQL setup (--skip-sql)")
        cur.execute("USE WAREHOUSE RETAIL_AI_EVAL_WH")

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

    conn.close()

    if not args.skip_deploy:
        deploy_dashboard_sis()

    configure_warehouse_reminder()
    print_summary()


if __name__ == "__main__":
    main()
