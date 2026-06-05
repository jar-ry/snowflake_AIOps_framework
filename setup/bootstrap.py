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
from utils import load_config as _load_merged_config, instance_dir, instance_path  # noqa: E402


def load_schedule_config(profile: str = "demo") -> dict:
    config_path = os.path.join(instance_dir(), "config", "schedules.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    profiles = config.get("profiles", {})
    if profile not in profiles:
        print(f"  WARN: Schedule profile '{profile}' not found, falling back to 'demo'")
        profile = "demo"
    return profiles[profile]["tasks"]


def load_env_config() -> dict:
    """Merged framework-defaults + active-instance config (see evaluation/utils)."""
    return _load_merged_config()


def build_sql_tokens(cfg: dict) -> dict:
    """Map {{TOKEN}} placeholders in the infra SQL to config values."""
    envs = cfg["environments"]
    dev, prod, ev, roles = envs["dev"], envs["prod"], cfg["eval"], cfg["roles"]
    return {
        "DB_DEV": dev["database"],
        "DB_PROD": prod["database"],
        "DB_EVAL": ev["database"],
        "WAREHOUSE": ev["warehouse"],
        "SCHEMA_ANALYTICS": dev["schema"],
        "SCHEMA_SEMANTIC": dev["semantic_schema"],
        "SCHEMA_RESULTS": ev["schema"],
        "SCHEMA_OBSERVABILITY": ev["observability_schema"],
        "SCHEMA_MONITORING": ev["monitoring_schema"],
        "ROLE_ANALYST": roles["analyst"],
        "ROLE_REVIEWER": roles["reviewer"],
        "ROLE_DEPLOYER": roles["deployer"],
        "ROLE_ADMIN": roles["admin"],
        "SEMANTIC_VIEW_NAME": dev["semantic_view_short"],
        "AGENT_NAME": dev["agent_short"],
        "EVAL_DATASET_TABLE": ev["dataset_table"],
    }


_TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
_SQL_TOKENS = None


def get_sql_tokens() -> dict:
    global _SQL_TOKENS
    if _SQL_TOKENS is None:
        _SQL_TOKENS = build_sql_tokens(load_env_config())
    return _SQL_TOKENS


def render_sql(text: str, tokens: dict = None) -> str:
    """Replace {{TOKEN}} placeholders from config. Fails loudly on any unresolved token.

    The strict [A-Z_] pattern never matches JSON object literals ({"k": ...}) in the SQL.
    """
    tokens = tokens if tokens is not None else get_sql_tokens()

    def repl(m):
        key = m.group(1)
        if key not in tokens:
            raise KeyError(f"Unresolved SQL token {{{{{key}}}}}")
        return tokens[key]

    rendered = _TOKEN_RE.sub(repl, text)
    leftover = _TOKEN_RE.findall(rendered)
    if leftover:
        raise KeyError(f"Unresolved SQL tokens: {sorted(set(leftover))}")
    return rendered


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


def split_sql_statements(sql_clean):
    """Split SQL text into statements, respecting:
      - Single-quoted string literals (including '' escape)
      - $$ dollar-quoted blocks (used for procedure bodies / agent specs)
      - BEGIN...END scripting blocks (semicolons inside are internal separators)

    A semicolon terminates a statement only when all three states are clear.
    The outermost END; closes a BEGIN block and emits the whole block as one statement.
    """
    statements = []
    current = []
    i = 0
    in_single_quote = False
    in_dollar_quote = False
    begin_depth = 0
    n = len(sql_clean)

    def _emit():
        stmt = "".join(current).strip()
        if stmt and not all(line.strip().startswith("--") or not line.strip() for line in stmt.split("\n")):
            statements.append(stmt)

    while i < n:
        char = sql_clean[i]

        # Skip -- line comments verbatim (they can contain ; and ')
        if not in_single_quote and not in_dollar_quote and sql_clean[i:i+2] == "--":
            while i < n and sql_clean[i] != "\n":
                current.append(sql_clean[i])
                i += 1
            continue

        # Skip /* ... */ block comments verbatim
        if not in_single_quote and not in_dollar_quote and sql_clean[i:i+2] == "/*":
            current.append(sql_clean[i])
            current.append(sql_clean[i+1])
            i += 2
            while i < n and sql_clean[i:i+2] != "*/":
                current.append(sql_clean[i])
                i += 1
            if i < n:
                current.append(sql_clean[i])
                current.append(sql_clean[i+1])
                i += 2
            continue

        # Inside $$ ... $$: copy verbatim until closing $$
        if in_dollar_quote:
            current.append(char)
            if sql_clean[i:i+2] == "$$":
                current.append(sql_clean[i+1])
                i += 2
                in_dollar_quote = False
            else:
                i += 1
            continue

        # Open a dollar-quoted block
        if sql_clean[i:i+2] == "$$":
            in_dollar_quote = True
            current.append(char)
            current.append(sql_clean[i+1])
            i += 2
            continue

        # Single-quoted string handling (with '' escape)
        if char == "'" and not in_single_quote:
            in_single_quote = True
            current.append(char)
            i += 1
            continue

        if char == "'" and in_single_quote:
            if i + 1 < n and sql_clean[i+1] == "'":
                current.append(char)
                current.append(sql_clean[i+1])
                i += 2
            else:
                in_single_quote = False
                current.append(char)
                i += 1
            continue

        if in_single_quote:
            current.append(char)
            i += 1
            continue

        # BEGIN / END tracking (only outside strings/dollar-quotes)
        upper_remaining = sql_clean[i:].upper()
        if re.match(r"\bBEGIN\b", upper_remaining):
            begin_depth += 1
            current.append(char)
            i += 1
            continue

        if re.match(r"\bEND\s*;", upper_remaining) and begin_depth > 0:
            # Consume "END" letters then the terminating ;
            current.append(char)
            i += 1
            while i < n and sql_clean[i] != ";":
                current.append(sql_clean[i])
                i += 1
            if i < n:
                current.append(sql_clean[i])
                i += 1
            begin_depth -= 1
            if begin_depth == 0:
                _emit()
                current = []
            continue

        # Plain statement terminator
        if char == ";" and begin_depth == 0:
            _emit()
            current = []
            i += 1
            continue

        current.append(char)
        i += 1

    # Flush remainder
    tail = "".join(current).strip()
    if tail and not all(line.strip().startswith("--") or not line.strip() for line in tail.split("\n")):
        statements.append(tail)

    return statements


def run_sql_file(conn, filepath, description):
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"  {filepath}")
    print(f"{'='*60}")

    with open(filepath) as f:
        sql = f.read()

    # Render {{TOKEN}} placeholders from config FIRST, so the USE-stripping
    # regexes below (which match real identifiers) still apply.
    sql = render_sql(sql)

    sql_clean = re.sub(r"(?i)^\s*USE\s+ROLE\s+\w+\s*;", "", sql, flags=re.MULTILINE)
    sql_clean = re.sub(r"(?i)^\s*USE\s+WAREHOUSE\s+\w+\s*;", "", sql_clean, flags=re.MULTILINE)
    sql_clean = re.sub(r"(?i)^\s*USE\s+DATABASE\s+\w+\s*;", "", sql_clean, flags=re.MULTILINE)
    sql_clean = re.sub(r"(?i)^\s*USE\s+SCHEMA\s+[\w.]+\s*;", "", sql_clean, flags=re.MULTILINE)

    statements = split_sql_statements(sql_clean)

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
    import deploy as deploy_mod
    where = deploy_mod.deploy_semantic_view(conn, "dev")
    print(f"  OK: {where}")


