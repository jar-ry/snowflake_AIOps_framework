-- ============================================================================
-- 05_observability_setup.sql
-- AI Observability setup using Snowflake's native ai_observability_events.
--
-- snowflake.local.ai_observability_events is Snowflake's built-in view that
-- captures all Cortex Agent and Analyst traces with rich structured data:
--   - Per-step token counts (input, output, cache_read, cache_write)
--   - Agent object identity (database, schema, agent name, object type)
--   - Tool selections, arguments, and execution results
--   - Planning traces with model, query, instructions, thinking_response
--   - OpenTelemetry trace/span correlation
--   - Thread tracking
--
-- No custom event table needed. We create convenience views on top.
-- ============================================================================

USE ROLE SYSADMIN;

-- ============================================================
-- Convenience view: Agent-level summary per request
-- Aggregates from the top-level "Agent" span
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES AS
SELECT
    e.TIMESTAMP                                                              AS event_time,
    e.START_TIMESTAMP                                                        AS start_time,
    DATEDIFF('millisecond', e.START_TIMESTAMP, e.TIMESTAMP)                  AS duration_ms,
    e.TRACE:trace_id::STRING                                                 AS trace_id,
    e.TRACE:span_id::STRING                                                  AS span_id,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING        AS database_name,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"::STRING          AS schema_name,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING          AS agent_name,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.object.type"::STRING          AS object_type,
    e.SCOPE:name::STRING                                                     AS scope_name,
    e.RECORD:name::STRING                                                    AS span_name,
    e.RECORD:status.code::STRING                                             AS status_code,
    e.RECORD:status.message::STRING                                          AS status_message,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.model"::STRING AS model_used,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.query"::STRING AS user_query,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.status"::STRING AS planning_status,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"::FLOAT AS planning_duration_ms,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.input"::INTEGER     AS input_tokens,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.output"::INTEGER    AS output_tokens,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::INTEGER     AS total_tokens,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_read_input"::INTEGER AS cache_read_tokens,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_write_input"::INTEGER AS cache_write_tokens,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.name"::STRING    AS tool_selected,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.id"::STRING      AS tool_selection_id,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.step_number"::INTEGER           AS step_number,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id"::STRING                       AS thread_id,
    e.RECORD_ATTRIBUTES:"request_id"::STRING                                                  AS request_id,
    e.RECORD_ATTRIBUTES:"ai.observability.input_id"::STRING                                   AS input_id
FROM snowflake.local.ai_observability_events e
WHERE e.RECORD_TYPE = 'SPAN'
  AND e.SCOPE:name::STRING = 'snow.cortex.agent';

-- ============================================================
-- Convenience view: Agent request-level rollup
-- One row per trace_id with aggregated token counts and step count
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.OBSERVABILITY.AGENT_REQUEST_SUMMARY AS
SELECT
    trace_id,
    MIN(start_time)                                     AS request_start,
    MAX(event_time)                                     AS request_end,
    DATEDIFF('millisecond', MIN(start_time), MAX(event_time)) AS total_duration_ms,
    MAX(database_name)                                  AS database_name,
    MAX(schema_name)                                    AS schema_name,
    MAX(agent_name)                                     AS agent_name,
    MAX(model_used)                                     AS model_used,
    MAX(user_query)                                     AS user_query,
    MAX(status_code)                                    AS status_code,
    MAX(thread_id)                                      AS thread_id,
    SUM(COALESCE(input_tokens, 0))                      AS total_input_tokens,
    SUM(COALESCE(output_tokens, 0))                     AS total_output_tokens,
    SUM(COALESCE(total_tokens, 0))                      AS total_tokens,
    SUM(COALESCE(cache_read_tokens, 0))                 AS total_cache_read_tokens,
    MAX(step_number)                                    AS max_step_number,
    COUNT(DISTINCT tool_selected)                       AS distinct_tools_used,
    ARRAY_AGG(DISTINCT tool_selected) WITHIN GROUP (ORDER BY step_number) AS tools_used
FROM RETAIL_AI_EVAL.OBSERVABILITY.AGENT_TRACES
WHERE span_name LIKE 'ReasoningAgentStepPlanning%'
   OR span_name LIKE 'CodingAgent.Step%'
GROUP BY trace_id;

-- ============================================================
-- Convenience view: Cortex Analyst query logs
-- Filters for analyst tool executions within agent traces
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.OBSERVABILITY.ANALYST_QUERIES AS
SELECT
    e.TIMESTAMP                                                              AS query_time,
    e.START_TIMESTAMP                                                        AS start_time,
    DATEDIFF('millisecond', e.START_TIMESTAMP, e.TIMESTAMP)                  AS latency_ms,
    e.TRACE:trace_id::STRING                                                 AS trace_id,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING        AS database_name,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"::STRING          AS schema_name,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING          AS agent_name,
    e.RECORD:name::STRING                                                    AS span_name,
    e.RECORD:status.code::STRING                                             AS status_code,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.query"::STRING AS natural_language_query,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::INTEGER AS total_tokens,
    e.RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.name"::STRING AS tool_name
FROM snowflake.local.ai_observability_events e
WHERE e.RECORD_TYPE = 'SPAN'
  AND e.SCOPE:name::STRING = 'snow.cortex.agent'
  AND (e.RECORD:name::STRING ILIKE '%Analyst%' OR e.RECORD:name::STRING ILIKE '%SqlExecution%');

-- ============================================================
-- Convenience view: LLM-level spans (non-agent COMPLETE calls)
-- ============================================================
CREATE OR REPLACE VIEW RETAIL_AI_EVAL.OBSERVABILITY.LLM_CALLS AS
SELECT
    e.TIMESTAMP                                         AS call_time,
    e.START_TIMESTAMP                                   AS start_time,
    DATEDIFF('millisecond', e.START_TIMESTAMP, e.TIMESTAMP) AS duration_ms,
    e.TRACE:trace_id::STRING                            AS trace_id,
    e.RECORD:name::STRING                               AS span_name,
    e.RECORD:status.code::STRING                        AS status_code,
    e.RECORD_ATTRIBUTES                                 AS attributes
FROM snowflake.local.ai_observability_events e
WHERE e.RECORD_TYPE = 'SPAN'
  AND e.SCOPE:name::STRING IS DISTINCT FROM 'snow.cortex.agent'
  AND e.RECORD:name::STRING = 'ai.observability.llm.span';

-- ============================================================
-- Grants
-- ============================================================
USE ROLE SECURITYADMIN;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON ALL VIEWS IN SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_ADMIN;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_ADMIN;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON ALL VIEWS IN SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_REVIEWER;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_REVIEWER;

GRANT USAGE ON SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_DEPLOYER;
GRANT SELECT ON ALL VIEWS IN SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_DEPLOYER;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA RETAIL_AI_EVAL.OBSERVABILITY TO ROLE RETAIL_AI_DEPLOYER;
