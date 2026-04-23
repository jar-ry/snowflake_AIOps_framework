-- ============================================================================
-- retail_analytics_sv.sql (TEST environment)
-- Identical to DEV but targets RETAIL_AI_TEST database
-- Deployed automatically by CI/CD after evaluation passes
-- ============================================================================

CREATE OR REPLACE SEMANTIC VIEW RETAIL_AI_TEST.SEMANTIC.RETAIL_ANALYTICS_SV
  COMMENT = 'Retail analytics semantic view for e-commerce data analysis'
AS SEMANTIC MODEL
  TABLES (
    RETAIL_AI_TEST.ANALYTICS.CUSTOMERS
      AS CUSTOMERS
      PRIMARY KEY (CUSTOMER_ID)
      WITH COLUMNS (
        CUSTOMER_ID AS "Customer ID" COMMENT 'Unique identifier for each customer',
        FIRST_NAME AS "First Name" COMMENT 'Customer first name',
        LAST_NAME AS "Last Name" COMMENT 'Customer last name',
        EMAIL AS "Email" COMMENT 'Customer email address',
        CITY AS "City" COMMENT 'City where the customer is located' VALUES ('New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Seattle', 'Denver', 'Boston', 'Austin', 'Miami'),
        STATE AS "State" COMMENT 'US state abbreviation' VALUES ('NY', 'CA', 'IL', 'TX', 'AZ', 'WA', 'CO', 'MA', 'FL'),
        COUNTRY AS "Country" COMMENT 'Country code' VALUES ('US'),
        CUSTOMER_SEGMENT AS "Customer Segment" COMMENT 'Business segment classification' VALUES ('Consumer', 'Corporate', 'Small Business', 'Enterprise'),
        LOYALTY_TIER AS "Loyalty Tier" COMMENT 'Customer loyalty program tier' VALUES ('Bronze', 'Silver', 'Gold', 'Platinum'),
        CREATED_AT AS "Customer Since" COMMENT 'Date the customer account was created',
        LIFETIME_VALUE AS "Lifetime Value" COMMENT 'Total lifetime value in USD'
      )
      WITH METRICS (
        "Total Customers" AS COUNT(CUSTOMER_ID) COMMENT 'Total number of unique customers',
        "Avg Lifetime Value" AS AVG(LIFETIME_VALUE) COMMENT 'Average customer lifetime value in USD'
      )
      WITH FILTERS (
        "High Value Customers" AS LIFETIME_VALUE > 10000 COMMENT 'Customers with lifetime value above $10,000',
        "Platinum Customers" AS LOYALTY_TIER = 'Platinum' COMMENT 'Customers in the Platinum loyalty tier'
      ),

    RETAIL_AI_TEST.ANALYTICS.PRODUCTS
      AS PRODUCTS
      PRIMARY KEY (PRODUCT_ID)
      WITH COLUMNS (
        PRODUCT_ID AS "Product ID" COMMENT 'Unique product identifier',
        PRODUCT_NAME AS "Product Name" COMMENT 'Display name of the product',
        CATEGORY AS "Category" COMMENT 'Top-level product category' VALUES ('Electronics', 'Audio', 'Computing', 'Accessories', 'Wearables'),
        SUBCATEGORY AS "Subcategory" COMMENT 'Detailed product subcategory',
        BRAND AS "Brand" COMMENT 'Product brand name' VALUES ('TechCorp', 'SoundMax', 'PixelPro', 'KeyMaster', 'SwiftGear', 'NovaTech'),
        UNIT_PRICE AS "Unit Price" COMMENT 'Retail price per unit in USD',
        COST_PRICE AS "Cost Price" COMMENT 'Cost of goods per unit in USD',
        IS_ACTIVE AS "Is Active" COMMENT 'Whether the product is currently active for sale',
        LAUNCH_DATE AS "Launch Date" COMMENT 'Date the product was launched'
      )
      WITH METRICS (
        "Total Products" AS COUNT(PRODUCT_ID) COMMENT 'Total number of products',
        "Avg Unit Price" AS AVG(UNIT_PRICE) COMMENT 'Average retail price across products',
        "Avg Margin Pct" AS AVG((UNIT_PRICE - COST_PRICE) / NULLIF(UNIT_PRICE, 0) * 100) COMMENT 'Average gross margin percentage'
      )
      WITH FILTERS (
        "Active Products" AS IS_ACTIVE = TRUE COMMENT 'Only active products'
      ),

    RETAIL_AI_TEST.ANALYTICS.ORDERS
      AS ORDERS
      PRIMARY KEY (ORDER_ID)
      WITH COLUMNS (
        ORDER_ID AS "Order ID" COMMENT 'Unique order identifier',
        CUSTOMER_ID AS "Customer ID" COMMENT 'Foreign key to the customer who placed the order',
        ORDER_DATE AS "Order Date" COMMENT 'Date the order was placed',
        SHIP_DATE AS "Ship Date" COMMENT 'Date the order was shipped',
        DELIVERY_DATE AS "Delivery Date" COMMENT 'Date the order was delivered',
        ORDER_STATUS AS "Order Status" COMMENT 'Current status of the order' VALUES ('Delivered', 'Processing', 'Cancelled', 'Returned'),
        SHIPPING_METHOD AS "Shipping Method" COMMENT 'Shipping method selected' VALUES ('Standard', 'Express', 'Next Day', 'Economy'),
        PAYMENT_METHOD AS "Payment Method" COMMENT 'Payment method used' VALUES ('Credit Card', 'Debit Card', 'PayPal', 'Gift Card'),
        DISCOUNT_PCT AS "Discount Percentage" COMMENT 'Discount applied as a decimal (0.10 = 10%)',
        TOTAL_AMOUNT AS "Order Total" COMMENT 'Total order amount in USD',
        SHIPPING_COST AS "Shipping Cost" COMMENT 'Shipping cost in USD'
      )
      WITH METRICS (
        "Total Orders" AS COUNT(ORDER_ID) COMMENT 'Total number of orders placed',
        "Total Revenue" AS SUM(TOTAL_AMOUNT) COMMENT 'Sum of all order amounts in USD',
        "Avg Order Value" AS AVG(TOTAL_AMOUNT) COMMENT 'Average order value in USD',
        "Total Shipping Revenue" AS SUM(SHIPPING_COST) COMMENT 'Total shipping charges collected'
      )
      WITH FILTERS (
        "Delivered Orders" AS ORDER_STATUS = 'Delivered' COMMENT 'Only orders with Delivered status',
        "Orders This Year" AS ORDER_DATE >= '2025-01-01' COMMENT 'Orders placed in 2025 or later'
      ),

    RETAIL_AI_TEST.ANALYTICS.ORDER_ITEMS
      AS ORDER_ITEMS
      PRIMARY KEY (ORDER_ITEM_ID)
      WITH COLUMNS (
        ORDER_ITEM_ID AS "Order Item ID" COMMENT 'Unique line item identifier',
        ORDER_ID AS "Order ID" COMMENT 'Foreign key to the parent order',
        PRODUCT_ID AS "Product ID" COMMENT 'Foreign key to the product',
        QUANTITY AS "Quantity" COMMENT 'Number of units ordered',
        UNIT_PRICE AS "Item Unit Price" COMMENT 'Price per unit at time of order in USD',
        DISCOUNT_AMOUNT AS "Item Discount" COMMENT 'Discount applied to this line item in USD',
        LINE_TOTAL AS "Line Total" COMMENT 'Total for this line item after discounts in USD'
      )
      WITH METRICS (
        "Total Units Sold" AS SUM(QUANTITY) COMMENT 'Total quantity of items sold',
        "Total Line Revenue" AS SUM(LINE_TOTAL) COMMENT 'Sum of all line item totals',
        "Avg Discount Per Item" AS AVG(DISCOUNT_AMOUNT) COMMENT 'Average discount amount per line item'
      ),

    RETAIL_AI_TEST.ANALYTICS.RETURNS
      AS RETURNS
      PRIMARY KEY (RETURN_ID)
      WITH COLUMNS (
        RETURN_ID AS "Return ID" COMMENT 'Unique return identifier',
        ORDER_ID AS "Order ID" COMMENT 'Foreign key to the original order',
        ORDER_ITEM_ID AS "Order Item ID" COMMENT 'Foreign key to the specific order item returned',
        RETURN_DATE AS "Return Date" COMMENT 'Date the return was initiated',
        RETURN_REASON AS "Return Reason" COMMENT 'Reason for the return' VALUES ('Defective', 'Wrong Item', 'Not as Described', 'Changed Mind', 'Too Late', 'Damaged in Shipping'),
        REFUND_AMOUNT AS "Refund Amount" COMMENT 'Amount refunded in USD',
        RETURN_STATUS AS "Return Status" COMMENT 'Current return processing status' VALUES ('Approved', 'Pending', 'Rejected')
      )
      WITH METRICS (
        "Total Returns" AS COUNT(RETURN_ID) COMMENT 'Total number of returns',
        "Total Refunds" AS SUM(REFUND_AMOUNT) COMMENT 'Sum of all refund amounts in USD',
        "Avg Refund Amount" AS AVG(REFUND_AMOUNT) COMMENT 'Average refund amount per return'
      )
      WITH FILTERS (
        "Approved Returns" AS RETURN_STATUS = 'Approved' COMMENT 'Only approved returns'
      ),

    RETAIL_AI_TEST.ANALYTICS.STORES
      AS STORES
      PRIMARY KEY (STORE_ID)
      WITH COLUMNS (
        STORE_ID AS "Store ID" COMMENT 'Unique store identifier',
        STORE_NAME AS "Store Name" COMMENT 'Display name of the store',
        STORE_TYPE AS "Store Type" COMMENT 'Type of retail store' VALUES ('Flagship', 'Outlet', 'Standard'),
        CITY AS "Store City" COMMENT 'City where the store is located',
        STATE AS "Store State" COMMENT 'US state abbreviation',
        REGION AS "Region" COMMENT 'Geographic region' VALUES ('Northeast', 'West', 'Midwest', 'South'),
        OPENED_DATE AS "Opened Date" COMMENT 'Date the store opened',
        SQUARE_FOOTAGE AS "Square Footage" COMMENT 'Store size in square feet',
        MANAGER_NAME AS "Manager" COMMENT 'Name of the store manager'
      )
      WITH METRICS (
        "Total Stores" AS COUNT(STORE_ID) COMMENT 'Total number of stores'
      )
  )

  RELATIONSHIPS (
    ORDERS (CUSTOMER_ID) REFERENCES CUSTOMERS (CUSTOMER_ID) COMMENT 'Each order belongs to one customer',
    ORDER_ITEMS (ORDER_ID) REFERENCES ORDERS (ORDER_ID) COMMENT 'Each order item belongs to one order',
    ORDER_ITEMS (PRODUCT_ID) REFERENCES PRODUCTS (PRODUCT_ID) COMMENT 'Each order item references one product',
    RETURNS (ORDER_ID) REFERENCES ORDERS (ORDER_ID) COMMENT 'Each return references an order',
    RETURNS (ORDER_ITEM_ID) REFERENCES ORDER_ITEMS (ORDER_ITEM_ID) COMMENT 'Each return references a specific order item'
  );
