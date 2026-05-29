# Platform quirks

> Status: Stable | Last reviewed: 2026-05-26 | Audience: Engineers, operators

**Purpose.** A single source of truth for the Snowflake platform limitations this framework has encountered, the workarounds applied, and each item's current status. Review this list when something behaves unexpectedly, and retire items here when the platform fixes them upstream.

## How to use this document

Each quirk lists: the symptom, the workaround, where it is handled in the codebase, and a status. Statuses are:

- **Active** — the limitation still applies; the workaround is required.
- **Resolved** — no longer applies in the primary code path; kept here for historical context.
- **Partial** — resolved in some paths but still present in others (read the detail).

## Active limitations

### 1. `SYSTEM$CREATE_EVALUATION_DATASET` drops VARIANT ground truth

- **Symptom.** Pre-creating an evaluation dataset with `SYSTEM$CREATE_EVALUATION_DATASET` silently loses the VARIANT `ground_truth` column. `GET_AI_EVALUATION_DATA` then returns empty ground truth, so `answer_correctness` scores 0 for every record.
- **Workaround.** Do not pre-create the dataset. Supply an inline `dataset:` block in the YAML config passed to `EXECUTE_AI_EVALUATION`; the engine then persists ground truth correctly. Use a unique dataset name per run.
- **Where handled.** [evaluation/audit_agent.py](../../evaluation/audit_agent.py) builds the eval table and inline dataset rather than calling `SYSTEM$CREATE_EVALUATION_DATASET`.
- **Status.** Active.

### 2. SSO browser auth blocks headless Python

- **Symptom.** The Snowflake Python connector with `authenticator=externalbrowser` opens a browser window. This is fine locally but fatal in CI/CD or any unattended job.
- **Workaround.** Use key-pair authentication for automation. Set `SNOWFLAKE_PRIVATE_KEY_PATH` (and `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` if encrypted), or configure a key-pair connection profile.
- **Where handled.** The `get_connection()` helpers in [setup/bootstrap.py](../../setup/bootstrap.py) and [evaluation/utils.py](../../evaluation/utils.py) accept key-pair credentials via environment variables.
- **Status.** Active. This is environmental, not a code defect.

### 3. `ALTER TASK SET SCHEDULE` requires the `USING CRON` prefix

- **Symptom.** `SHOW TASKS` returns the schedule already prefixed with `USING CRON` (for example `USING CRON 30 2 * * * UTC`), but `ALTER TASK ... SET SCHEDULE = '<value>'` requires that prefix to be present in the value you set. Comparing the two directly, or setting a bare cron string, fails.
- **Workaround.** Strip the `USING CRON` prefix when comparing the current schedule, and re-add it when issuing the `ALTER TASK SET SCHEDULE` statement.
- **Where handled.** The schedule switcher on the parked demo branch (`setup/switch_schedule.py`) applies this pattern.
- **Status.** Active. This is standard Snowflake behavior, not expected to change.

### 4. Default role must allow `CREATE WAREHOUSE` for bootstrap

- **Symptom.** Running `bootstrap.py` with a connection whose default role is, for example, `SECURITYADMIN` fails at the first step with `Insufficient privileges to operate on account ... must have CREATE WAREHOUSE granted`.
- **Workaround.** Run bootstrap with a role that can create warehouses (for example `ACCOUNTADMIN`), or set the connection's default role accordingly: `ALTER USER <user> SET DEFAULT_ROLE = ACCOUNTADMIN`.
- **Where handled.** Bootstrap creates the warehouse in `main()` before any SQL file runs, so the active role at connection time must already have the privilege.
- **Status.** Active. Document this in customer onboarding.

## Partial

### 5. `DATA_AGENT_RUN` cannot resolve a warehouse for the Cortex Analyst tool

- **Symptom (historical).** Invoking an agent via the `SNOWFLAKE.CORTEX.DATA_AGENT_RUN` SQL function could not resolve a warehouse for the `cortex_analyst_text_to_sql` tool, returning "missing an execution environment". This previously required a manual warehouse configuration step in the Snowsight UI.
- **Resolution in primary paths.** The agent specification now declares its execution environment directly:

  ```yaml
  tool_resources:
    RetailAnalyst:
      execution_environment:
        type: "warehouse"
        warehouse: "RETAIL_AI_EVAL_WH"
  ```

  (see [agents/dev/retail_agent.sql](../../agents/dev/retail_agent.sql)). The evaluation path also invokes the agent through the REST API (`/api/v2/databases/.../agents/{name}:run` in [evaluation/utils.py](../../evaluation/utils.py)), not the SQL function. The bootstrap no longer prints a manual warehouse reminder, and the agent evaluation in CI ran end to end without manual intervention.
- **Still present.** The weekly smoke-test stored procedures still call `DATA_AGENT_RUN` directly:
  - [setup/bootstrap.py](../../setup/bootstrap.py) (the `SP_WEEKLY_AGENT_EVAL` body)
  - [setup/08_monitoring_tasks.sql](../../setup/08_monitoring_tasks.sql)

  These weekly tasks have not been independently verified since the spec change and may still hit the original limitation.
- **Status.** Partial. Resolved for the eval and REST paths; unverified for the weekly `DATA_AGENT_RUN` smoke tests.
- **Tracking.** This issue remains open as the upstream-watch and weekly-path verification tracker.

## Resolved

### 6. `SNOWFLAKE.CORTEX.COMPLETE('analyst', ...)` is deprecated

- **Symptom.** Calling `SNOWFLAKE.CORTEX.COMPLETE('analyst', ...)` returns "Model analyst is unavailable".
- **Resolution.** The semantic-view evaluation path was migrated to the Cortex Agent REST API. `call_cortex_analyst` in [evaluation/utils.py](../../evaluation/utils.py) now routes through `call_cortex_agent` (REST). This was fixed in commit `d301b35`.
- **Caveat.** The deprecated call still exists in two non-eval paths: the `SP_WEEKLY_SV_EVAL` stored proc ([setup/bootstrap.py](../../setup/bootstrap.py), [setup/08_monitoring_tasks.sql](../../setup/08_monitoring_tasks.sql)) and [monitoring/health_check.py](../../monitoring/health_check.py). These would fail if executed and should be migrated in a follow-up.
- **Status.** Resolved for the eval path; a follow-up is warranted for the weekly SV smoke test and health check.

## Monitoring guidance

- Re-check the Active and Partial items against Snowflake release notes periodically. When an item is fixed upstream, move it to Resolved with the commit or release reference, and close any associated tracking issue.
- The two follow-ups surfaced during the May 2026 review — the weekly `DATA_AGENT_RUN` smoke test and the deprecated `COMPLETE('analyst')` calls in the weekly SV proc and health check — should be captured as their own issues so the monitoring paths are brought in line with the eval paths.
