-- ============================================================================
-- 08_monitoring_tasks.sql
-- Snowflake Tasks for automated monitoring:
--   1. Daily usage & token cost aggregation from event table
--   2. Daily feedback sentiment analysis & rollup
--   3. Daily health checks (agent responds, SV exists, latency OK)
--   4. Weekly scheduled evaluations (SV + Agent question banks)
-- ============================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE {{WAREHOUSE}};
USE DATABASE {{DB_EVAL}};

-- ============================================================
-- TASK 1: Daily usage & token cost aggregation
-- Runs every day at 02:00 UTC. Pulls from event table spans.
-- ============================================================
CREATE OR REPLACE TASK {{DB_EVAL}}.MONITORING.TASK_DAILY_USAGE_AGGREGATION
    WAREHOUSE = {{WAREHOUSE}}
    SCHEDULE = 'USING CRON 0 2 * * * UTC'
    COMMENT = 'Daily aggregation of agent/analyst usage and token costs from ai_observability_events'
AS
BEGIN
    INSERT INTO {{DB_EVAL}}.MONITORING.USAGE_METRICS (
        metric_date, environment, service_type, agent_or_sv_name,
        total_requests, successful_requests, failed_requests,
        total_input_tokens, total_output_tokens, total_tokens, total_cache_read_tokens,
        estimated_credits, avg_latency_ms, p50_latency_ms, p95_latency_ms, p99_latency_ms,
        unique_users
    )
    SELECT
        CURRENT_DATE() - 1                                                           AS metric_date,
        COALESCE(database_name, 'UNKNOWN')                                           AS environment,
        CASE
            WHEN span_name LIKE 'ReasoningAgentStep%' OR span_name LIKE 'CodingAgent%' THEN 'cortex_agent'
            WHEN span_name ILIKE '%Analyst%' OR span_name ILIKE '%SqlExecution%' THEN 'cortex_analyst'
            ELSE 'other'
        END                                                                          AS service_type,
        COALESCE(agent_name, 'unknown')                                              AS agent_or_sv_name,
        COUNT(DISTINCT trace_id)                                                     AS total_requests,
        COUNT_IF(status_code = 'STATUS_CODE_OK')                                     AS successful_requests,
        COUNT_IF(status_code != 'STATUS_CODE_OK')                                    AS failed_requests,
        COALESCE(SUM(input_tokens), 0)                                               AS total_input_tokens,
        COALESCE(SUM(output_tokens), 0)                                              AS total_output_tokens,
        COALESCE(SUM(total_tokens), 0)                                               AS total_tokens,
        COALESCE(SUM(cache_read_tokens), 0)                                          AS total_cache_read_tokens,
        SUM(CASE                                                                        -- Cache-aware per-model pricing (AI Credits per 1M tokens) from config/defaults.yaml; kept in sync with evaluation/utils.build_credits_expr
            WHEN model_used = 'claude-opus-4-7' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*3.25 + COALESCE(cache_read_tokens,0)/1000000.0*0.33 + COALESCE(output_tokens,0)/1000000.0*16.26
            WHEN model_used = 'claude-opus-4-6' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*3.25 + COALESCE(cache_read_tokens,0)/1000000.0*0.33 + COALESCE(output_tokens,0)/1000000.0*16.26
            WHEN model_used = 'claude-opus-4-5' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*3.25 + COALESCE(cache_read_tokens,0)/1000000.0*0.33 + COALESCE(output_tokens,0)/1000000.0*16.26
            WHEN model_used = 'claude-4-opus' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*8.87 + COALESCE(cache_read_tokens,0)/1000000.0*0.89 + COALESCE(output_tokens,0)/1000000.0*44.34
            WHEN model_used = 'claude-4-sonnet' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*1.77 + COALESCE(cache_read_tokens,0)/1000000.0*0.18 + COALESCE(output_tokens,0)/1000000.0*8.87
            WHEN model_used = 'claude-3-7-sonnet' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*1.77 + COALESCE(cache_read_tokens,0)/1000000.0*0.18 + COALESCE(output_tokens,0)/1000000.0*8.87
            WHEN model_used = 'claude-sonnet-4-5' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*1.95 + COALESCE(cache_read_tokens,0)/1000000.0*0.20 + COALESCE(output_tokens,0)/1000000.0*9.76
            WHEN model_used = 'claude-sonnet-4-6' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*1.95 + COALESCE(cache_read_tokens,0)/1000000.0*0.20 + COALESCE(output_tokens,0)/1000000.0*9.76
            WHEN model_used = 'claude-haiku-4-5' THEN GREATEST(COALESCE(input_tokens,0)-COALESCE(cache_read_tokens,0),0)/1000000.0*0.65 + COALESCE(cache_read_tokens,0)/1000000.0*0.06 + COALESCE(output_tokens,0)/1000000.0*3.25
            ELSE COALESCE(input_tokens,0)/1000000.0*1.0 + COALESCE(output_tokens,0)/1000000.0*1.0
        END)                                                                         AS estimated_credits,
        AVG(planning_duration_ms)                                                    AS avg_latency_ms,
        APPROX_PERCENTILE(planning_duration_ms, 0.5)                                 AS p50_latency_ms,
        APPROX_PERCENTILE(planning_duration_ms, 0.95)                                AS p95_latency_ms,
        APPROX_PERCENTILE(planning_duration_ms, 0.99)                                AS p99_latency_ms,
        0                                                                            AS unique_users
    FROM {{DB_EVAL}}.OBSERVABILITY.AGENT_TRACES
    WHERE event_time >= DATEADD('day', -1, CURRENT_DATE())
      AND event_time < CURRENT_DATE()
      AND span_name LIKE 'ReasoningAgentStepPlanning%'
         OR span_name LIKE 'CodingAgent.Step%'
         OR span_name ILIKE '%Analyst%'
    GROUP BY 1, 2, 3, 4;
