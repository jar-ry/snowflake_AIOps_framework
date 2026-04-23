-- ============================================================================
-- 07_monitoring_tables.sql
-- Tables for long-term monitoring: feedback, usage, token costs, health checks
-- ============================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE RETAIL_AI_EVAL_WH;
USE DATABASE RETAIL_AI_EVAL;

CREATE SCHEMA IF NOT EXISTS RETAIL_AI_EVAL.MONITORING;

-- ============================================================
-- User feedback tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK (
    feedback_id         STRING DEFAULT UUID_STRING(),
    environment         STRING,
    source              STRING,            -- 'agent', 'analyst', 'snowsight'
    agent_or_sv_name    STRING,
    user_query          STRING,
    agent_response      STRING,
    feedback_rating     INTEGER,           -- 1-5 scale (1=very negative, 5=very positive)
    feedback_text       STRING,
    feedback_category   STRING,            -- 'incorrect_answer', 'slow_response', 'refused_valid', 'safety_concern', 'other'
    sentiment_score     FLOAT,             -- AI-computed sentiment (-1.0 to 1.0)
    user_name           STRING DEFAULT CURRENT_USER(),
    created_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- Scheduled evaluation run history
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS (
    run_id              STRING DEFAULT UUID_STRING(),
    run_type            STRING,            -- 'weekly_sv_eval', 'weekly_agent_eval', 'weekly_native_eval', 'weekly_sv_audit'
    environment         STRING,
    target_name         STRING,            -- semantic view or agent FQN
    accuracy_pct        FLOAT,
    threshold_pct       FLOAT,
    passed_threshold    BOOLEAN,
    total_questions     INTEGER,
    passed_questions    INTEGER,
    failed_questions    INTEGER,
    accuracy_delta      FLOAT,             -- change from previous run
    run_details         VARIANT,
    run_timestamp       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- Agent/Analyst usage and token costs
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.USAGE_METRICS (
    metric_id           STRING DEFAULT UUID_STRING(),
    metric_date         DATE,
    environment         STRING,
    service_type        STRING,            -- 'cortex_agent', 'cortex_analyst', 'llm_complete'
    agent_or_sv_name    STRING,
    total_requests      INTEGER,
    successful_requests INTEGER,
    failed_requests     INTEGER,
    total_input_tokens  BIGINT,
    total_output_tokens BIGINT,
    total_tokens        BIGINT,
    estimated_cost_usd  FLOAT,
    avg_latency_ms      FLOAT,
    p50_latency_ms      FLOAT,
    p95_latency_ms      FLOAT,
    p99_latency_ms      FLOAT,
    unique_users        INTEGER,
    collected_at        TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- Health check results
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS (
    check_id            STRING DEFAULT UUID_STRING(),
    check_name          STRING,            -- 'agent_responds', 'analyst_generates_sql', 'sv_exists', 'latency_ok', etc.
    environment         STRING,
    target_name         STRING,
    status              STRING,            -- 'HEALTHY', 'DEGRADED', 'UNHEALTHY', 'ERROR'
    details             STRING,
    latency_ms          INTEGER,
    checked_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- Alert history
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY (
    alert_id            STRING DEFAULT UUID_STRING(),
    alert_type          STRING,            -- 'negative_feedback_spike', 'accuracy_regression', 'latency_degradation', 'cost_anomaly', 'health_failure'
    severity            STRING,            -- 'CRITICAL', 'WARNING', 'INFO'
    environment         STRING,
    target_name         STRING,
    message             STRING,
    metric_value        FLOAT,
    threshold_value     FLOAT,
    acknowledged        BOOLEAN DEFAULT FALSE,
    acknowledged_by     STRING,
    acknowledged_at     TIMESTAMP_NTZ,
    created_at          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- Feedback sentiment aggregation (daily rollup)
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY (
    summary_date        DATE,
    environment         STRING,
    agent_or_sv_name    STRING,
    total_feedback      INTEGER,
    positive_count      INTEGER,           -- rating >= 4
    neutral_count       INTEGER,           -- rating = 3
    negative_count      INTEGER,           -- rating <= 2
    avg_rating          FLOAT,
    avg_sentiment_score FLOAT,
    negative_pct        FLOAT,
    feedback_categories VARIANT,           -- JSON object of category counts
    computed_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- Grants
-- ============================================================
USE ROLE SECURITYADMIN;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_ADMIN;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_ADMIN;
GRANT ALL PRIVILEGES ON FUTURE TABLES IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_ADMIN;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_DEPLOYER;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_DEPLOYER;
GRANT INSERT, SELECT ON FUTURE TABLES IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_DEPLOYER;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON ALL TABLES IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_REVIEWER;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_ANALYST;
GRANT INSERT ON TABLE RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK TO ROLE RETAIL_AI_ANALYST;
GRANT SELECT ON TABLE RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK TO ROLE RETAIL_AI_ANALYST;
