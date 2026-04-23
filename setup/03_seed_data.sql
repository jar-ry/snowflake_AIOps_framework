-- ============================================================================
-- 03_seed_data.sql
-- Seeds mock retail data into DEV, TEST, and PROD environments
-- Generates realistic data using Snowflake SQL generators
-- ============================================================================

USE ROLE SYSADMIN;
USE WAREHOUSE RETAIL_AI_EVAL_WH;

-- ============================================================
-- CUSTOMERS (500 rows)
-- ============================================================
INSERT INTO RETAIL_AI_DEV.ANALYTICS.CUSTOMERS
SELECT
    SEQ4()                                                          AS customer_id,
    CASE MOD(SEQ4(), 20)
        WHEN 0 THEN 'Emma' WHEN 1 THEN 'James' WHEN 2 THEN 'Olivia' WHEN 3 THEN 'Liam'
        WHEN 4 THEN 'Sophia' WHEN 5 THEN 'Noah' WHEN 6 THEN 'Ava' WHEN 7 THEN 'Mason'
        WHEN 8 THEN 'Isabella' WHEN 9 THEN 'Ethan' WHEN 10 THEN 'Mia' WHEN 11 THEN 'Logan'
        WHEN 12 THEN 'Charlotte' WHEN 13 THEN 'Lucas' WHEN 14 THEN 'Amelia' WHEN 15 THEN 'Jack'
        WHEN 16 THEN 'Harper' WHEN 17 THEN 'Aiden' WHEN 18 THEN 'Ella' ELSE 'Owen'
    END                                                             AS first_name,
    CASE MOD(SEQ4(), 15)
        WHEN 0 THEN 'Smith' WHEN 1 THEN 'Johnson' WHEN 2 THEN 'Williams' WHEN 3 THEN 'Brown'
        WHEN 4 THEN 'Jones' WHEN 5 THEN 'Garcia' WHEN 6 THEN 'Miller' WHEN 7 THEN 'Davis'
        WHEN 8 THEN 'Rodriguez' WHEN 9 THEN 'Martinez' WHEN 10 THEN 'Wilson' WHEN 11 THEN 'Anderson'
        WHEN 12 THEN 'Taylor' WHEN 13 THEN 'Thomas' ELSE 'Moore'
    END                                                             AS last_name,
    LOWER(first_name || '.' || last_name || SEQ4() || '@email.com') AS email,
    '+1-555-' || LPAD(MOD(SEQ4() * 7, 10000)::STRING, 4, '0')     AS phone,
    CASE MOD(SEQ4(), 10)
        WHEN 0 THEN 'New York' WHEN 1 THEN 'Los Angeles' WHEN 2 THEN 'Chicago'
        WHEN 3 THEN 'Houston' WHEN 4 THEN 'Phoenix' WHEN 5 THEN 'Seattle'
        WHEN 6 THEN 'Denver' WHEN 7 THEN 'Boston' WHEN 8 THEN 'Austin' ELSE 'Miami'
    END                                                             AS city,
    CASE MOD(SEQ4(), 10)
        WHEN 0 THEN 'NY' WHEN 1 THEN 'CA' WHEN 2 THEN 'IL' WHEN 3 THEN 'TX'
        WHEN 4 THEN 'AZ' WHEN 5 THEN 'WA' WHEN 6 THEN 'CO' WHEN 7 THEN 'MA'
        WHEN 8 THEN 'TX' ELSE 'FL'
    END                                                             AS state,
    'US'                                                            AS country,
    CASE MOD(SEQ4(), 4)
        WHEN 0 THEN 'Consumer' WHEN 1 THEN 'Corporate' WHEN 2 THEN 'Small Business' ELSE 'Enterprise'
    END                                                             AS customer_segment,
    CASE MOD(SEQ4(), 4)
        WHEN 0 THEN 'Bronze' WHEN 1 THEN 'Silver' WHEN 2 THEN 'Gold' ELSE 'Platinum'
    END                                                             AS loyalty_tier,
    DATEADD('day', -MOD(SEQ4() * 17, 1825), '2025-12-31')::DATE    AS created_at,
    ROUND(UNIFORM(100, 50000, RANDOM()), 2)                         AS lifetime_value