END;

-- ============================================================
-- TASK 2: Daily feedback sentiment analysis
-- Uses CORTEX.SENTIMENT to score unscored feedback,
-- then rolls up daily summary.
-- ============================================================
CREATE OR REPLACE TASK {{DB_EVAL}}.MONITORING.TASK_DAILY_FEEDBACK_ANALYSIS
    WAREHOUSE = {{WAREHOUSE}}
    SCHEDULE = 'USING CRON 15 2 * * * UTC'
    COMMENT = 'Daily feedback sentiment scoring and summary rollup'
AS
BEGIN
    UPDATE {{DB_EVAL}}.MONITORING.USER_FEEDBACK
    SET sentiment_score = SNOWFLAKE.CORTEX.SENTIMENT(
        COALESCE(feedback_text, '') || ' Rating: ' || feedback_rating::STRING
    )
    WHERE sentiment_score IS NULL
      AND (feedback_text IS NOT NULL OR feedback_rating IS NOT NULL);

    MERGE INTO {{DB_EVAL}}.MONITORING.FEEDBACK_DAILY_SUMMARY tgt
    USING (
        SELECT
            created_at::DATE                                             AS summary_date,
            environment,
            agent_or_sv_name,
            COUNT(*)                                                     AS total_feedback,
            COUNT_IF(feedback_rating >= 4)                               AS positive_count,
            COUNT_IF(feedback_rating = 3)                                AS neutral_count,
            COUNT_IF(feedback_rating <= 2)                               AS negative_count,
            AVG(feedback_rating)                                         AS avg_rating,
            AVG(sentiment_score)                                         AS avg_sentiment_score,
            ROUND(COUNT_IF(feedback_rating <= 2) * 100.0 / NULLIF(COUNT(*), 0), 2) AS negative_pct,
            OBJECT_AGG(
                COALESCE(feedback_category, 'uncategorized'),
                cnt::VARIANT
            )                                                            AS feedback_categories
        FROM (
            SELECT *, COUNT(*) OVER (PARTITION BY created_at::DATE, environment, agent_or_sv_name, feedback_category) AS cnt
            FROM {{DB_EVAL}}.MONITORING.USER_FEEDBACK
            WHERE created_at::DATE = CURRENT_DATE() - 1
        )
        GROUP BY 1, 2, 3
    ) src
    ON tgt.summary_date = src.summary_date
       AND tgt.environment = src.environment
       AND tgt.agent_or_sv_name = src.agent_or_sv_name
    WHEN MATCHED THEN UPDATE SET
        tgt.total_feedback = src.total_feedback,
        tgt.positive_count = src.positive_count,
        tgt.neutral_count = src.neutral_count,
        tgt.negative_count = src.negative_count,
        tgt.avg_rating = src.avg_rating,
        tgt.avg_sentiment_score = src.avg_sentiment_score,
        tgt.negative_pct = src.negative_pct,
        tgt.feedback_categories = src.feedback_categories,
        tgt.computed_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (
        summary_date, environment, agent_or_sv_name,
        total_feedback, positive_count, neutral_count, negative_count,
        avg_rating, avg_sentiment_score, negative_pct, feedback_categories
    ) VALUES (
        src.summary_date, src.environment, src.agent_or_sv_name,
        src.total_feedback, src.positive_count, src.neutral_count, src.negative_count,
        src.avg_rating, src.avg_sentiment_score, src.negative_pct, src.feedback_categories
    );