def deploy_agent(conn):
    print(f"\n{'='*60}")
    print(f"  Deploying DEV Agent")
    print(f"{'='*60}")
    import deploy as deploy_mod
    where = deploy_mod.deploy_agent(conn, "dev")
    print(f"  OK: deployed agent from {where}")


def transfer_ci_ownership(conn):
    """Hand the CI-managed DEV objects to the deployer role so CI (running as that
    role) can CREATE OR REPLACE them. bootstrap runs as an admin role and would
    otherwise own them, blocking the deployer's redeploys (see #22/#34)."""
    cfg = load_env_config()
    dev = cfg["environments"]["dev"]
    deployer = cfg["roles"]["deployer"]
    db, sem = dev["database"], dev["semantic_schema"]
    objects = [
        ("AGENT", f"{db}.{sem}.{dev['agent_short']}"),
        ("SEMANTIC VIEW", f"{db}.{sem}.{dev['semantic_view_short']}"),
    ]
    print(f"\n{'='*60}\n  Transferring CI object ownership -> {deployer}\n{'='*60}")
    cur = conn.cursor()
    for obj_type, fqn in objects:
        try:
            cur.execute(f"GRANT OWNERSHIP ON {obj_type} {fqn} TO ROLE {deployer} COPY CURRENT GRANTS")
            print(f"  OK: {fqn} -> {deployer}")
        except Exception as e:
            print(f"  WARN: ownership {fqn}: {str(e)[:100]}")


