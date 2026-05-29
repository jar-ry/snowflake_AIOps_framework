-- ============================================================================
-- teardown.sql
-- Complete environment purge for AIOps V1 framework.
-- Drops ALL objects created by scripts 01-11, SV, agent, dashboard, and RBAC.
-- Run as ACCOUNTADMIN in a Snowsight worksheet.
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- ============================================================
-- 1. SUSPEND ALL TASKS AND ALERTS (must happen before DROP)
-- ============================================================
ALTER TASK IF EXISTS RETAIL_AI_EVAL.MONITORING.TASK_DAILY_USAGE_AGGREGATION SUSPEND;
ALTER TASK IF EXISTS RETAIL_AI_EVAL.MONITORING.TASK_DAILY_FEEDBACK_ANALYSIS SUSPEND;
ALTER TASK IF EXISTS RETAIL_AI_EVAL.MONITORING.TASK_DAILY_HEALTH_CHECKS SUSPEND;
ALTER TASK IF EXISTS RETAIL_AI_EVAL.MONITORING.TASK_WEEKLY_SV_EVAL SUSPEND;
ALTER TASK IF EXISTS RETAIL_AI_EVAL.MONITORING.TASK_WEEKLY_AGENT_EVAL SUSPEND;
ALTER TASK IF EXISTS RETAIL_AI_EVAL.MONITORING.TASK_DAILY_INTERACTION_QUALITY SUSPEND;

ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_NEGATIVE_FEEDBACK_SPIKE SUSPEND;
ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_ACCURACY_REGRESSION SUSPEND;
ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_LATENCY_DEGRADATION SUSPEND;
ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_COST_ANOMALY SUSPEND;
ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_ERROR_SPIKE SUSPEND;
ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_HEALTH_FAILURE SUSPEND;
ALTER ALERT IF EXISTS RETAIL_AI_EVAL.MONITORING.ALERT_INTERACTION_QUALITY SUSPEND;

-- ============================================================
-- 2. DROP AGENTS
-- ============================================================
DROP AGENT IF EXISTS RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT;
DROP AGENT IF EXISTS RETAIL_AI_PROD.SEMANTIC.RETAIL_AGENT;

-- ============================================================
-- 3. DROP SEMANTIC VIEWS
-- ============================================================
DROP SEMANTIC VIEW IF EXISTS RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV;
DROP SEMANTIC VIEW IF EXISTS RETAIL_AI_PROD.SEMANTIC.RETAIL_ANALYTICS_SV;

-- ============================================================
-- 4. DROP STREAMLIT APPS
-- ============================================================
DROP STREAMLIT IF EXISTS RETAIL_AI_EVAL.MONITORING.AI_MONITORING_DASHBOARD;

-- ============================================================
-- 5. DROP ALL THREE DATABASES (cascades schemas, tables, views, stages, tasks, alerts, procedures)
-- ============================================================
DROP DATABASE IF EXISTS RETAIL_AI_DEV;
DROP DATABASE IF EXISTS RETAIL_AI_PROD;
DROP DATABASE IF EXISTS RETAIL_AI_EVAL;

-- ============================================================
-- 6. DROP WAREHOUSE
-- ============================================================
DROP WAREHOUSE IF EXISTS RETAIL_AI_EVAL_WH;

-- ============================================================
-- 7. DROP RBAC ROLES (created by 04_rbac_setup.sql)
-- ============================================================
USE ROLE SECURITYADMIN;

REVOKE ROLE RETAIL_AI_ANALYST FROM ROLE RETAIL_AI_REVIEWER;
REVOKE ROLE RETAIL_AI_REVIEWER FROM ROLE RETAIL_AI_ADMIN;
REVOKE ROLE RETAIL_AI_DEPLOYER FROM ROLE RETAIL_AI_ADMIN;
REVOKE ROLE RETAIL_AI_ADMIN FROM ROLE SYSADMIN;

DROP ROLE IF EXISTS RETAIL_AI_ANALYST;
DROP ROLE IF EXISTS RETAIL_AI_REVIEWER;
DROP ROLE IF EXISTS RETAIL_AI_DEPLOYER;
DROP ROLE IF EXISTS RETAIL_AI_ADMIN;

-- ============================================================
-- 8. VERIFY CLEAN STATE
-- ============================================================
USE ROLE ACCOUNTADMIN;
SHOW DATABASES LIKE 'RETAIL_AI%';
SHOW WAREHOUSES LIKE 'RETAIL_AI%';
SHOW ROLES LIKE 'RETAIL_AI%';