FROM TABLE(GENERATOR(ROWCOUNT => 500));

-- ============================================================
-- PRODUCTS (100 rows)
-- ============================================================
INSERT INTO RETAIL_AI_DEV.ANALYTICS.PRODUCTS
SELECT
    SEQ4()                                                                  AS product_id,
    CASE MOD(SEQ4(), 5)
        WHEN 0 THEN 'Premium ' WHEN 1 THEN 'Classic ' WHEN 2 THEN 'Ultra '
        WHEN 3 THEN 'Essential ' ELSE 'Pro '
    END ||
    CASE MOD(SEQ4(), 10)
        WHEN 0 THEN 'Laptop' WHEN 1 THEN 'Headphones' WHEN 2 THEN 'Monitor'
        WHEN 3 THEN 'Keyboard' WHEN 4 THEN 'Mouse' WHEN 5 THEN 'Tablet'
        WHEN 6 THEN 'Speaker' WHEN 7 THEN 'Camera' WHEN 8 THEN 'Phone' ELSE 'Watch'
    END                                                                     AS product_name,
    CASE MOD(SEQ4(), 5)
        WHEN 0 THEN 'Electronics' WHEN 1 THEN 'Audio' WHEN 2 THEN 'Computing'
        WHEN 3 THEN 'Accessories' ELSE 'Wearables'
    END                                                                     AS category,
    CASE MOD(SEQ4(), 8)
        WHEN 0 THEN 'Laptops' WHEN 1 THEN 'Over-ear' WHEN 2 THEN 'Displays'
        WHEN 3 THEN 'Input Devices' WHEN 4 THEN 'Mice' WHEN 5 THEN 'Tablets'
        WHEN 6 THEN 'Portable Audio' ELSE 'Smartwatches'
    END                                                                     AS subcategory,
    CASE MOD(SEQ4(), 6)
        WHEN 0 THEN 'TechCorp' WHEN 1 THEN 'SoundMax' WHEN 2 THEN 'PixelPro'
        WHEN 3 THEN 'KeyMaster' WHEN 4 THEN 'SwiftGear' ELSE 'NovaTech'
    END                                                                     AS brand,
    ROUND(UNIFORM(9.99, 2499.99, RANDOM()), 2)                             AS unit_price,
    ROUND(unit_price * UNIFORM(0.3, 0.7, RANDOM()), 2)                     AS cost_price,
    ROUND(UNIFORM(0.1, 5.0, RANDOM()), 2)                                  AS weight_kg,
    IFF(MOD(SEQ4(), 10) < 9, TRUE, FALSE)                                  AS is_active,
    DATEADD('day', -MOD(SEQ4() * 13, 730), '2025-12-31')::DATE             AS launch_date
FROM TABLE(GENERATOR(ROWCOUNT => 100));

