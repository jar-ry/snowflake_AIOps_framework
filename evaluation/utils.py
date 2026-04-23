"""
utils.py
Shared utilities for the evaluation framework.
"""
import os
import json
import yaml
import snowflake.connector
from datetime import datetime


def get_connection(environment: str = "dev") -> snowflake.connector.SnowflakeConnection:
    config = load_config()
    env_config = config["environments"][environment]
    conn = snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or env_config.get("connection_name", "default")
    )
    conn.cursor().execute(f"USE DATABASE {env_config['database']}")
    conn.cursor().execute(f"USE SCHEMA {env_config['schema']}")
    conn.cursor().execute(f"USE WAREHOUSE {env_config['warehouse']}")
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
    return llm_config.get(role, llm_config.get("model", "claude-4-opus"))


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
    sql = f"""
    SELECT SNOWFLAKE.CORTEX.COMPLETE(
        'analyst',
        OBJECT_CONSTRUCT(
            'messages', ARRAY_CONSTRUCT(
                OBJECT_CONSTRUCT('role', 'user', 'content', ARRAY_CONSTRUCT(
                    OBJECT_CONSTRUCT('type', 'text', 'text', '{question.replace("'", "''")}')
                ))
            ),
            'semantic_model', OBJECT_CONSTRUCT(
                'semantic_view', '{semantic_view}'
            )
        )
    ) AS response
    """
    cursor = conn.cursor()
    cursor.execute(sql)
    result = cursor.fetchone()
    if result:
        return json.loads(result[0]) if isinstance(result[0], str) else result[0]
    return {}


def call_cortex_agent(
    conn: snowflake.connector.SnowflakeConnection,
    agent_name: str,
    question: str
) -> dict:
    sql = f"""
    SELECT SNOWFLAKE.CORTEX.COMPLETE(
        'agent',
        OBJECT_CONSTRUCT(
            'agent_name', '{agent_name}',
            'messages', ARRAY_CONSTRUCT(
                OBJECT_CONSTRUCT('role', 'user', 'content', '{question.replace("'", "''")}')
            )
        )
    ) AS response
    """
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
