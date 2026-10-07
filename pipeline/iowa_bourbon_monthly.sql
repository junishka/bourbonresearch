-- BigQuery route. Scans the public Iowa table once (~7 GB, inside the free 1 TB/month tier).
-- Run in the BigQuery console or `bq query --use_legacy_sql=false < iowa_bourbon_monthly.sql`
-- and export both result sets to CSV as item_master.csv and item_month.csv.

-- 1. Item master
WITH b AS (
  SELECT *
  FROM `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE UPPER(category_name) LIKE '%BOURBON%'
    AND date >= '2012-01-01'
)
SELECT
  item_number,
  APPROX_TOP_COUNT(item_description, 1)[OFFSET(0)].value AS item_description,
  APPROX_TOP_COUNT(vendor_number, 1)[OFFSET(0)].value   AS vendor_number,
  APPROX_TOP_COUNT(vendor_name, 1)[OFFSET(0)].value     AS vendor_name,
  APPROX_TOP_COUNT(category_name, 1)[OFFSET(0)].value   AS category_name,
  APPROX_TOP_COUNT(bottle_volume_ml, 1)[OFFSET(0)].value AS bottle_volume_ml,
  APPROX_TOP_COUNT(pack, 1)[OFFSET(0)].value            AS pack,
  FORMAT_DATE('%Y-%m', MIN(date)) AS first_month,
  FORMAT_DATE('%Y-%m', MAX(date)) AS last_month,
  COUNT(DISTINCT FORMAT_DATE('%Y-%m', date)) AS n_months,
  SUM(bottles_sold) AS total_bottles
FROM b
GROUP BY item_number;

-- 2. Item by month price panel
WITH b AS (
  SELECT *
  FROM `bigquery-public-data.iowa_liquor_sales.sales`
  WHERE UPPER(category_name) LIKE '%BOURBON%'
    AND date >= '2012-01-01'
)
SELECT
  item_number,
  FORMAT_DATE('%Y-%m', date) AS month,
  APPROX_QUANTILES(state_bottle_retail, 2)[OFFSET(1)] AS price_median,
  MIN(state_bottle_retail) AS price_min,
  MAX(state_bottle_retail) AS price_max,
  APPROX_QUANTILES(state_bottle_cost, 2)[OFFSET(1)]   AS cost_median,
  SUM(bottles_sold)  AS bottles_sold,
  COUNT(*)           AS n_rows,
  COUNT(DISTINCT store_number) AS n_stores
FROM b
GROUP BY item_number, month;