def run_first_eval(conn):
    print(f"\n{'='*60}")
    print(f"  Running First Evaluation (SV audit on DEV)")
    print(f"{'='*60}")
    try:
        audit_path = os.path.join(PROJECT_ROOT, "evaluation", "audit_semantic_view.py")
        ddl_path = instance_path(load_env_config()["environments"]["dev"]["sv_yaml_path"])
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
    config = load_env_config()
    pricing = config.get("pricing", {})
    # Cache-aware credit formula (single source: evaluation/utils.build_credits_expr).
    from utils import build_credits_expr
    credits_expr = build_credits_expr(pricing)

    # Config-derived names (genericize embedded SQL)
    ev = config["eval"]; envs = config["environments"]
    db_eval = ev["database"]; wh = ev["warehouse"]
    mon = ev["monitoring_schema"]; obs = ev["observability_schema"]
    db_prod = envs["prod"]["database"]; sem = envs["prod"]["semantic_schema"]

    tasks = [
        ("TASK_DAILY_USAGE_AGGREGATION", schedules["usage_aggregation"]["schedule"], f"""
            INSERT INTO {db_eval}.{mon}.USAGE_METRICS (
                metric_date, environment, service_type, agent_or_sv_name,
                total_requests, successful_requests, failed_requests,
                total_input_tokens, total_output_tokens, total_tokens, total_cache_read_tokens,
                estimated_credits, avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms, unique_users)
            SELECT CURRENT_DATE(), COALESCE(database_name, 'UNKNOWN'),
                CASE WHEN span_name LIKE 'ReasoningAgentStep%' OR span_name LIKE 'CodingAgent%' THEN 'cortex_agent'
                     WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst' ELSE 'other' END,
                COALESCE(agent_name, 'unknown'),
                COUNT(DISTINCT trace_id), COUNT_IF(status_code = 'STATUS_CODE_OK'), COUNT_IF(status_code != 'STATUS_CODE_OK'),
                COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0), COALESCE(SUM(cache_read_tokens),0),
                SUM({credits_expr}), AVG(planning_duration_ms),
                APPROX_PERCENTILE(planning_duration_ms,0.5), APPROX_PERCENTILE(planning_duration_ms,0.95),
                APPROX_PERCENTILE(planning_duration_ms,0.99), 0
            FROM {db_eval}.{obs}.AGENT_TRACES
            WHERE event_time >= DATEADD('hour',-24,CURRENT_TIMESTAMP())
              AND (span_name LIKE 'ReasoningAgentStepPlanning%' OR span_name LIKE 'CodingAgent.Step%' OR span_name ILIKE '%Analyst%')
            GROUP BY 1,2,3,4"""),
        ("TASK_DAILY_FEEDBACK_ANALYSIS", schedules["feedback_analysis"]["schedule"], f"""
            UPDATE {db_eval}.{mon}.USER_FEEDBACK
            SET sentiment_score = SNOWFLAKE.CORTEX.SENTIMENT(COALESCE(feedback_text,'') || ' Rating: ' || feedback_rating::STRING)
            WHERE sentiment_score IS NULL AND (feedback_text IS NOT NULL OR feedback_rating IS NOT NULL)"""),
        ("TASK_DAILY_HEALTH_CHECKS", schedules["health_checks"]["schedule"], f"""
            INSERT INTO {db_eval}.{mon}.HEALTH_CHECK_RESULTS (check_name, environment, target_name, status, details, latency_ms)
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
            cur.execute(f"""CREATE OR REPLACE TASK {db_eval}.{mon}.{name}
                WAREHOUSE = {wh} SCHEDULE = '{schedule}' AS {body}""")
            cur.execute(f"ALTER TASK {db_eval}.{mon}.{name} RESUME")
            print(f"  OK: {name}")
        except Exception as e:
            print(f"  WARN: {name}: {str(e)[:100]}")

    procs = {
        "SP_WEEKLY_SV_EVAL": """
CREATE OR REPLACE PROCEDURE {{DB_EVAL}}.MONITORING.SP_WEEKLY_SV_EVAL()
RETURNS STRING LANGUAGE SQL EXECUTE AS CALLER AS
$$
BEGIN
    LET sv_name STRING := '{{DB_PROD}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}}';
    LET start_ts TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    LET status STRING := 'HEALTHY';
    LET details STRING := '';
    BEGIN
        -- SQL-native liveness: confirm the semantic view exists / is accessible.
        LET stmt STRING := 'DESCRIBE SEMANTIC VIEW ' || :sv_name;
        EXECUTE IMMEDIATE :stmt;
        LET latency INTEGER := DATEDIFF('millisecond', :start_ts, CURRENT_TIMESTAMP());
        INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        SELECT 'weekly_sv_smoke_test','prod',:sv_name,100,0,TRUE,1,1,0, OBJECT_CONSTRUCT('check','sv_exists','latency_ms', :latency);
        details := 'Passed in ' || :latency || 'ms';
    EXCEPTION WHEN OTHER THEN
        LET err STRING := SQLERRM;
        status := 'UNHEALTHY'; details := 'Failed: ' || :err;
        INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        SELECT 'weekly_sv_smoke_test','prod',:sv_name,0,0,FALSE,1,0,1, OBJECT_CONSTRUCT('error', :err);
    END;
    INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS (check_name, environment, target_name, status, details, latency_ms)
    VALUES ('weekly_sv_smoke_test','prod',:sv_name,:status,:details,0);
    RETURN :status || ': ' || :details;
END;
$$""",
        "SP_WEEKLY_AGENT_EVAL": """
CREATE OR REPLACE PROCEDURE {{DB_EVAL}}.MONITORING.SP_WEEKLY_AGENT_EVAL()
RETURNS STRING LANGUAGE SQL EXECUTE AS CALLER AS
$$
BEGIN
    LET agent_name STRING := '{{DB_PROD}}.SEMANTIC.{{AGENT_NAME}}';
    LET start_ts TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    LET status STRING := 'HEALTHY';
    LET details STRING := '';
    BEGIN
        -- SQL-native liveness: confirm the agent exists / is accessible.
        LET stmt STRING := 'DESCRIBE AGENT ' || :agent_name;
        EXECUTE IMMEDIATE :stmt;
        LET latency INTEGER := DATEDIFF('millisecond', :start_ts, CURRENT_TIMESTAMP());
        INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        SELECT 'weekly_agent_smoke_test','prod',:agent_name,100,0,TRUE,1,1,0, OBJECT_CONSTRUCT('check','agent_exists','latency_ms', :latency);
        details := 'Passed in ' || :latency || 'ms';
    EXCEPTION WHEN OTHER THEN
        LET err STRING := SQLERRM;
        status := 'UNHEALTHY'; details := 'Failed: ' || :err;
        INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS (run_type, environment, target_name, accuracy_pct, threshold_pct, passed_threshold, total_questions, passed_questions, failed_questions, run_details)
        SELECT 'weekly_agent_smoke_test','prod',:agent_name,0,0,FALSE,1,0,1, OBJECT_CONSTRUCT('error', :err);
    END;
    INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS (check_name, environment, target_name, status, details, latency_ms)
    VALUES ('weekly_agent_smoke_test','prod',:agent_name,:status,:details,0);
    RETURN :status || ': ' || :details;
END;
$$""",
    }

    weekly_tasks = [
        ("TASK_WEEKLY_SV_EVAL", schedules["weekly_sv_eval"]["schedule"], f"CALL {db_eval}.{mon}.SP_WEEKLY_SV_EVAL()"),
        ("TASK_WEEKLY_AGENT_EVAL", schedules["weekly_agent_eval"]["schedule"], f"CALL {db_eval}.{mon}.SP_WEEKLY_AGENT_EVAL()"),
    ]

    for name, sql in procs.items():
        try:
            cur.execute(render_sql(sql))
            print(f"  OK: {name}")
        except Exception as e:
            print(f"  WARN: {name}: {str(e)[:100]}")

    # PROD smoke-test tasks are NOT created here. They are created by the CD
    # pipeline after the first successful PROD deployment (semantic_view_cd.yml
    # and agent_cd.yml). This avoids spam failures while PROD is empty.
    print(f"  SKIP: TASK_WEEKLY_SV_EVAL, TASK_WEEKLY_AGENT_EVAL (created by CD pipeline on first PROD deploy)")


def deploy_dashboard_sis():
    print(f"\n{'='*60}")
    print(f"  Deploying Monitoring Dashboard (Streamlit in Snowflake)")
    print(f"{'='*60}")
    try:
        import subprocess
        monitoring_dir = os.path.join(PROJECT_ROOT, "monitoring")
        # Render the SiS descriptor from the active instance config before deploy.
        # snow reads snowflake.yml from disk; the tracked artifact is the template.
        template_path = os.path.join(monitoring_dir, "snowflake.yml.template")
        rendered_path = os.path.join(monitoring_dir, "snowflake.yml")
        with open(template_path) as tf:
            with open(rendered_path, "w") as rf:
                rf.write(render_sql(tf.read()))
        ev = load_env_config()["eval"]
        dashboard_fqn = f"{ev['database']}.{ev['monitoring_schema']}.AI_MONITORING_DASHBOARD"
        conn_name = os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
        result = subprocess.run(
            ["snow", "streamlit", "deploy", "--replace", "--connection", conn_name],
            capture_output=True,
            text=True,
            cwd=monitoring_dir,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"  OK: AI_MONITORING_DASHBOARD deployed to {dashboard_fqn}")
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


def run_example_seed(conn):
    """Invoke the active instance's configured demo-seeding module (if any).

    The framework stays domain-agnostic: each example owns its seed logic and
    exposes a seed(conn) entry point. Configured via the example.seed_module key.
    """
    cfg = load_env_config()
    seed_rel = cfg.get("example", {}).get("seed_module")
    if not seed_rel:
        print("  No example seed_module configured; skipping demo seeding.")
        return
    seed_path = instance_path(seed_rel)
    if not os.path.exists(seed_path):
        print(f"  SKIP: seed module not found ({seed_rel})")
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("example_seed", seed_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "seed"):
        mod.seed(conn)
    else:
        print(f"  WARN: seed module {seed_rel} has no seed(conn) entry point")

def print_summary():
    print(f"\n{'='*60}")
    print(f"  SETUP COMPLETE")
    print(f"{'='*60}")
    cfg = load_env_config()
    dev = cfg["environments"]["dev"]
    ev = cfg["eval"]
    roles = cfg["roles"]
    print(f"""
  What was created:
    Databases:     {dev['database']}, {cfg['environments']['prod']['database']}, {ev['database']}
    RBAC:          4 roles ({roles['analyst']}, {roles['reviewer']}, {roles['deployer']}, {roles['admin']})
    Observability: views over ai_observability_events
    Monitoring:    tables, views, tasks (running), alerts (active)
    Dashboard:     {ev['database']}.{ev['monitoring_schema']}.AI_MONITORING_DASHBOARD (SiS)
    Semantic View: {dev['semantic_view']}
    Agent:         {dev['agent_name']}
    Example data:  seeded from the active instance ({instance_dir()})

  PROD is empty — SV and agent are deployed on merge via CD pipeline.

  Next steps:
    1. Open the dashboard in Snowsight:
       Projects → Streamlit → AI_MONITORING_DASHBOARD
    2. Chat with the agent in Snowsight:
       AI & ML → Agents → {dev['agent_short']}
    3. Push to GitHub and open a PR to test CI/CD
""")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap the AI Evaluation Framework")
    parser.add_argument("--example", default="examples/retail",
                        help="Instance/example directory to set up (default: examples/retail)")
    parser.add_argument("--render", metavar="SQL_FILE",
                        help="Render a token SQL file against the active instance config and print to stdout (no execution)")
    parser.add_argument("--skip-sql", action="store_true", help="Skip SQL setup (if already run)")
    parser.add_argument("--skip-deploy", action="store_true", help="Skip SV/agent deployment")
    parser.add_argument("--skip-eval", action="store_true", help="Skip first evaluation")
    parser.add_argument("--skip-populate", action="store_true", help="Skip dashboard population (health check + eval + agent queries)")
    parser.add_argument("--schedule-profile", default="demo", choices=["demo", "prod"],
                        help="Task schedule profile: 'demo' (every 15 min) or 'prod' (realistic daily/weekly)")
    args = parser.parse_args()

    # Resolve the active instance. AIOPS_INSTANCE drives all config + path lookups
    # (evaluation/utils). Set it before any config is read. An absolute --example
    # is honoured as-is; a relative one resolves against the repo root.
    if not os.environ.get("AIOPS_INSTANCE"):
        example = args.example if os.path.isabs(args.example) else os.path.join(PROJECT_ROOT, args.example)
        os.environ["AIOPS_INSTANCE"] = os.path.abspath(example)

    if args.render:
        with open(args.render) as f:
            sys.stdout.write(render_sql(f.read()))
        return

    print("\n" + "="*60)
    print("  AI EVALUATION FRAMEWORK — BOOTSTRAP")
    print("="*60)
    print(f"  Instance: {instance_dir()}")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE()")
    account, user, role = cur.fetchone()
    print(f"  Account:  {account}")
    print(f"  User:     {user}")
    print(f"  Role:     {role}")

    wh = load_env_config()["eval"]["warehouse"]

    if not args.skip_sql:
        # Framework infrastructure scripts (domain-agnostic, token-rendered).
        sql_scripts = [
            ("setup/01_create_databases.sql", "Framework 1/8: Create databases, schemas, eval tables, warehouse"),
            ("setup/04_rbac_setup.sql", "Framework 2/8: Create RBAC roles and grants"),
            ("setup/05_observability_setup.sql", "Framework 3/8: Create observability views"),
            ("setup/07_monitoring_tables.sql", "Framework 4/8: Create monitoring tables"),
            ("setup/08_monitoring_tasks.sql", "Framework 5/8: Create monitoring tasks"),
            ("setup/09_monitoring_views.sql", "Framework 6/8: Create monitoring views"),
            ("setup/10_monitoring_alerts.sql", "Framework 7/8: Create monitoring alerts"),
            ("setup/11_interaction_quality_engine.sql", "Framework 8/8: Create interaction quality engine"),
        ]

        cur.execute(f"CREATE WAREHOUSE IF NOT EXISTS {wh} WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE")
        cur.execute(f"USE WAREHOUSE {wh}")

        for script, desc in sql_scripts:
            filepath = os.path.join(PROJECT_ROOT, script)
            if os.path.exists(filepath):
                run_sql_file(conn, filepath, desc)
            else:
                print(f"  SKIP: {script} (not found)")

        # Example/instance data scripts (domain-specific), run after framework infra.
        data_scripts = load_env_config().get("example", {}).get("data_scripts", [])
        for i, rel in enumerate(data_scripts, 1):
            filepath = instance_path(rel)
            if os.path.exists(filepath):
                run_sql_file(conn, filepath, f"Example data {i}/{len(data_scripts)}: {rel}")
            else:
                print(f"  SKIP: {rel} (not found)")

        create_tasks_directly(cur, schedule_profile=args.schedule_profile)
    else:
        print("\n  Skipping SQL setup (--skip-sql)")
        cur.execute(f"USE WAREHOUSE {wh}")

    if not args.skip_sql:
        cur.execute(f"ALTER USER {user} SET DEFAULT_WAREHOUSE = '{wh}'")

    if not args.skip_deploy:
        try:
            deploy_semantic_view(conn)
        except Exception as e:
            print(f"  WARN: SV deploy: {str(e)[:120]}")
        try:
            deploy_agent(conn)
        except Exception as e:
            print(f"  WARN: Agent deploy: {str(e)[:120]}")
        transfer_ci_ownership(conn)

    if not args.skip_eval:
        run_first_eval(conn)

    if not args.skip_populate:
        run_example_seed(conn)

    conn.close()

    if not args.skip_deploy:
        deploy_dashboard_sis()

    print_summary()


if __name__ == "__main__":
    main()
