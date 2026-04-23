-- ============================================================================
-- 01_create_databases.sql
-- Creates the three-environment structure: DEV, TEST, PROD
-- Each environment is a separate database with identical schemas
-- ============================================================================

USE ROLE SYSADMIN;

-- Development environment - analysts work here
CREATE DATABASE IF NOT EXISTS RETAIL_AI_DEV;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_DEV.ANALYTICS;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_DEV.SEMANTIC;

-- Test environment - CI/CD evaluations run here
CREATE DATABASE IF NOT EXISTS RETAIL_AI_TEST;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_TEST.ANALYTICS;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_TEST.SEMANTIC;

-- Production environment - promoted after passing quality gates
CREATE DATABASE IF NOT EXISTS RETAIL_AI_PROD;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_PROD.ANALYTICS;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_PROD.SEMANTIC;

-- Shared evaluation database for storing results across environments
CREATE DATABASE IF NOT EXISTS RETAIL_AI_EVAL;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_EVAL.RESULTS;
CREATE SCHEMA IF NOT EXISTS RETAIL_AI_EVAL.OBSERVABILITY;

-- Evaluation results table
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.RESULTS.SEMANTIC_VIEW_EVAL_RUNS (
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

CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.RESULTS.SEMANTIC_VIEW_EVAL_DETAILS (
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

CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.RESULTS.AGENT_EVAL_RUNS (
    eval_run_id         STRING DEFAULT UUID_STRING(),
    environment         STRING,
    agent_name          STRING,
    git_commit_sha      STRING,
    git_branch          STRING,
    total_questions     INTEGER,
    passed_questions    INTEGER,
    failed_questions    INTEGER,
    accuracy_pct        FLOAT,
    threshold_pct       FLOAT,
    passed_threshold    BOOLEAN,
    avg_context_relevance   FLOAT,
    avg_groundedness        FLOAT,
    avg_answer_relevance    FLOAT,
    run_timestamp       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    run_details         VARIANT
);

CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.RESULTS.AGENT_EVAL_DETAILS (
    eval_run_id             STRING,
    question_id             STRING,
    question_text           STRING,
    category                STRING,
    should_answer           BOOLEAN,
    did_answer              BOOLEAN,
    expected_answer         STRING,
    agent_response          STRING,
    context_relevance_score FLOAT,
    groundedness_score      FLOAT,
    answer_relevance_score  FLOAT,
    overall_score           FLOAT,
    llm_judge_reasoning     STRING,
    latency_ms              INTEGER,
    tool_calls_made         VARIANT,
    eval_timestamp          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Warehouse for evaluations
CREATE WAREHOUSE IF NOT EXISTS RETAIL_AI_EVAL_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE;
