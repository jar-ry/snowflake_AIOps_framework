"""
utils.py
Shared utilities for the evaluation framework.
"""
import os
import json
import yaml
import snowflake.connector
from datetime import datetime


def _load_private_key(key_path: str) -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    with open(os.path.expanduser(key_path), "rb") as f:
        p_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _resolve_connection_params(connection_name: str) -> dict:
    try:
        import tomli
    except ImportError:
        import tomllib as tomli
    toml_path = os.path.expanduser("~/.snowflake/connections.toml")
    if not os.path.exists(toml_path):
        return {}
    with open(toml_path, "rb") as f:
        config = tomli.load(f)
    return config.get(connection_name, {})


def get_connection(environment: str = "dev") -> snowflake.connector.SnowflakeConnection:
    config = load_config()
    env_config = config["environments"][environment]

    if os.getenv("SNOWFLAKE_ACCOUNT") and os.getenv("SNOWFLAKE_USER"):
        conn = snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            warehouse=env_config["warehouse"],
        )
    else:
        conn_name = os.getenv("SNOWFLAKE_CONNECTION_NAME") or env_config.get("connection_name", "default")
        params = _resolve_connection_params(conn_name)
        key_path = params.get("private_key_path") or params.get("private_key_file")
        if key_path and params.get("authenticator") in ("snowflake_jwt", "SNOWFLAKE_JWT"):
            conn = snowflake.connector.connect(
                account=params["account"],
                user=params["user"],
                private_key=_load_private_key(key_path),
                role=params.get("role"),
                warehouse=env_config["warehouse"],
            )
        else:
            conn = snowflake.connector.connect(connection_name=conn_name)
            conn.cursor().execute(f"USE WAREHOUSE {env_config['warehouse']}")

    conn.cursor().execute(f"USE DATABASE {env_config['database']}")
    conn.cursor().execute(f"USE SCHEMA {env_config.get('semantic_schema', env_config['schema'])}")
    return conn


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "environments.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_thresholds() -> dict:
    threshold_path = os.path.join(os.path.dirname(__file__), "..", "config", "thresholds.yaml")
    with open(threshold_path, "r") as f:
        return yaml.safe_load(f)


def get_llm_model(role: str = "model") -> str:
    config = load_config()
    llm_config = config.get("llm", {})
    return llm_config.get(role, llm_config.get("model", "claude-opus-4-7"))


def load_question_bank(bank_type: str, difficulty: str) -> list:
    path = os.path.join(
        os.path.dirname(__file__), "..", "question_banks", bank_type, f"{difficulty}_questions.yaml"
    )
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("questions", [])


def execute_sql(conn: snowflake.connector.SnowflakeConnection, sql: str) -> list:
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


def call_cortex_analyst(conn: snowflake.connector.SnowflakeConnection, semantic_view: str, question: str) -> dict:
    config = load_config()
    env_key = None
    for env, ecfg in config.get("environments", {}).items():
        if ecfg.get("semantic_view") == semantic_view:
            env_key = env
            break
    agent_name = config["environments"].get(env_key or "dev", {}).get("agent_name")
    if agent_name:
        agent_resp = call_cortex_agent(conn, agent_name, question)
        content = agent_resp.get("content", [])
        sql_stmt = ""
        text_resp = ""
        for item in content:
            if item.get("type") == "tool_result":
                tool_content = item.get("tool_result", {}).get("content", [])
                for tc in tool_content:
                    if isinstance(tc, dict) and tc.get("type") == "json":
                        sql_stmt = tc.get("json", {}).get("sql", "")
                        text_resp = tc.get("json", {}).get("text", "")
            elif item.get("type") == "text":
                text_resp = text_resp or item.get("text", "")
        return {
            "choices": [{
                "messages": [
                    {"type": "sql", "statement": sql_stmt},
                    {"type": "text", "text": text_resp},
                ]
            }]
        }
    return {}


def call_cortex_agent(
    conn: snowflake.connector.SnowflakeConnection,
    agent_name: str,
    question: str
) -> dict:
    escaped = question.replace("\\", "\\\\").replace('"', '\\"')
    request_body = json.dumps({
        "messages": [{"role": "user", "content": [{"type": "text", "text": escaped}]}]
    })
    sql = f"SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN('{agent_name}', $${request_body}$$) AS response"
    cursor = conn.cursor()
    cursor.execute(sql)
    result = cursor.fetchone()
    if result:
        return json.loads(result[0]) if isinstance(result[0], str) else result[0]
    return {}


def llm_complete(conn: snowflake.connector.SnowflakeConnection, model: str, prompt: str) -> str:
    escaped = prompt.replace("'", "''").replace("\\", "\\\\")
    sql = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{escaped}') AS response"
    cursor = conn.cursor()
    cursor.execute(sql)
    result = cursor.fetchone()
    return result[0] if result else ""


def log_eval_run(
    conn: snowflake.connector.SnowflakeConnection,
    table: str,
    run_data: dict
):
    columns = ", ".join(run_data.keys())
    values = ", ".join([
        f"'{v}'" if isinstance(v, str) else
        f"PARSE_JSON('{json.dumps(v)}')" if isinstance(v, (dict, list)) else
        str(v)
        for v in run_data.values()
    ])
    sql = f"INSERT INTO RETAIL_AI_EVAL.RESULTS.{table} ({columns}) VALUES ({values})"
    conn.cursor().execute(sql)


def format_results_table(results: list) -> str:
    if not results:
        return "No results"
    headers = list(results[0].keys())
    rows = [[str(row.get(h, "")) for h in headers] for row in results]
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep_line = "-+-".join("-" * w for w in widths)
    data_lines = [" | ".join(r[i].ljust(widths[i]) for i in range(len(headers))) for r in rows]
    return "\n".join([header_line, sep_line] + data_lines)