-- ============================================================
-- STORES (20 rows)
-- ============================================================
INSERT INTO RETAIL_AI_DEV.ANALYTICS.STORES
SELECT
    SEQ4()                                                  AS store_id,
    'Store #' || LPAD(SEQ4()::STRING, 3, '0')              AS store_name,
    CASE MOD(SEQ4(), 3)
        WHEN 0 THEN 'Flagship' WHEN 1 THEN 'Outlet' ELSE 'Standard'
    END                                                     AS store_type,
    CASE MOD(SEQ4(), 10)
        WHEN 0 THEN 'New York' WHEN 1 THEN 'Los Angeles' WHEN 2 THEN 'Chicago'
        WHEN 3 THEN 'Houston' WHEN 4 THEN 'Phoenix' WHEN 5 THEN 'Seattle'
        WHEN 6 THEN 'Denver' WHEN 7 THEN 'Boston' WHEN 8 THEN 'Austin' ELSE 'Miami'
    END                                                     AS city,
    CASE MOD(SEQ4(), 10)
        WHEN 0 THEN 'NY' WHEN 1 THEN 'CA' WHEN 2 THEN 'IL' WHEN 3 THEN 'TX'
        WHEN 4 THEN 'AZ' WHEN 5 THEN 'WA' WHEN 6 THEN 'CO' WHEN 7 THEN 'MA'
        WHEN 8 THEN 'TX' ELSE 'FL'
    END                                                     AS state,
    'US'                                                    AS country,
    CASE MOD(SEQ4(), 4)
        WHEN 0 THEN 'Northeast' WHEN 1 THEN 'West' WHEN 2 THEN 'Midwest' ELSE 'South'
    END                                                     AS region,
    DATEADD('day', -MOD(SEQ4() * 31, 3650), '2025-12-31')::DATE AS opened_date,
    UNIFORM(5000, 50000, RANDOM())                          AS square_footage,
    CASE MOD(SEQ4(), 8)
        WHEN 0 THEN 'Sarah Chen' WHEN 1 THEN 'Mike Rivera' WHEN 2 THEN 'Lisa Park'
        WHEN 3 THEN 'Tom Wilson' WHEN 4 THEN 'Anna Kumar' WHEN 5 THEN 'David Lee'
        WHEN 6 THEN 'Maria Santos' ELSE 'John Kim'
    END                                                     AS manager_name
FROM TABLE(GENERATOR(ROWCOUNT => 20));

-- ============================================================
-- ORDERS (5000 rows)
-- ============================================================
INSERT INTO RETAIL_AI_DEV.ANALYTICS.ORDERS
SELECT
    SEQ4()                                                              AS order_id,
    UNIFORM(0, 499, RANDOM())                                          AS customer_id,
    DATEADD('day', -MOD(SEQ4() * 3, 730), '2025-12-31')::DATE          AS order_date,
    DATEADD('day', UNIFORM(1, 5, RANDOM()), order_date)::DATE           AS ship_date,
    DATEADD('day', UNIFORM(3, 14, RANDOM()), ship_date)::DATE           AS delivery_date,
    CASE MOD(SEQ4(), 20)
        WHEN 0 THEN 'Cancelled' WHEN 1 THEN 'Returned'
        WHEN 2 THEN 'Processing' ELSE 'Delivered'
    END                                                                 AS order_status,
    CASE MOD(SEQ4(), 4)
        WHEN 0 THEN 'Standard' WHEN 1 THEN 'Express' WHEN 2 THEN 'Next Day' ELSE 'Economy'
    END                                                                 AS shipping_method,
    CASE MOD(SEQ4(), 4)
        WHEN 0 THEN 'Credit Card' WHEN 1 THEN 'Debit Card' WHEN 2 THEN 'PayPal' ELSE 'Gift Card'
    END                                                                 AS payment_method,
    ROUND(UNIFORM(0, 30, RANDOM()) / 100.0, 2)                         AS discount_pct,
    ROUND(UNIFORM(15, 5000, RANDOM()), 2)                               AS total_amount,
    ROUND(UNIFORM(0, 25, RANDOM()), 2)                                  AS shipping_cost
FROM TABLE(GENERATOR(ROWCOUNT => 5000));

-- ============================================================
-- ORDER_ITEMS (12000 rows)
-- ============================================================
INSERT INTO RETAIL_AI_DEV.ANALYTICS.ORDER_ITEMS
SELECT
    SEQ4()                                                      AS order_item_id,
    UNIFORM(0, 4999, RANDOM())                                  AS order_id,
    UNIFORM(0, 99, RANDOM())                                    AS product_id,
    UNIFORM(1, 5, RANDOM())                                     AS quantity,
    ROUND(UNIFORM(9.99, 2499.99, RANDOM()), 2)                  AS unit_price,
    ROUND(unit_price * UNIFORM(0, 20, RANDOM()) / 100.0, 2)     AS discount_amount,
    ROUND((unit_price * quantity) - discount_amount, 2)          AS line_total
