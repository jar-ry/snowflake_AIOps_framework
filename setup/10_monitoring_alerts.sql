-- ============================================================================
-- 10_monitoring_alerts.sql
-- Snowflake Alerts that fire when monitoring thresholds are breached:
--   1. Negative feedback spike (>25% negative in a day)
--   2. Accuracy regression (>10% drop between eval runs)
--   3. Latency degradation (P95 > 30s)
--   4. Cost anomaly (daily cost > 2x 7-day average)
--   5. Agent error spike (error rate > 10%)
--   6. Health check failure (any UNHEALTHY status)
--
-- Each alert inserts into ALERT_HISTORY and can optionally send
-- a notification via a notification integration.
-- ============================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE RETAIL_AI_EVAL_WH;
USE DATABASE RETAIL_AI_EVAL;

-- ============================================================
-- ALERT 1: Negative feedback spike
-- Fires when >25% of yesterday's feedback is negative (rating <= 2)
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_NEGATIVE_FEEDBACK_SPIKE
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 0 7 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY
        WHERE summary_date = CURRENT_DATE() - 1
          AND negative_pct > 25
          AND total_feedback >= 5
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'negative_feedback_spike',
            CASE WHEN negative_pct > 50 THEN 'CRITICAL' ELSE 'WARNING' END,
            environment,
            agent_or_sv_name,
            'Negative feedback spike: ' || ROUND(negative_pct, 1) || '% negative (' ||
                negative_count || '/' || total_feedback || ') on ' || summary_date::STRING ||
                '. Avg rating: ' || ROUND(avg_rating, 1),
            negative_pct,
            25
        FROM RETAIL_AI_EVAL.MONITORING.FEEDBACK_DAILY_SUMMARY
        WHERE summary_date = CURRENT_DATE() - 1
          AND negative_pct > 25
          AND total_feedback >= 5;

-- ============================================================
-- ALERT 2: Accuracy regression
-- Fires when any eval run shows >10% accuracy drop from previous
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_ACCURACY_REGRESSION
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 0 8 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.V_EVAL_ACCURACY_TREND
        WHERE eval_date >= CURRENT_DATE() - 1
          AND accuracy_delta < -10
          AND prev_accuracy_pct IS NOT NULL
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'accuracy_regression',
            CASE WHEN accuracy_delta < -20 THEN 'CRITICAL' ELSE 'WARNING' END,
            environment,
            target_name,
            eval_type || ' accuracy regression: ' || ROUND(accuracy_pct, 1) || '% (was ' ||
                ROUND(prev_accuracy_pct, 1) || '%, delta: ' || ROUND(accuracy_delta, 1) || '%)',
            accuracy_delta,
            -10
        FROM RETAIL_AI_EVAL.MONITORING.V_EVAL_ACCURACY_TREND
        WHERE eval_date >= CURRENT_DATE() - 1
          AND accuracy_delta < -10
          AND prev_accuracy_pct IS NOT NULL;

-- ============================================================
-- ALERT 3: Latency degradation
-- Fires when P95 latency exceeds 30 seconds
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_LATENCY_DEGRADATION
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 0 7 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
        WHERE metric_date = CURRENT_DATE() - 1
          AND p95_latency_ms > 30000
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'latency_degradation',
            CASE WHEN p95_latency_ms > 60000 THEN 'CRITICAL' ELSE 'WARNING' END,
            environment,
            agent_or_sv_name,
            service_type || ' P95 latency: ' || ROUND(p95_latency_ms / 1000, 1) ||
                's (avg: ' || ROUND(avg_latency_ms / 1000, 1) || 's) on ' || metric_date::STRING,
            p95_latency_ms,
            30000
        FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
        WHERE metric_date = CURRENT_DATE() - 1
          AND p95_latency_ms > 30000;

