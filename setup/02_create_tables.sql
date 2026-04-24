-- ============================================================================
-- 02_create_tables.sql
-- Creates the retail analytics tables in DEV and PROD
-- Run this after 01_create_databases.sql
-- ============================================================================

-- Macro: repeat for each environment
-- We use a stored procedure to avoid repetition

CREATE OR REPLACE PROCEDURE RETAIL_AI_DEV.ANALYTICS.CREATE_RETAIL_TABLES(db_name STRING)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    EXECUTE IMMEDIATE 'CREATE OR REPLACE TABLE ' || db_name || '.ANALYTICS.CUSTOMERS (
        customer_id         INTEGER,
        first_name          STRING,
        last_name           STRING,
        email               STRING,
        phone               STRING,
        city                STRING,
        state               STRING,
        country             STRING,
        customer_segment    STRING,
        loyalty_tier        STRING,
        created_at          DATE,
        lifetime_value      FLOAT
    )';

    EXECUTE IMMEDIATE 'CREATE OR REPLACE TABLE ' || db_name || '.ANALYTICS.PRODUCTS (
        product_id          INTEGER,
        product_name        STRING,
        category            STRING,
        subcategory         STRING,
        brand               STRING,
        unit_price          FLOAT,
        cost_price          FLOAT,
        weight_kg           FLOAT,
        is_active           BOOLEAN,
        launch_date         DATE
    )';

    EXECUTE IMMEDIATE 'CREATE OR REPLACE TABLE ' || db_name || '.ANALYTICS.ORDERS (
        order_id            INTEGER,
        customer_id         INTEGER,
        order_date          DATE,
        ship_date           DATE,
        delivery_date       DATE,
        order_status        STRING,
        shipping_method     STRING,
        payment_method      STRING,
        discount_pct        FLOAT,
        total_amount        FLOAT,
        shipping_cost       FLOAT
    )';

    EXECUTE IMMEDIATE 'CREATE OR REPLACE TABLE ' || db_name || '.ANALYTICS.ORDER_ITEMS (
        order_item_id       INTEGER,
        order_id            INTEGER,
        product_id          INTEGER,
        quantity            INTEGER,
        unit_price          FLOAT,
        discount_amount     FLOAT,
        line_total          FLOAT
    )';

    EXECUTE IMMEDIATE 'CREATE OR REPLACE TABLE ' || db_name || '.ANALYTICS.RETURNS (
        return_id           INTEGER,
        order_id            INTEGER,
        order_item_id       INTEGER,
        return_date         DATE,
        return_reason       STRING,
        refund_amount       FLOAT,
        return_status       STRING
    )';

    EXECUTE IMMEDIATE 'CREATE OR REPLACE TABLE ' || db_name || '.ANALYTICS.STORES (
        store_id            INTEGER,
        store_name          STRING,
        store_type          STRING,
        city                STRING,
        state               STRING,
        country             STRING,
        region              STRING,
        opened_date         DATE,
        square_footage      INTEGER,
        manager_name        STRING
    )';

    RETURN 'Tables created in ' || db_name;
END;
$$;

CALL RETAIL_AI_DEV.ANALYTICS.CREATE_RETAIL_TABLES('RETAIL_AI_DEV');
CALL RETAIL_AI_DEV.ANALYTICS.CREATE_RETAIL_TABLES('RETAIL_AI_PROD');