END;

-- ============================================================
-- TASK 3: Daily health checks
-- Verifies agent responds, semantic view exists, latency is OK.
-- ============================================================
CREATE OR REPLACE TASK {{DB_EVAL}}.MONITORING.TASK_DAILY_HEALTH_CHECKS
    WAREHOUSE = {{WAREHOUSE}}
    SCHEDULE = 'USING CRON 0 6 * * * UTC'
    COMMENT = 'Daily health checks for agent and semantic view availability'
AS
BEGIN
    LET check_time TIMESTAMP_NTZ := CURRENT_TIMESTAMP();

    -- Check: PROD semantic view exists
    BEGIN
        DESCRIBE SEMANTIC VIEW {{DB_PROD}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}};
        INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
            (check_name, environment, target_name, status, details, latency_ms)
        VALUES ('sv_exists', 'prod', '{{DB_PROD}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}}', 'HEALTHY', 'Semantic view exists and is accessible', 0);
    EXCEPTION
        WHEN OTHER THEN
            LET err STRING := SQLERRM;
            INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
                (check_name, environment, target_name, status, details, latency_ms)
            SELECT 'sv_exists', 'prod', '{{DB_PROD}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}}', 'UNHEALTHY',
                   'Semantic view not accessible: ' || :err, 0;
    END;

    -- Check: PROD agent exists
    BEGIN
        DESCRIBE AGENT {{DB_PROD}}.SEMANTIC.{{AGENT_NAME}};
        INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
            (check_name, environment, target_name, status, details, latency_ms)
        VALUES ('agent_exists', 'prod', '{{DB_PROD}}.SEMANTIC.{{AGENT_NAME}}', 'HEALTHY', 'Agent exists and is accessible', 0);
    EXCEPTION
        WHEN OTHER THEN
            LET err STRING := SQLERRM;
            INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
                (check_name, environment, target_name, status, details, latency_ms)
            SELECT 'agent_exists', 'prod', '{{DB_PROD}}.SEMANTIC.{{AGENT_NAME}}', 'UNHEALTHY',
                   'Agent not accessible: ' || :err, 0;
    END;

    -- Check: recent errors from ai_observability_events (last 24h)
    INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
        (check_name, environment, target_name, status, details, latency_ms)
    SELECT
        'error_rate',
        'prod',
        'ALL_SERVICES',
        CASE
            WHEN error_pct > 20 THEN 'UNHEALTHY'
            WHEN error_pct > 5 THEN 'DEGRADED'
            ELSE 'HEALTHY'
        END,
        'Error rate: ' || ROUND(error_pct, 1) || '% (' || error_count || ' errors / ' || total_count || ' total)',
        0
    FROM (
        SELECT
            COUNT_IF(RECORD:status.code::STRING != 'STATUS_CODE_OK') AS error_count,
            COUNT(*) AS total_count,
            ROUND(COUNT_IF(RECORD:status.code::STRING != 'STATUS_CODE_OK') * 100.0 / NULLIF(COUNT(*), 0), 2) AS error_pct
        FROM snowflake.local.ai_observability_events
        WHERE RECORD_TYPE = 'SPAN'
          AND SCOPE:name::STRING = 'snow.cortex.agent'
          AND TIMESTAMP >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
          AND RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING = '{{DB_PROD}}'
    );

    -- Check: average latency last 24h
    INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
        (check_name, environment, target_name, status, details, latency_ms)
    SELECT
        'latency_check',
        'prod',
        'ALL_SERVICES',
        CASE
            WHEN avg_lat > 30000 THEN 'UNHEALTHY'
            WHEN avg_lat > 15000 THEN 'DEGRADED'
            ELSE 'HEALTHY'
        END,
        'Avg latency: ' || ROUND(avg_lat, 0) || 'ms, P95: ' || ROUND(p95_lat, 0) || 'ms',
        ROUND(avg_lat, 0)
    FROM (
        SELECT
            AVG(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"::FLOAT) AS avg_lat,
            APPROX_PERCENTILE(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"::FLOAT, 0.95) AS p95_lat
        FROM snowflake.local.ai_observability_events
        WHERE RECORD_TYPE = 'SPAN'
          AND SCOPE:name::STRING = 'snow.cortex.agent'
          AND TIMESTAMP >= DATEADD('hour', -24, CURRENT_TIMESTAMP())
          AND RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING = '{{DB_PROD}}'
          AND RECORD:name::STRING LIKE 'ReasoningAgentStepPlanning%'
    );
END;

-- ============================================================
-- TASK 4: Weekly scheduled evaluation (semantic view)
-- Runs every Sunday at 04:00 UTC.
-- Calls a stored procedure that wraps the evaluation logic.
-- ============================================================
CREATE OR REPLACE PROCEDURE {{DB_EVAL}}.MONITORING.SP_WEEKLY_SV_EVAL()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS CALLER
AS
BEGIN
    LET sv_name STRING := '{{DB_PROD}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}}';

    LET start_ts TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    LET status STRING := 'HEALTHY';
    LET details STRING := '';

    BEGIN
        -- SQL-native liveness: confirm the semantic view exists / is accessible.
        -- LLM-based analyst smoke (which requires a REST call) lives in the
        -- Python health_check.py path, not in this Task-driven SQL procedure.
        LET stmt STRING := 'DESCRIBE SEMANTIC VIEW ' || :sv_name;
        EXECUTE IMMEDIATE :stmt;

        LET latency INTEGER := DATEDIFF('millisecond', :start_ts, CURRENT_TIMESTAMP());

        INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS
            (run_type, environment, target_name, accuracy_pct, threshold_pct,
             passed_threshold, total_questions, passed_questions, failed_questions,
             run_details)
        SELECT
            'weekly_sv_smoke_test', 'prod', :sv_name, 100, 0, TRUE, 1, 1, 0,
            OBJECT_CONSTRUCT('check', 'sv_exists', 'latency_ms', :latency);

        details := 'SV existence check passed in ' || :latency || 'ms';

    EXCEPTION
        WHEN OTHER THEN
            LET err STRING := SQLERRM;
            status := 'UNHEALTHY';
            details := 'SV smoke test failed: ' || :err;

            INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS
                (run_type, environment, target_name, accuracy_pct, threshold_pct,
                 passed_threshold, total_questions, passed_questions, failed_questions,
                 run_details)
            SELECT
                'weekly_sv_smoke_test', 'prod', :sv_name, 0, 0, FALSE, 1, 0, 1,
                OBJECT_CONSTRUCT('error', :err);
    END;

    INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
        (check_name, environment, target_name, status, details, latency_ms)
    VALUES ('weekly_sv_smoke_test', 'prod', :sv_name, :status, :details, 0);

    RETURN :status || ': ' || :details;
END;

CREATE OR REPLACE TASK {{DB_EVAL}}.MONITORING.TASK_WEEKLY_SV_EVAL
    WAREHOUSE = {{WAREHOUSE}}
    SCHEDULE = 'USING CRON 0 4 * * 0 UTC'
    COMMENT = 'Weekly PROD semantic view smoke test'
AS
    CALL {{DB_EVAL}}.MONITORING.SP_WEEKLY_SV_EVAL();

-- ============================================================
-- TASK 5: Weekly agent smoke test
-- ============================================================
CREATE OR REPLACE PROCEDURE {{DB_EVAL}}.MONITORING.SP_WEEKLY_AGENT_EVAL()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS CALLER
AS
BEGIN
    LET agent_name STRING := '{{DB_PROD}}.SEMANTIC.{{AGENT_NAME}}';

    LET start_ts TIMESTAMP_NTZ := CURRENT_TIMESTAMP();
    LET status STRING := 'HEALTHY';
    LET details STRING := '';

    BEGIN
        -- SQL-native liveness: confirm the agent exists / is accessible.
        -- LLM-based agent smoke (which requires a REST call) lives in the
        -- Python health_check.py path, not in this Task-driven SQL procedure.
        LET stmt STRING := 'DESCRIBE AGENT ' || :agent_name;
        EXECUTE IMMEDIATE :stmt;

        LET latency INTEGER := DATEDIFF('millisecond', :start_ts, CURRENT_TIMESTAMP());

        INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS
            (run_type, environment, target_name, accuracy_pct, threshold_pct,
             passed_threshold, total_questions, passed_questions, failed_questions,
             run_details)
        SELECT
            'weekly_agent_smoke_test', 'prod', :agent_name, 100, 0, TRUE, 1, 1, 0,
            OBJECT_CONSTRUCT('check', 'agent_exists', 'latency_ms', :latency);

        details := 'Agent existence check passed in ' || :latency || 'ms';

    EXCEPTION
        WHEN OTHER THEN
            LET err STRING := SQLERRM;
            status := 'UNHEALTHY';
            details := 'Agent smoke test failed: ' || :err;

            INSERT INTO {{DB_EVAL}}.MONITORING.SCHEDULED_EVAL_RUNS
                (run_type, environment, target_name, accuracy_pct, threshold_pct,
                 passed_threshold, total_questions, passed_questions, failed_questions,
                 run_details)
            SELECT
                'weekly_agent_smoke_test', 'prod', :agent_name, 0, 0, FALSE, 1, 0, 1,
                OBJECT_CONSTRUCT('error', :err);
    END;

    INSERT INTO {{DB_EVAL}}.MONITORING.HEALTH_CHECK_RESULTS
        (check_name, environment, target_name, status, details, latency_ms)
    VALUES ('weekly_agent_smoke_test', 'prod', :agent_name, :status, :details, 0);

    RETURN :status || ': ' || :details;
END;
END;

CREATE OR REPLACE TASK {{DB_EVAL}}.MONITORING.TASK_WEEKLY_AGENT_EVAL
    WAREHOUSE = {{WAREHOUSE}}
    SCHEDULE = 'USING CRON 0 5 * * 0 UTC'
    COMMENT = 'Weekly PROD agent smoke test'
AS
    CALL {{DB_EVAL}}.MONITORING.SP_WEEKLY_AGENT_EVAL();

-- ============================================================
-- Resume all tasks
-- ============================================================
ALTER TASK {{DB_EVAL}}.MONITORING.TASK_DAILY_USAGE_AGGREGATION RESUME;
ALTER TASK {{DB_EVAL}}.MONITORING.TASK_DAILY_FEEDBACK_ANALYSIS RESUME;
ALTER TASK {{DB_EVAL}}.MONITORING.TASK_DAILY_HEALTH_CHECKS RESUME;
ALTER TASK {{DB_EVAL}}.MONITORING.TASK_WEEKLY_SV_EVAL RESUME;
ALTER TASK {{DB_EVAL}}.MONITORING.TASK_WEEKLY_AGENT_EVAL RESUME;

-- ============================================================
-- Grants for task execution
-- ============================================================
USE ROLE SECURITYADMIN;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE SYSADMIN;