-- ============================================================
-- ALERT 4: Cost anomaly
-- Fires when daily cost exceeds 2x the 7-day rolling average
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_COST_ANOMALY
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 0 7 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.V_TOKEN_COST_TREND
        WHERE metric_date = CURRENT_DATE() - 1
          AND rolling_7d_cost_usd > 0
          AND estimated_cost_usd > (rolling_7d_cost_usd / 7.0) * 2
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'cost_anomaly',
            CASE
                WHEN estimated_cost_usd > (rolling_7d_cost_usd / 7.0) * 5 THEN 'CRITICAL'
                ELSE 'WARNING'
            END,
            environment,
            agent_or_sv_name,
            service_type || ' cost anomaly: $' || ROUND(estimated_cost_usd, 2) ||
                ' (7-day daily avg: $' || ROUND(rolling_7d_cost_usd / 7.0, 2) ||
                ', ' || ROUND(estimated_cost_usd / NULLIF(rolling_7d_cost_usd / 7.0, 0), 1) || 'x normal)',
            estimated_cost_usd,
            ROUND(rolling_7d_cost_usd / 7.0 * 2, 2)
        FROM RETAIL_AI_EVAL.MONITORING.V_TOKEN_COST_TREND
        WHERE metric_date = CURRENT_DATE() - 1
          AND rolling_7d_cost_usd > 0
          AND estimated_cost_usd > (rolling_7d_cost_usd / 7.0) * 2;

-- ============================================================
-- ALERT 5: Agent error spike
-- Fires when error rate exceeds 10% on any day
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_ERROR_SPIKE
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 0 7 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
        WHERE metric_date = CURRENT_DATE() - 1
          AND total_requests >= 10
          AND ROUND(failed_requests * 100.0 / NULLIF(total_requests, 0), 2) > 10
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'error_spike',
            CASE
                WHEN ROUND(failed_requests * 100.0 / NULLIF(total_requests, 0), 2) > 25 THEN 'CRITICAL'
                ELSE 'WARNING'
            END,
            environment,
            agent_or_sv_name,
            service_type || ' error rate: ' ||
                ROUND(failed_requests * 100.0 / NULLIF(total_requests, 0), 1) ||
                '% (' || failed_requests || ' failures / ' || total_requests || ' total)',
            ROUND(failed_requests * 100.0 / NULLIF(total_requests, 0), 2),
            10
        FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
        WHERE metric_date = CURRENT_DATE() - 1
          AND total_requests >= 10
          AND ROUND(failed_requests * 100.0 / NULLIF(total_requests, 0), 2) > 10;

-- ============================================================
-- ALERT 6: Health check failure
-- Fires when any health check comes back UNHEALTHY
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_HEALTH_FAILURE
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 30 6 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.V_HEALTH_DASHBOARD
        WHERE status = 'UNHEALTHY'
          AND checked_at >= DATEADD('hour', -25, CURRENT_TIMESTAMP())
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'health_failure',
            'CRITICAL',
            environment,
            target_name,
            'Health check FAILED: ' || check_name || ' - ' || details,
            0,
            0
        FROM RETAIL_AI_EVAL.MONITORING.V_HEALTH_DASHBOARD
        WHERE status = 'UNHEALTHY'
          AND checked_at >= DATEADD('hour', -25, CURRENT_TIMESTAMP());

-- ============================================================
-- Resume all alerts
-- ============================================================
ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_NEGATIVE_FEEDBACK_SPIKE RESUME;
ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_ACCURACY_REGRESSION RESUME;
ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_LATENCY_DEGRADATION RESUME;
ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_COST_ANOMALY RESUME;
ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_ERROR_SPIKE RESUME;
ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_HEALTH_FAILURE RESUME;

-- ============================================================
-- Optional: Email notification integration
-- Uncomment and configure if you want email alerts.
-- ============================================================
-- CREATE OR REPLACE NOTIFICATION INTEGRATION RETAIL_AI_EMAIL_ALERTS
--     TYPE = EMAIL
--     ENABLED = TRUE
--     ALLOWED_RECIPIENTS = ('your-team@company.com');
--
-- To wire an alert to email, modify the THEN clause:
-- ALTER ALERT ... MODIFY CONDITION ... THEN
--   CALL SYSTEM$SEND_EMAIL(
--     'RETAIL_AI_EMAIL_ALERTS',
--     'your-team@company.com',
--     'RETAIL AI Alert: <type>',
--     '<message body>'
--   );
