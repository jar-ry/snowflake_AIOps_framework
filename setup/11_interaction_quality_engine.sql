-- ============================================================================
-- 11_interaction_quality_engine.sql
-- Rules-based interaction quality engine built on ai_observability_events.
--
-- Detects problematic agent interactions WITHOUT LLM-as-a-judge:
--   1. Tool call looping       (same tool called 3+ times in one request)
--   2. Excessive planning steps (4+ steps to resolve a query)
--   3. Slow requests           (total duration > 60s)
--   4. High token burn         (>100k tokens in a single request)
--   5. Planning errors         (any step with planning_status = 'ERROR')
--   6. Abandoned conversations (thread with 3+ turns, no follow-up in 30min)
--   7. Single-turn drop-off    (thread with exactly 1 turn — possible bad answer)
--   8. Repeated rephrasing     (user sends 3+ messages in a thread quickly,
--                               suggesting they're struggling to get a good answer)
--
-- Architecture:
--   VIEW  V_REQUEST_QUALITY_SIGNALS   — per-request quality metrics
--   VIEW  V_THREAD_QUALITY_SIGNALS    — per-thread (conversation) quality metrics
--   VIEW  V_INTERACTION_QUALITY_FLAGS — union of all flagged interactions
--   TABLE INTERACTION_QUALITY_DAILY   — daily rollup of flags
--   TASK  TASK_DAILY_INTERACTION_QUALITY — scans yesterday's interactions
--   ALERT ALERT_INTERACTION_QUALITY   — fires if too many flags in a day
--   VIEW  V_INTERACTION_QUALITY_DASHBOARD — for Snowsight dashboards
-- ============================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE RETAIL_AI_EVAL_WH;
USE DATABASE RETAIL_AI_EVAL;

-- ============================================================
-- VIEW: Per-request quality signals
-- One row per trace_id with computed quality metrics
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_REQUEST_QUALITY_SIGNALS AS
WITH request_spans AS (
    SELECT
        TRACE:trace_id::STRING                                                              AS trace_id,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id"::STRING                   AS thread_id,
        RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING                     AS database_name,
        RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"::STRING                       AS schema_name,
        RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING                       AS agent_name,
        RECORD:name::STRING                                                                 AS span_name,
        RECORD:status.code::STRING                                                          AS status_code,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.status"::STRING             AS planning_status,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.step_number"::INTEGER       AS step_number,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::INTEGER AS step_tokens,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"::FLOAT            AS step_duration_ms,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.name"::STRING AS tool_selected,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.query"::STRING              AS user_query,
        START_TIMESTAMP,
        TIMESTAMP AS end_timestamp
    FROM snowflake.local.ai_observability_events
    WHERE RECORD_TYPE = 'SPAN'
      AND SCOPE:name::STRING = 'snow.cortex.agent'
      AND RECORD:name::STRING LIKE 'ReasoningAgentStepPlanning%'
),
tool_counts AS (
    SELECT
        trace_id,
        tool_selected,
        COUNT(*) AS call_count
    FROM request_spans
    WHERE tool_selected IS NOT NULL
    GROUP BY 1, 2
)
SELECT
    r.trace_id,
    MAX(r.thread_id)                                                    AS thread_id,
    MAX(r.database_name)                                                AS database_name,
    MAX(r.schema_name)                                                  AS schema_name,
    MAX(r.agent_name)                                                   AS agent_name,
    MAX(r.user_query)                                                   AS user_query,
    MIN(r.START_TIMESTAMP)                                              AS request_start,
    MAX(r.end_timestamp)                                                AS request_end,
    DATEDIFF('millisecond', MIN(r.START_TIMESTAMP), MAX(r.end_timestamp)) AS total_duration_ms,

    MAX(r.step_number)                                                  AS max_step,
    SUM(COALESCE(r.step_tokens, 0))                                     AS total_tokens,
    COUNT_IF(r.planning_status = 'ERROR')                               AS error_step_count,
    MAX(COALESCE(tc.max_same_tool_calls, 0))                            AS max_same_tool_calls,

    -- FLAGS
    IFF(MAX(COALESCE(tc.max_same_tool_calls, 0)) >= 3, TRUE, FALSE)     AS flag_tool_looping,
    IFF(MAX(r.step_number) >= 4, TRUE, FALSE)                           AS flag_excessive_steps,
    IFF(DATEDIFF('millisecond', MIN(r.START_TIMESTAMP), MAX(r.end_timestamp)) > 60000, TRUE, FALSE) AS flag_slow_request,
    IFF(SUM(COALESCE(r.step_tokens, 0)) > 100000, TRUE, FALSE)         AS flag_high_token_burn,
    IFF(COUNT_IF(r.planning_status = 'ERROR') > 0, TRUE, FALSE)        AS flag_planning_error,

    (IFF(MAX(COALESCE(tc.max_same_tool_calls, 0)) >= 3, 1, 0)
     + IFF(MAX(r.step_number) >= 4, 1, 0)
     + IFF(DATEDIFF('millisecond', MIN(r.START_TIMESTAMP), MAX(r.end_timestamp)) > 60000, 1, 0)
     + IFF(SUM(COALESCE(r.step_tokens, 0)) > 100000, 1, 0)
     + IFF(COUNT_IF(r.planning_status = 'ERROR') > 0, 1, 0))           AS flag_count

FROM request_spans r
LEFT JOIN (
    SELECT trace_id, MAX(call_count) AS max_same_tool_calls
    FROM tool_counts
    GROUP BY 1
) tc ON r.trace_id = tc.trace_id
GROUP BY r.trace_id;

-- ============================================================
-- VIEW: Per-thread (conversation) quality signals
-- Detects abandonment, struggling users, single-turn drop-offs
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_THREAD_QUALITY_SIGNALS AS
WITH thread_turns AS (
    SELECT
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id"::STRING   AS thread_id,
        TRACE:trace_id::STRING                                               AS trace_id,
        RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING        AS agent_name,
        RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING      AS database_name,
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.query"::STRING AS user_query,
        MIN(START_TIMESTAMP)                                                 AS turn_start,
        MAX(TIMESTAMP)                                                       AS turn_end
    FROM snowflake.local.ai_observability_events
    WHERE RECORD_TYPE = 'SPAN'
      AND SCOPE:name::STRING = 'snow.cortex.agent'
      AND RECORD:name::STRING = 'ReasoningAgentStepPlanning-0'
      AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id" IS NOT NULL
    GROUP BY 1, 2, 3, 4, 5
),
thread_summary AS (
    SELECT
        thread_id,
        MAX(agent_name)                                             AS agent_name,
        MAX(database_name)                                          AS database_name,
        COUNT(DISTINCT trace_id)                                    AS turn_count,
        MIN(turn_start)                                             AS first_turn,
        MAX(turn_end)                                               AS last_turn,
        DATEDIFF('minute', MIN(turn_start), MAX(turn_end))          AS conversation_duration_min,
        DATEDIFF('minute',
            MAX(turn_end),
            LEAD(MIN(turn_start)) OVER (PARTITION BY thread_id ORDER BY MIN(turn_start))
        )                                                           AS gap_to_next_turn_min,
        AVG(DATEDIFF('second', turn_start, turn_end))               AS avg_turn_duration_sec
    FROM thread_turns
    GROUP BY thread_id
)
SELECT
    thread_id,
    agent_name,
    database_name,
    turn_count,
    first_turn,
    last_turn,
    conversation_duration_min,
    avg_turn_duration_sec,

    -- FLAGS
    IFF(turn_count = 1, TRUE, FALSE)                                            AS flag_single_turn_dropoff,
    IFF(turn_count >= 3 AND conversation_duration_min <= 5, TRUE, FALSE)        AS flag_rapid_rephrasing,
    IFF(turn_count >= 3
        AND DATEDIFF('minute', last_turn, CURRENT_TIMESTAMP()) > 30
        AND conversation_duration_min < 60, TRUE, FALSE)                        AS flag_abandoned_conversation,

    (IFF(turn_count = 1, 1, 0)
     + IFF(turn_count >= 3 AND conversation_duration_min <= 5, 1, 0)
     + IFF(turn_count >= 3
           AND DATEDIFF('minute', last_turn, CURRENT_TIMESTAMP()) > 30
           AND conversation_duration_min < 60, 1, 0))                          AS flag_count

FROM thread_summary;

-- ============================================================
-- VIEW: All flagged interactions (union of request + thread flags)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_FLAGS AS

SELECT
    'request' AS signal_source,
    trace_id AS interaction_id,
    thread_id,
    database_name AS environment,
    agent_name,
    user_query,
    request_start AS event_time,
    total_duration_ms,
    total_tokens,
    max_step AS steps,
    max_same_tool_calls,
    flag_count,
    ARRAY_CONSTRUCT_COMPACT(
        IFF(flag_tool_looping, 'TOOL_LOOPING', NULL),
        IFF(flag_excessive_steps, 'EXCESSIVE_STEPS', NULL),
        IFF(flag_slow_request, 'SLOW_REQUEST', NULL),
        IFF(flag_high_token_burn, 'HIGH_TOKEN_BURN', NULL),
        IFF(flag_planning_error, 'PLANNING_ERROR', NULL)
    ) AS flags,
    CASE
        WHEN flag_planning_error THEN 'CRITICAL'
        WHEN flag_tool_looping AND flag_high_token_burn THEN 'CRITICAL'
        WHEN flag_tool_looping OR flag_excessive_steps THEN 'WARNING'
        WHEN flag_slow_request OR flag_high_token_burn THEN 'WARNING'
        ELSE 'INFO'
    END AS severity
FROM RETAIL_AI_EVAL.MONITORING.V_REQUEST_QUALITY_SIGNALS
WHERE flag_count > 0

UNION ALL

SELECT
    'thread' AS signal_source,
    thread_id AS interaction_id,
    thread_id,
    database_name AS environment,
    agent_name,
    NULL AS user_query,
    first_turn AS event_time,
    conversation_duration_min * 60000 AS total_duration_ms,
    NULL AS total_tokens,
    turn_count AS steps,
    NULL AS max_same_tool_calls,
    flag_count,
    ARRAY_CONSTRUCT_COMPACT(
        IFF(flag_single_turn_dropoff, 'SINGLE_TURN_DROPOFF', NULL),
        IFF(flag_rapid_rephrasing, 'RAPID_REPHRASING', NULL),
        IFF(flag_abandoned_conversation, 'ABANDONED_CONVERSATION', NULL)
    ) AS flags,
    CASE
        WHEN flag_abandoned_conversation AND flag_rapid_rephrasing THEN 'CRITICAL'
        WHEN flag_rapid_rephrasing THEN 'WARNING'
        WHEN flag_abandoned_conversation THEN 'WARNING'
        ELSE 'INFO'
    END AS severity
FROM RETAIL_AI_EVAL.MONITORING.V_THREAD_QUALITY_SIGNALS
WHERE flag_count > 0;

-- ============================================================
-- TABLE: Daily interaction quality summary
-- ============================================================
CREATE TABLE IF NOT EXISTS RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY (
    summary_date            DATE,
    environment             STRING,
    agent_name              STRING,
    total_requests          INTEGER,
    total_threads           INTEGER,
    flagged_requests        INTEGER,
    flagged_threads         INTEGER,
    tool_looping_count      INTEGER,
    excessive_steps_count   INTEGER,
    slow_request_count      INTEGER,
    high_token_burn_count   INTEGER,
    planning_error_count    INTEGER,
    single_turn_dropoff_count INTEGER,
    rapid_rephrasing_count  INTEGER,
    abandoned_count         INTEGER,
    critical_count          INTEGER,
    warning_count           INTEGER,
    flagged_request_pct     FLOAT,
    computed_at             TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================
-- TASK: Daily interaction quality scan
-- ============================================================
CREATE OR REPLACE TASK RETAIL_AI_EVAL.MONITORING.TASK_DAILY_INTERACTION_QUALITY
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 30 2 * * * UTC'
    COMMENT = 'Daily scan of agent interactions for quality issues using rules engine'
AS
BEGIN
    -- Insert request-level summary
    MERGE INTO RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY tgt
    USING (
        WITH yesterday_requests AS (
            SELECT *
            FROM RETAIL_AI_EVAL.MONITORING.V_REQUEST_QUALITY_SIGNALS
            WHERE request_start >= DATEADD('day', -1, CURRENT_DATE())
              AND request_start < CURRENT_DATE()
        ),
        yesterday_threads AS (
            SELECT *
            FROM RETAIL_AI_EVAL.MONITORING.V_THREAD_QUALITY_SIGNALS
            WHERE last_turn >= DATEADD('day', -1, CURRENT_DATE())
              AND last_turn < CURRENT_DATE()
        )
        SELECT
            CURRENT_DATE() - 1                                          AS summary_date,
            COALESCE(r.database_name, t.database_name)                  AS environment,
            COALESCE(r.agent_name, t.agent_name)                        AS agent_name,
            COALESCE(r.total_req, 0)                                    AS total_requests,
            COALESCE(t.total_thr, 0)                                    AS total_threads,
            COALESCE(r.flagged_req, 0)                                  AS flagged_requests,
            COALESCE(t.flagged_thr, 0)                                  AS flagged_threads,
            COALESCE(r.tool_looping, 0)                                 AS tool_looping_count,
            COALESCE(r.excessive_steps, 0)                              AS excessive_steps_count,
            COALESCE(r.slow_requests, 0)                                AS slow_request_count,
            COALESCE(r.high_burn, 0)                                    AS high_token_burn_count,
            COALESCE(r.plan_errors, 0)                                  AS planning_error_count,
            COALESCE(t.single_drops, 0)                                 AS single_turn_dropoff_count,
            COALESCE(t.rapid_rephrase, 0)                               AS rapid_rephrasing_count,
            COALESCE(t.abandoned, 0)                                    AS abandoned_count,
            COALESCE(r.critical_req, 0) + COALESCE(t.critical_thr, 0)   AS critical_count,
            COALESCE(r.warning_req, 0) + COALESCE(t.warning_thr, 0)     AS warning_count,
            ROUND(COALESCE(r.flagged_req, 0) * 100.0 / NULLIF(COALESCE(r.total_req, 0), 0), 2) AS flagged_request_pct
        FROM (
            SELECT
                database_name,
                agent_name,
                COUNT(*) AS total_req,
                COUNT_IF(flag_count > 0) AS flagged_req,
                COUNT_IF(flag_tool_looping) AS tool_looping,
                COUNT_IF(flag_excessive_steps) AS excessive_steps,
                COUNT_IF(flag_slow_request) AS slow_requests,
                COUNT_IF(flag_high_token_burn) AS high_burn,
                COUNT_IF(flag_planning_error) AS plan_errors,
                COUNT_IF(flag_count > 0 AND (flag_planning_error OR (flag_tool_looping AND flag_high_token_burn))) AS critical_req,
                COUNT_IF(flag_count > 0 AND NOT (flag_planning_error OR (flag_tool_looping AND flag_high_token_burn))) AS warning_req
            FROM yesterday_requests
            GROUP BY 1, 2
        ) r
        FULL OUTER JOIN (
            SELECT
                database_name,
                agent_name,
                COUNT(*) AS total_thr,
                COUNT_IF(flag_count > 0) AS flagged_thr,
                COUNT_IF(flag_single_turn_dropoff) AS single_drops,
                COUNT_IF(flag_rapid_rephrasing) AS rapid_rephrase,
                COUNT_IF(flag_abandoned_conversation) AS abandoned,
                COUNT_IF(flag_abandoned_conversation AND flag_rapid_rephrasing) AS critical_thr,
                COUNT_IF(flag_count > 0 AND NOT (flag_abandoned_conversation AND flag_rapid_rephrasing)) AS warning_thr
            FROM yesterday_threads
            GROUP BY 1, 2
        ) t ON r.database_name = t.database_name AND r.agent_name = t.agent_name
    ) src
    ON tgt.summary_date = src.summary_date
       AND tgt.environment = src.environment
       AND tgt.agent_name = src.agent_name
    WHEN MATCHED THEN UPDATE SET
        tgt.total_requests = src.total_requests,
        tgt.total_threads = src.total_threads,
        tgt.flagged_requests = src.flagged_requests,
        tgt.flagged_threads = src.flagged_threads,
        tgt.tool_looping_count = src.tool_looping_count,
        tgt.excessive_steps_count = src.excessive_steps_count,
        tgt.slow_request_count = src.slow_request_count,
        tgt.high_token_burn_count = src.high_token_burn_count,
        tgt.planning_error_count = src.planning_error_count,
        tgt.single_turn_dropoff_count = src.single_turn_dropoff_count,
        tgt.rapid_rephrasing_count = src.rapid_rephrasing_count,
        tgt.abandoned_count = src.abandoned_count,
        tgt.critical_count = src.critical_count,
        tgt.warning_count = src.warning_count,
        tgt.flagged_request_pct = src.flagged_request_pct,
        tgt.computed_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (
        summary_date, environment, agent_name,
        total_requests, total_threads, flagged_requests, flagged_threads,
        tool_looping_count, excessive_steps_count, slow_request_count,
        high_token_burn_count, planning_error_count,
        single_turn_dropoff_count, rapid_rephrasing_count, abandoned_count,
        critical_count, warning_count, flagged_request_pct
    ) VALUES (
        src.summary_date, src.environment, src.agent_name,
        src.total_requests, src.total_threads, src.flagged_requests, src.flagged_threads,
        src.tool_looping_count, src.excessive_steps_count, src.slow_request_count,
        src.high_token_burn_count, src.planning_error_count,
        src.single_turn_dropoff_count, src.rapid_rephrasing_count, src.abandoned_count,
        src.critical_count, src.warning_count, src.flagged_request_pct
    );
END;

ALTER TASK RETAIL_AI_EVAL.MONITORING.TASK_DAILY_INTERACTION_QUALITY RESUME;

-- ============================================================
-- ALERT: Interaction quality degradation
-- Fires if >20% of requests are flagged OR any critical flags
-- ============================================================
CREATE OR REPLACE ALERT RETAIL_AI_EVAL.MONITORING.ALERT_INTERACTION_QUALITY
    WAREHOUSE = RETAIL_AI_EVAL_WH
    SCHEDULE = 'USING CRON 0 7 * * * UTC'
    IF (EXISTS (
        SELECT 1
        FROM RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY
        WHERE summary_date = CURRENT_DATE() - 1
          AND (flagged_request_pct > 20 OR critical_count > 0)
          AND total_requests >= 5
    ))
    THEN
        INSERT INTO RETAIL_AI_EVAL.MONITORING.ALERT_HISTORY
            (alert_type, severity, environment, target_name, message, metric_value, threshold_value)
        SELECT
            'interaction_quality',
            CASE WHEN critical_count > 0 THEN 'CRITICAL' ELSE 'WARNING' END,
            environment,
            agent_name,
            'Interaction quality issues: ' ||
                flagged_requests || '/' || total_requests || ' requests flagged (' ||
                ROUND(flagged_request_pct, 1) || '%). ' ||
                'Looping: ' || tool_looping_count ||
                ', Excessive steps: ' || excessive_steps_count ||
                ', Slow: ' || slow_request_count ||
                ', High burn: ' || high_token_burn_count ||
                ', Errors: ' || planning_error_count ||
                ', Abandoned: ' || abandoned_count ||
                ', Rephrasing: ' || rapid_rephrasing_count,
            flagged_request_pct,
            20
        FROM RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY
        WHERE summary_date = CURRENT_DATE() - 1
          AND (flagged_request_pct > 20 OR critical_count > 0)
          AND total_requests >= 5;

ALTER ALERT RETAIL_AI_EVAL.MONITORING.ALERT_INTERACTION_QUALITY RESUME;

-- ============================================================
-- VIEW: Interaction quality dashboard
-- Combines daily trends + current flagged interactions
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_DASHBOARD AS
SELECT
    summary_date,
    environment,
    agent_name,
    total_requests,
    total_threads,
    flagged_requests,
    flagged_request_pct,
    tool_looping_count,
    excessive_steps_count,
    slow_request_count,
    high_token_burn_count,
    planning_error_count,
    single_turn_dropoff_count,
    rapid_rephrasing_count,
    abandoned_count,
    critical_count,
    warning_count,
    AVG(flagged_request_pct) OVER (
        PARTITION BY environment, agent_name
        ORDER BY summary_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_flagged_pct,
    SUM(flagged_requests) OVER (
        PARTITION BY environment, agent_name
        ORDER BY summary_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_flagged_count,
    SUM(abandoned_count + rapid_rephrasing_count) OVER (
        PARTITION BY environment, agent_name
        ORDER BY summary_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_user_struggle_count
FROM RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY;

-- ============================================================
-- Grants
-- ============================================================
USE ROLE SECURITYADMIN;

GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_REQUEST_QUALITY_SIGNALS TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_THREAD_QUALITY_SIGNALS TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_FLAGS TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_DASHBOARD TO ROLE RETAIL_AI_ADMIN;
GRANT ALL PRIVILEGES ON TABLE RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY TO ROLE RETAIL_AI_ADMIN;

GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_REQUEST_QUALITY_SIGNALS TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_THREAD_QUALITY_SIGNALS TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_FLAGS TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON VIEW RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_DASHBOARD TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON TABLE RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY TO ROLE RETAIL_AI_REVIEWER;

GRANT INSERT, SELECT ON TABLE RETAIL_AI_EVAL.MONITORING.INTERACTION_QUALITY_DAILY TO ROLE RETAIL_AI_DEPLOYER;
