#!/usr/bin/env python3
"""Build item_master.csv and item_month.csv from Iowa rows with DuckDB.

Input is either the CSV written by fetch_iowa.py or the full bulk CSV from
data.iowa.gov (display-name headers). Both header styles are handled.

  python3 build_panel.py --in data/iowa_bourbon_raw.csv --outdir data
"""
import argparse, os, duckdb

RENAME = {  # display name -> canonical
    "Invoice/Item Number": "invoice", "Date": "date", "Store Number": "store_number",
    "Store Name": "store_name", "Category": "category", "Category Name": "category_name",
    "Vendor Number": "vendor_number", "Vendor Name": "vendor_name", "Item Number": "item_number",
    "Item Description": "item_description", "Pack": "pack", "Bottle Volume (ml)": "bottle_volume_ml",
    "State Bottle Cost": "state_bottle_cost", "State Bottle Retail": "state_bottle_retail",
    "Bottles Sold": "bottles_sold", "Sale (Dollars)": "sale_dollars",
    "Volume Sold (Liters)": "volume_sold_liters",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--since", default="2012-01-01")
    ap.add_argument("--category-like", default="%BOURBON%")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    con = duckdb.connect()
    cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{args.inp}', sample_size=200000)").fetchall()]
    sel = ", ".join(f'"{c}" AS {RENAME.get(c, c)}' for c in cols)
    con.execute(f"""
        CREATE TABLE raw AS
        SELECT {sel} FROM read_csv_auto('{args.inp}', sample_size=200000, all_varchar=true)
    """)
    con.execute(f"""
        CREATE TABLE b AS
        SELECT CAST(item_number AS VARCHAR) AS item_number,
               item_description, vendor_number, vendor_name, category_name,
               TRY_CAST(bottle_volume_ml AS INTEGER) AS bottle_volume_ml,
               TRY_CAST(pack AS INTEGER) AS pack,
               TRY_CAST(date AS DATE) AS date,
               TRY_CAST(state_bottle_cost AS DOUBLE) AS cost,
               TRY_CAST(state_bottle_retail AS DOUBLE) AS price,
               TRY_CAST(bottles_sold AS INTEGER) AS bottles_sold,
               store_number
        FROM raw
        WHERE upper(category_name) LIKE '{args.category_like}'
          AND TRY_CAST(date AS DATE) >= DATE '{args.since}'
    """)
    con.execute(f"""
        COPY (
          SELECT item_number,
                 mode(item_description) AS item_description,
                 mode(vendor_number) AS vendor_number,
                 arg_max(vendor_name, date) AS vendor_name,
                 arg_max(category_name, date) AS category_name,
                 mode(bottle_volume_ml) AS bottle_volume_ml,
                 mode(pack) AS pack,
                 strftime(min(date), '%Y-%m') AS first_month,
                 strftime(max(date), '%Y-%m') AS last_month,
                 count(DISTINCT strftime(date, '%Y-%m')) AS n_months,
                 sum(bottles_sold) AS total_bottles
          FROM b GROUP BY item_number ORDER BY total_bottles DESC
        ) TO '{args.outdir}/item_master.csv' (HEADER)
    """)
    con.execute(f"""
        COPY (
          SELECT item_number, strftime(date, '%Y-%m') AS month,
                 median(price) AS price_median, min(price) AS price_min, max(price) AS price_max,
                 median(cost) AS cost_median,
                 sum(bottles_sold) AS bottles_sold, count(*) AS n_rows,
                 count(DISTINCT store_number) AS n_stores
          FROM b GROUP BY 1, 2 ORDER BY 1, 2
        ) TO '{args.outdir}/item_month.csv' (HEADER)
    """)
    n_items, n_rows = con.execute("SELECT count(DISTINCT item_number), count(*) FROM b").fetchone()
    print(f"bourbon rows {n_rows:,}  distinct items {n_items:,}  -> {args.outdir}/item_master.csv, item_month.csv")

if __name__ == "__main__":
    main()
