-- ============================================================================
-- 04_rbac_setup.sql
-- Role-based access control for the AI evaluation framework
-- Two-tier model: Analyst (dev), Reviewer (approve), Deployer (prod)
-- ============================================================================

USE ROLE SECURITYADMIN;

-- ============================================================
-- Custom Roles
-- ============================================================

CREATE ROLE IF NOT EXISTS {{ROLE_ANALYST}};
COMMENT ON ROLE {{ROLE_ANALYST}} IS 'Data analysts who create/edit semantic views in DEV';

CREATE ROLE IF NOT EXISTS {{ROLE_REVIEWER}};
COMMENT ON ROLE {{ROLE_REVIEWER}} IS 'Reviewers who approve promotions from DEV to PROD';

CREATE ROLE IF NOT EXISTS {{ROLE_DEPLOYER}};
COMMENT ON ROLE {{ROLE_DEPLOYER}} IS 'CI/CD service account that deploys to DEV and PROD';

CREATE ROLE IF NOT EXISTS {{ROLE_ADMIN}};
COMMENT ON ROLE {{ROLE_ADMIN}} IS 'Admin role for full framework management';

-- ============================================================
-- Role hierarchy
-- ============================================================
GRANT ROLE {{ROLE_ANALYST}}  TO ROLE {{ROLE_REVIEWER}};
GRANT ROLE {{ROLE_REVIEWER}} TO ROLE {{ROLE_ADMIN}};
GRANT ROLE {{ROLE_DEPLOYER}} TO ROLE {{ROLE_ADMIN}};
GRANT ROLE {{ROLE_ADMIN}}    TO ROLE SYSADMIN;

-- ============================================================
-- Warehouse grants
-- ============================================================
GRANT USAGE ON WAREHOUSE {{WAREHOUSE}} TO ROLE {{ROLE_ANALYST}};
GRANT USAGE ON WAREHOUSE {{WAREHOUSE}} TO ROLE {{ROLE_REVIEWER}};
GRANT USAGE ON WAREHOUSE {{WAREHOUSE}} TO ROLE {{ROLE_DEPLOYER}};

-- ============================================================
-- ANALYST: Full access to DEV, read-only on PROD
-- ============================================================
GRANT USAGE ON DATABASE {{DB_DEV}} TO ROLE {{ROLE_ANALYST}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_DEV}} TO ROLE {{ROLE_ANALYST}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{DB_DEV}}.ANALYTICS TO ROLE {{ROLE_ANALYST}};
GRANT CREATE SEMANTIC VIEW ON SCHEMA {{DB_DEV}}.SEMANTIC TO ROLE {{ROLE_ANALYST}};
GRANT ALL ON ALL SEMANTIC VIEWS IN SCHEMA {{DB_DEV}}.SEMANTIC TO ROLE {{ROLE_ANALYST}};

GRANT USAGE ON DATABASE {{DB_PROD}} TO ROLE {{ROLE_ANALYST}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_PROD}} TO ROLE {{ROLE_ANALYST}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{DB_PROD}}.ANALYTICS TO ROLE {{ROLE_ANALYST}};

GRANT USAGE ON DATABASE {{DB_EVAL}} TO ROLE {{ROLE_ANALYST}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_EVAL}} TO ROLE {{ROLE_ANALYST}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{DB_EVAL}}.RESULTS TO ROLE {{ROLE_ANALYST}};

-- ============================================================
-- DEPLOYER: Deploy semantic views and agents to DEV and PROD
-- ============================================================
GRANT USAGE ON DATABASE {{DB_DEV}} TO ROLE {{ROLE_DEPLOYER}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_DEV}} TO ROLE {{ROLE_DEPLOYER}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{DB_DEV}}.ANALYTICS TO ROLE {{ROLE_DEPLOYER}};
GRANT CREATE SEMANTIC VIEW ON SCHEMA {{DB_DEV}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};
GRANT ALL ON ALL SEMANTIC VIEWS IN SCHEMA {{DB_DEV}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};

GRANT USAGE ON DATABASE {{DB_PROD}} TO ROLE {{ROLE_DEPLOYER}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_PROD}} TO ROLE {{ROLE_DEPLOYER}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{DB_PROD}}.ANALYTICS TO ROLE {{ROLE_DEPLOYER}};
GRANT CREATE SEMANTIC VIEW ON SCHEMA {{DB_PROD}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};
GRANT ALL ON ALL SEMANTIC VIEWS IN SCHEMA {{DB_PROD}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};

GRANT USAGE ON DATABASE {{DB_EVAL}} TO ROLE {{ROLE_DEPLOYER}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_EVAL}} TO ROLE {{ROLE_DEPLOYER}};
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA {{DB_EVAL}}.RESULTS TO ROLE {{ROLE_DEPLOYER}};

-- CI/CD eval privileges: the deployer (CI service account) must be able to
-- run agent evaluations and (re)deploy agents. EXECUTE_AI_EVALUATION needs
-- Cortex access; the eval flow creates a dataset table, a config stage, and a
-- file format in the SEMANTIC schema; deploys CREATE OR REPLACE the agent.
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE {{ROLE_DEPLOYER}};
GRANT CREATE AGENT ON SCHEMA {{DB_DEV}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};
GRANT CREATE AGENT ON SCHEMA {{DB_PROD}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};
GRANT CREATE TABLE, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA {{DB_DEV}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};
GRANT CREATE TABLE, CREATE STAGE, CREATE FILE FORMAT ON SCHEMA {{DB_PROD}}.SEMANTIC TO ROLE {{ROLE_DEPLOYER}};

-- ============================================================
-- REVIEWER: Can view everything, approve promotions
-- ============================================================
GRANT USAGE ON DATABASE {{DB_EVAL}} TO ROLE {{ROLE_REVIEWER}};
GRANT USAGE ON ALL SCHEMAS IN DATABASE {{DB_EVAL}} TO ROLE {{ROLE_REVIEWER}};
GRANT SELECT ON ALL TABLES IN SCHEMA {{DB_EVAL}}.RESULTS TO ROLE {{ROLE_REVIEWER}};

-- ============================================================
-- Future grants for new objects
-- ============================================================
GRANT SELECT ON FUTURE TABLES IN SCHEMA {{DB_DEV}}.ANALYTICS TO ROLE {{ROLE_ANALYST}};
GRANT SELECT ON FUTURE TABLES IN SCHEMA {{DB_PROD}}.ANALYTICS TO ROLE {{ROLE_ANALYST}};
GRANT SELECT ON FUTURE TABLES IN SCHEMA {{DB_EVAL}}.RESULTS TO ROLE {{ROLE_ANALYST}};

-- Deployer (CI) must be able to SELECT domain tables created AFTER this script
-- runs (the example's data scripts create them later). Without these FUTURE
-- grants, the SV question-bank eval -- which executes Cortex Analyst's generated
-- SQL as the deployer role -- cannot read the tables and silently scores 0%.
GRANT SELECT ON FUTURE TABLES IN SCHEMA {{DB_DEV}}.ANALYTICS TO ROLE {{ROLE_DEPLOYER}};
GRANT SELECT ON FUTURE TABLES IN SCHEMA {{DB_PROD}}.ANALYTICS TO ROLE {{ROLE_DEPLOYER}};
