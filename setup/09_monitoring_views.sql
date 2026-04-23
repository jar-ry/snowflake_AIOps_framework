-- ============================================================================
-- 09_monitoring_views.sql
-- Views for long-term trend analysis and Snowsight dashboards:
--   - Evaluation accuracy trends
--   - Feedback sentiment trends
--   - Token cost trends
--   - Agent usage patterns
--   - Health dashboard summary
-- ============================================================================

USE ROLE SYSADMIN;
USE DATABASE RETAIL_AI_EVAL;

-- ============================================================
-- VIEW: Evaluation accuracy trend over time (CI/CD + scheduled)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_EVAL_ACCURACY_TREND AS
SELECT
    run_timestamp::DATE                         AS eval_date,
    'semantic_view'                             AS eval_type,
    environment,
    semantic_view_name                          AS target_name,
    accuracy_pct,
    threshold_pct,
    passed_threshold,
    total_questions,
    passed_questions,
    git_commit_sha,
    git_branch,
    LAG(accuracy_pct) OVER (
        PARTITION BY environment, semantic_view_name
        ORDER BY run_timestamp
    )                                           AS prev_accuracy_pct,
    accuracy_pct - COALESCE(LAG(accuracy_pct) OVER (
        PARTITION BY environment, semantic_view_name
        ORDER BY run_timestamp
    ), accuracy_pct)                            AS accuracy_delta,
    run_timestamp
FROM RETAIL_AI_EVAL.RESULTS.SEMANTIC_VIEW_EVAL_RUNS

UNION ALL

SELECT
    run_timestamp::DATE                         AS eval_date,
    'agent'                                     AS eval_type,
    environment,
    agent_name                                  AS target_name,
    accuracy_pct,
    threshold_pct,
    passed_threshold,
    total_questions,
    passed_questions,
    git_commit_sha,
    git_branch,
    LAG(accuracy_pct) OVER (
        PARTITION BY environment, agent_name
        ORDER BY run_timestamp
    )                                           AS prev_accuracy_pct,
    accuracy_pct - COALESCE(LAG(accuracy_pct) OVER (
        PARTITION BY environment, agent_name
        ORDER BY run_timestamp
    ), accuracy_pct)                            AS accuracy_delta,
    run_timestamp
FROM RETAIL_AI_EVAL.RESULTS.AGENT_EVAL_RUNS

UNION ALL

SELECT
    run_timestamp::DATE                         AS eval_date,
    run_type                                    AS eval_type,
    environment,
    target_name,
    accuracy_pct,
    threshold_pct,
    passed_threshold,
    total_questions,
    passed_questions,
    NULL                                        AS git_commit_sha,
    NULL                                        AS git_branch,
    LAG(accuracy_pct) OVER (
        PARTITION BY environment, target_name, run_type
        ORDER BY run_timestamp
    )                                           AS prev_accuracy_pct,
    accuracy_pct - COALESCE(LAG(accuracy_pct) OVER (
        PARTITION BY environment, target_name, run_type
        ORDER BY run_timestamp
    ), accuracy_pct)                            AS accuracy_delta,
    run_timestamp
FROM RETAIL_AI_EVAL.MONITORING.SCHEDULED_EVAL_RUNS;

