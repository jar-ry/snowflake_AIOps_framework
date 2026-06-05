-- ============================================================================
-- 01_create_databases.sql
-- Creates the two-tier environment structure: DEV + PROD
-- DEV: development + CI evaluation | PROD: promoted on merge
-- ============================================================================

USE ROLE SYSADMIN;

-- Development environment - analysts work here, CI evaluations run here
CREATE DATABASE IF NOT EXISTS {{DB_DEV}};
CREATE SCHEMA IF NOT EXISTS {{DB_DEV}}.ANALYTICS;
CREATE SCHEMA IF NOT EXISTS {{DB_DEV}}.SEMANTIC;

-- Production environment - promoted after passing quality gates
CREATE DATABASE IF NOT EXISTS {{DB_PROD}};
CREATE SCHEMA IF NOT EXISTS {{DB_PROD}}.ANALYTICS;
CREATE SCHEMA IF NOT EXISTS {{DB_PROD}}.SEMANTIC;

-- Shared evaluation database for storing results across environments
CREATE DATABASE IF NOT EXISTS {{DB_EVAL}};
CREATE SCHEMA IF NOT EXISTS {{DB_EVAL}}.RESULTS;
CREATE SCHEMA IF NOT EXISTS {{DB_EVAL}}.OBSERVABILITY;

-- Evaluation results table
CREATE TABLE IF NOT EXISTS {{DB_EVAL}}.RESULTS.SEMANTIC_VIEW_EVAL_RUNS (
    eval_run_id         STRING DEFAULT UUID_STRING(),
    environment         STRING,
    semantic_view_name  STRING,
    git_commit_sha      STRING,
    git_branch          STRING,
    total_questions     INTEGER,
    passed_questions    INTEGER,
    failed_questions    INTEGER,
    accuracy_pct        FLOAT,
    threshold_pct       FLOAT,
    passed_threshold    BOOLEAN,
    run_timestamp       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    run_details         VARIANT
);

CREATE TABLE IF NOT EXISTS {{DB_EVAL}}.RESULTS.SEMANTIC_VIEW_EVAL_DETAILS (
    eval_run_id         STRING,
    question_id         STRING,
    question_text       STRING,
    difficulty          STRING,
    expected_sql        STRING,
    generated_sql       STRING,
    expected_result     VARIANT,
    generated_result    VARIANT,
    match_status        STRING,
    llm_judge_score     FLOAT,
    llm_judge_reasoning STRING,
    latency_ms          INTEGER,
    eval_timestamp      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Agent evaluation results are stored by Snowflake's native EXECUTE_AI_EVALUATION
-- and accessed via GET_AI_EVALUATION_DATA(). No custom tables needed.

-- Warehouse for evaluations
CREATE WAREHOUSE IF NOT EXISTS {{WAREHOUSE}}
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;
