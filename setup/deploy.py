"""
deploy.py
Deploy the semantic view or the agent to a target environment using the shared,
key-pair-capable connection from evaluation/utils.get_connection().

This replaces the inline, password-only `snowflake.connector.connect(...)` logic
that used to be embedded in each CI/CD workflow, so every deployment honours the
same authentication (key-pair in CI, connections.toml locally) from one place.

Usage:
    python setup/deploy.py --target semantic_view --environment dev
    python setup/deploy.py --target agent --environment prod
"""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "evaluation"))
from utils import get_connection, load_config, instance_dir  # noqa: E402


def _strip_sql_comments(sql: str) -> str:
    lines = [ln for ln in sql.split("\n") if not ln.strip().startswith("--")]
    return "\n".join(lines).strip().rstrip(";")


def deploy_agent(conn, environment: str) -> str:
    cfg = load_config()["environments"][environment]
    path = os.path.join(instance_dir(), cfg["agent_sql_path"])
    with open(path) as f:
        sql = _strip_sql_comments(f.read())
    conn.cursor().execute(sql)
    return os.path.relpath(path, instance_dir())


def deploy_semantic_view(conn, environment: str) -> str:
    cfg = load_config()["environments"][environment]
    target = f"{cfg['database']}.{cfg.get('semantic_schema', cfg['schema'])}"
    path = os.path.join(instance_dir(), cfg["sv_yaml_path"])
    with open(path) as f:
        yaml_content = f.read()
    # Target schema is derived from config (validated env), yaml passed as a bind param.
    conn.cursor().execute(
        f"CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML('{target}', %s)", (yaml_content,)
    )
    return f"{target} (from {os.path.relpath(path, instance_dir())})"


def main():
    parser = argparse.ArgumentParser(description="Deploy the SV or agent to an environment.")
    parser.add_argument("--target", required=True, choices=["agent", "semantic_view"])
    parser.add_argument("--environment", required=True, choices=["dev", "prod"])
    args = parser.parse_args()

    conn = get_connection(args.environment)
    try:
        if args.target == "agent":
            where = deploy_agent(conn, args.environment)
            print(f"Agent deployed to {args.environment.upper()}: {where}")
        else:
            where = deploy_semantic_view(conn, args.environment)
            print(f"Semantic view deployed to {args.environment.upper()}: {where}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