-- ============================================================
-- VIEW: Feedback sentiment trend (daily)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_FEEDBACK_TREND AS
SELECT
    summary_date,
    environment,
    agent_or_sv_name,
    total_feedback,
    positive_count,
    neutral_count,
    negative_count,
    avg_rating,
    avg_sentiment_score,
    negative_pct,
    AVG(avg_rating) OVER (
        PARTITION BY environment, agent_or_sv_name
        ORDER BY summary_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                           AS rolling_7d_avg_rating,
    AVG(negative_pct) OVER (
        PARTITION BY environment, agent_or_sv_name
        ORDER BY summary_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                           AS rolling_7d_negative_pct,
    SUM(total_feedback) OVER (
        PARTITION BY environment, agent_or_sv_name
        ORDER BY summary_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                           AS rolling_7d_total_feedback,
    feedback_categories
FROM RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY;

-- ============================================================
-- VIEW: Token cost & usage trends (daily)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_TOKEN_COST_TREND AS
SELECT
    metric_date,
    environment,
    service_type,
    agent_or_sv_name,
    total_requests,
    successful_requests,
    failed_requests,
    total_input_tokens,
    total_output_tokens,
    total_tokens,
    estimated_cost_usd,
    avg_latency_ms,
    p95_latency_ms,
    unique_users,
    SUM(total_tokens) OVER (
        PARTITION BY environment, service_type, agent_or_sv_name
        ORDER BY metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                           AS rolling_7d_tokens,
    SUM(estimated_cost_usd) OVER (
        PARTITION BY environment, service_type, agent_or_sv_name
        ORDER BY metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                           AS rolling_7d_cost_usd,
    AVG(avg_latency_ms) OVER (
        PARTITION BY environment, service_type, agent_or_sv_name
        ORDER BY metric_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )                                           AS rolling_7d_avg_latency_ms,
    SUM(total_requests) OVER (
        PARTITION BY environment, service_type, agent_or_sv_name
        ORDER BY metric_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    )                                           AS rolling_30d_requests,
    SUM(estimated_cost_usd) OVER (
        PARTITION BY environment, service_type, agent_or_sv_name
        ORDER BY metric_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    )                                           AS rolling_30d_cost_usd,
    ROUND(
        COALESCE(failed_requests, 0) * 100.0 / NULLIF(total_requests, 0), 2
    )                                           AS error_rate_pct
FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS;

-- ============================================================
-- VIEW: Agent usage patterns (hourly distribution from raw events)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_AGENT_USAGE_PATTERNS AS
SELECT
    event_time::DATE                                                AS usage_date,
    HOUR(event_time)                                                AS usage_hour,
    DAYNAME(event_time)                                             AS day_of_week,
    COALESCE(database_name, 'UNKNOWN')                              AS environment,
    CASE
        WHEN span_name LIKE 'ReasoningAgentStep%' OR span_name LIKE 'CodingAgent%' THEN 'cortex_agent'
        WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst'
        ELSE 'other'
    END                                                             AS service_type,
    agent_name,
    model_used,
    COUNT(*)                                                        AS span_count,
    COUNT(DISTINCT trace_id)                                        AS request_count,
    SUM(COALESCE(total_tokens, 0))                                  AS total_tokens,
    AVG(planning_duration_ms)                                       AS avg_latency_ms,
    COUNT_IF(status_code != 'STATUS_CODE_OK')                       AS error_count
FROM RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES
GROUP BY 1, 2, 3, 4, 5, 6, 7;

-- ============================================================
-- VIEW: Health dashboard summary (latest status per check)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_HEALTH_DASHBOARD AS
SELECT *
FROM (
    SELECT
        check_name,
        environment,
        target_name,
        status,
        details,
        latency_ms,
        checked_at,
        ROW_NUMBER() OVER (
            PARTITION BY check_name, environment, target_name
            ORDER BY checked_at DESC
        ) AS rn
    FROM RETAIL_AI_EVAL.MONITORING.HEALTH_CHECK_RESULTS
)
WHERE rn = 1;

-- ============================================================
-- VIEW: Active alerts (unacknowledged)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_ACTIVE_ALERTS AS
SELECT
    alert_id,
    alert_type,
    severity,
    environment,
    target_name,
    message,
    metric_value,
    threshold_value,
    created_at,
    DATEDIFF('hour', created_at, CURRENT_TIMESTAMP()) AS hours_since_created
FROM RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
WHERE acknowledged = FALSE
ORDER BY
    CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END,
    created_at DESC;

-- ============================================================
-- VIEW: Weekly executive summary
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_WEEKLY_EXECUTIVE_SUMMARY AS
SELECT
    DATE_TRUNC('week', metric_date)                     AS week_start,
    environment,
    SUM(total_requests)                                 AS total_requests,
    SUM(successful_requests)                            AS successful_requests,
    ROUND(SUM(successful_requests) * 100.0 / NULLIF(SUM(total_requests), 0), 2) AS success_rate_pct,
    SUM(total_tokens)                                   AS total_tokens,
    SUM(estimated_cost_usd)                             AS total_cost_usd,
    AVG(avg_latency_ms)                                 AS avg_latency_ms,
    SUM(unique_users)                                   AS total_user_sessions
FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
GROUP BY 1, 2;

-- ============================================================
-- Grants
-- ============================================================
USE ROLE SECURITYADMIN;

GRANT SELECT ON ALL VIEWS IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON ALL VIEWS IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA RETAIL_AI_EVAL.MONITORING TO ROLE RETAIL_AI_REVIEWER;