FROM TABLE(GENERATOR(ROWCOUNT => 12000));

-- ============================================================
-- RETURNS (800 rows)
-- ============================================================
INSERT INTO RETAIL_AI_DEV.ANALYTICS.RETURNS
SELECT
    SEQ4()                                                              AS return_id,
    UNIFORM(0, 4999, RANDOM())                                          AS order_id,
    UNIFORM(0, 11999, RANDOM())                                         AS order_item_id,
    DATEADD('day', UNIFORM(1, 30, RANDOM()),
        DATEADD('day', -MOD(SEQ4() * 5, 730), '2025-12-31'))::DATE      AS return_date,
    CASE MOD(SEQ4(), 6)
        WHEN 0 THEN 'Defective' WHEN 1 THEN 'Wrong Item' WHEN 2 THEN 'Not as Described'
        WHEN 3 THEN 'Changed Mind' WHEN 4 THEN 'Too Late' ELSE 'Damaged in Shipping'
    END                                                                 AS return_reason,
    ROUND(UNIFORM(10, 2500, RANDOM()), 2)                               AS refund_amount,
    CASE MOD(SEQ4(), 3)
        WHEN 0 THEN 'Approved' WHEN 1 THEN 'Pending' ELSE 'Rejected'
    END                                                                 AS return_status
FROM TABLE(GENERATOR(ROWCOUNT => 800));

-- ============================================================
-- Copy data to TEST and PROD environments
-- ============================================================
INSERT INTO RETAIL_AI_TEST.ANALYTICS.CUSTOMERS   SELECT * FROM RETAIL_AI_DEV.ANALYTICS.CUSTOMERS;
INSERT INTO RETAIL_AI_TEST.ANALYTICS.PRODUCTS    SELECT * FROM RETAIL_AI_DEV.ANALYTICS.PRODUCTS;
INSERT INTO RETAIL_AI_TEST.ANALYTICS.STORES      SELECT * FROM RETAIL_AI_DEV.ANALYTICS.STORES;
INSERT INTO RETAIL_AI_TEST.ANALYTICS.ORDERS      SELECT * FROM RETAIL_AI_DEV.ANALYTICS.ORDERS;
INSERT INTO RETAIL_AI_TEST.ANALYTICS.ORDER_ITEMS SELECT * FROM RETAIL_AI_DEV.ANALYTICS.ORDER_ITEMS;
INSERT INTO RETAIL_AI_TEST.ANALYTICS.RETURNS     SELECT * FROM RETAIL_AI_DEV.ANALYTICS.RETURNS;

INSERT INTO RETAIL_AI_PROD.ANALYTICS.CUSTOMERS   SELECT * FROM RETAIL_AI_DEV.ANALYTICS.CUSTOMERS;
INSERT INTO RETAIL_AI_PROD.ANALYTICS.PRODUCTS    SELECT * FROM RETAIL_AI_DEV.ANALYTICS.PRODUCTS;
INSERT INTO RETAIL_AI_PROD.ANALYTICS.STORES      SELECT * FROM RETAIL_AI_DEV.ANALYTICS.STORES;
INSERT INTO RETAIL_AI_PROD.ANALYTICS.ORDERS      SELECT * FROM RETAIL_AI_DEV.ANALYTICS.ORDERS;
INSERT INTO RETAIL_AI_PROD.ANALYTICS.ORDER_ITEMS SELECT * FROM RETAIL_AI_DEV.ANALYTICS.ORDER_ITEMS;
INSERT INTO RETAIL_AI_PROD.ANALYTICS.RETURNS     SELECT * FROM RETAIL_AI_DEV.ANALYTICS.RETURNS;
