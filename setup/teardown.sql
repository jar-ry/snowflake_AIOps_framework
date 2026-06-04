-- ============================================================================
-- teardown.sql
-- Complete environment purge for the AIOps framework.
-- Drops ALL objects created by the framework setup + the active example's
-- SV, agent, dashboard, data, and RBAC roles.
--
-- This file uses double-brace placeholders rendered from the active instance config.
-- Render it before running, e.g.:
--     python setup/bootstrap.py --render setup/teardown.sql > /tmp/teardown.sql
-- then paste the rendered SQL into a Snowsight worksheet as ACCOUNTADMIN.
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- ============================================================
-- 1. SUSPEND ALL TASKS AND ALERTS (must happen before DROP)
-- ============================================================
ALTER TASK IF EXISTS {{DB_EVAL}}.MONITORING.TASK_DAILY_USAGE_AGGREGATION SUSPEND;
ALTER TASK IF EXISTS {{DB_EVAL}}.MONITORING.TASK_DAILY_FEEDBACK_ANALYSIS SUSPEND;
ALTER TASK IF EXISTS {{DB_EVAL}}.MONITORING.TASK_DAILY_HEALTH_CHECKS SUSPEND;
ALTER TASK IF EXISTS {{DB_EVAL}}.MONITORING.TASK_WEEKLY_SV_EVAL SUSPEND;
ALTER TASK IF EXISTS {{DB_EVAL}}.MONITORING.TASK_WEEKLY_AGENT_EVAL SUSPEND;
ALTER TASK IF EXISTS {{DB_EVAL}}.MONITORING.TASK_DAILY_INTERACTION_QUALITY SUSPEND;

ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_NEGATIVE_FEEDBACK_SPIKE SUSPEND;
ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_ACCURACY_REGRESSION SUSPEND;
ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_LATENCY_DEGRADATION SUSPEND;
ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_COST_ANOMALY SUSPEND;
ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_ERROR_SPIKE SUSPEND;
ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_HEALTH_FAILURE SUSPEND;
ALTER ALERT IF EXISTS {{DB_EVAL}}.MONITORING.ALERT_INTERACTION_QUALITY SUSPEND;

-- ============================================================
-- 2. DROP AGENTS
-- ============================================================
DROP AGENT IF EXISTS {{DB_DEV}}.SEMANTIC.{{AGENT_NAME}};
DROP AGENT IF EXISTS {{DB_PROD}}.SEMANTIC.{{AGENT_NAME}};

-- ============================================================
-- 3. DROP SEMANTIC VIEWS
-- ============================================================
DROP SEMANTIC VIEW IF EXISTS {{DB_DEV}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}};
DROP SEMANTIC VIEW IF EXISTS {{DB_PROD}}.SEMANTIC.{{SEMANTIC_VIEW_NAME}};

-- ============================================================
-- 4. DROP STREAMLIT APPS
-- ============================================================
DROP STREAMLIT IF EXISTS {{DB_EVAL}}.MONITORING.AI_MONITORING_DASHBOARD;

-- ============================================================
-- 5. DROP ALL THREE DATABASES (cascades schemas, tables, views, stages, tasks, alerts, procedures)
-- ============================================================
DROP DATABASE IF EXISTS {{DB_DEV}};
DROP DATABASE IF EXISTS {{DB_PROD}};
DROP DATABASE IF EXISTS {{DB_EVAL}};

-- ============================================================
-- 6. DROP WAREHOUSE
-- ============================================================
DROP WAREHOUSE IF EXISTS {{WAREHOUSE}};

-- ============================================================
-- 7. DROP RBAC ROLES (created by 04_rbac_setup.sql)
-- ============================================================
USE ROLE SECURITYADMIN;

REVOKE ROLE {{ROLE_ANALYST}} FROM ROLE {{ROLE_REVIEWER}};
REVOKE ROLE {{ROLE_REVIEWER}} FROM ROLE {{ROLE_ADMIN}};
REVOKE ROLE {{ROLE_DEPLOYER}} FROM ROLE {{ROLE_ADMIN}};
REVOKE ROLE {{ROLE_ADMIN}} FROM ROLE SYSADMIN;

DROP ROLE IF EXISTS {{ROLE_ANALYST}};
DROP ROLE IF EXISTS {{ROLE_REVIEWER}};
DROP ROLE IF EXISTS {{ROLE_DEPLOYER}};
DROP ROLE IF EXISTS {{ROLE_ADMIN}};

-- ============================================================
-- 8. VERIFY CLEAN STATE (each should return no rows)
-- ============================================================
USE ROLE ACCOUNTADMIN;
SHOW DATABASES LIKE '{{DB_DEV}}';
SHOW DATABASES LIKE '{{DB_PROD}}';
SHOW DATABASES LIKE '{{DB_EVAL}}';
SHOW WAREHOUSES LIKE '{{WAREHOUSE}}';
SHOW ROLES LIKE '{{ROLE_ADMIN}}';
