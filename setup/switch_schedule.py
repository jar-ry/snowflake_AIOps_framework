#!/usr/bin/env python3
"""
switch_schedule.py
Flip monitoring tasks between schedule profiles (demo vs prod) without a full
redeploy.

Reads config/schedules.yaml and executes ALTER TASK for each configured task.
Tasks must exist (bootstrap already run).

Usage:
    python setup/switch_schedule.py --profile demo
    python setup/switch_schedule.py --profile prod
    python setup/switch_schedule.py --profile demo --dry-run
    SNOWFLAKE_CONNECTION_NAME=COCO_demo_connection python setup/switch_schedule.py --profile demo
"""
import argparse
import os
import sys

import snowflake.connector
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULES_PATH = os.path.join(PROJECT_ROOT, "config", "schedules.yaml")
TASK_SCHEMA = "RETAIL_AI_EVAL.MONITORING"


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


def load_profile(profile):
    with open(SCHEDULES_PATH) as f:
        config = yaml.safe_load(f)
    profiles = config.get("profiles", {})
    if profile not in profiles:
        available = ", ".join(profiles.keys()) or "(none)"
        print(f"ERROR: profile '{profile}' not found. Available: {available}")
        sys.exit(1)
    return profiles[profile]


def get_current_schedule(cur, task_name):
    cur.execute(f"SHOW TASKS LIKE '{task_name}' IN SCHEMA {TASK_SCHEMA}")
    rows = cur.fetchall()
    if not rows:
        return None
    cols = [c[0].lower() for c in cur.description]
    row = dict(zip(cols, rows[0]))
    return row.get("schedule")


def switch(profile, dry_run):
    profile_data = load_profile(profile)
    tasks = profile_data.get("tasks", {})

    print(f"{'=' * 60}")
    print(f"  SWITCH SCHEDULE PROFILE -> {profile}")
    if dry_run:
        print(f"  (DRY RUN — no changes will be applied)")
    print(f"  {profile_data.get('description', '')}")
    print(f"{'=' * 60}")

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("USE WAREHOUSE RETAIL_AI_EVAL_WH")

        applied = 0
        skipped = 0
        for task_key, task_cfg in tasks.items():
            task_name = task_cfg["name"]
            new_schedule = task_cfg["schedule"]
            fqn = f"{TASK_SCHEMA}.{task_name}"

            current = get_current_schedule(cur, task_name)
            if current is None:
                print(f"  SKIP {task_name}: task does not exist")
                skipped += 1
                continue

            new_cron = new_schedule.replace("USING CRON ", "").strip()
            current_cron = (current or "").replace("USING CRON ", "").strip()
            if current_cron == new_cron:
                print(f"  OK   {task_name}: already on '{current_cron}'")
                applied += 1
                continue

            print(f"  {'DRY' if dry_run else 'SET'}  {task_name}: '{current_cron}' -> '{new_cron}'")
            if not dry_run:
                cur.execute(f"ALTER TASK {fqn} SUSPEND")
                cur.execute(f"ALTER TASK {fqn} SET SCHEDULE = 'USING CRON {new_cron}'")
                cur.execute(f"ALTER TASK {fqn} RESUME")
            applied += 1

        print(f"{'=' * 60}")
        print(f"  Applied: {applied} | Skipped: {skipped}")
        print(f"{'=' * 60}")
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True, help="Profile name from config/schedules.yaml (e.g. demo, prod)")
    ap.add_argument("--dry-run", action="store_true", help="Print changes without applying")
    args = ap.parse_args()
    switch(args.profile, args.dry_run)


if __name__ == "__main__":
    main()
