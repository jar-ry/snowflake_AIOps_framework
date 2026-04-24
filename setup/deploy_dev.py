"""
deploy_dev.py
Deploys semantic view and agent to the DEV environment.
PROD is only deployed via CD pipeline after passing quality gates.

Usage:
    python setup/deploy_dev.py
    SNOWFLAKE_CONNECTION_NAME=myconn python setup/deploy_dev.py
"""
import os
import sys
import snowflake.connector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_connection():
    if os.getenv("SNOWFLAKE_ACCOUNT") and os.getenv("SNOWFLAKE_USER"):
        return snowflake.connector.connect(
            account=os.getenv("SNOWFLAKE_ACCOUNT"),
            user=os.getenv("SNOWFLAKE_USER"),
            password=os.getenv("SNOWFLAKE_PASSWORD"),
            warehouse="RETAIL_AI_EVAL_WH",
        )
    return snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
    )


def deploy_semantic_view(conn):
    sv_path = os.path.join(PROJECT_ROOT, "semantic_views", "dev", "retail_analytics_sv.yaml")
    with open(sv_path) as f:
        yaml_content = f.read()
    conn.cursor().execute(
        "CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML('RETAIL_AI_DEV.SEMANTIC', %s)",
        (yaml_content,),
    )
    print("DEV semantic view deployed: RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV")


def deploy_agent(conn):
    agent_path = os.path.join(PROJECT_ROOT, "agents", "dev", "retail_agent.sql")
    with open(agent_path) as f:
        sql = f.read()
    lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
    full_sql = "\n".join(lines).strip().rstrip(";")
    conn.cursor().execute(full_sql)
    print("DEV agent deployed: RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT")


def main():
    conn = get_connection()
    try:
        deploy_semantic_view(conn)
        deploy_agent(conn)
        print("\nDEV environment ready. PROD will be deployed on merge via CD pipeline.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
