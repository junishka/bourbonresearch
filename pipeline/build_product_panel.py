#!/usr/bin/env python3
"""Join the accepted crosswalk to the Iowa monthly panel and emit analysis files.

  python3 build_product_panel.py --outdir data

Reads item_month.csv, item_master.csv, cola_item_crosswalk.csv, cola_products.csv,
cola_to_product.csv from --outdir. Writes:
  panel.csv         product_id x item_number x month with price and volume
  label_events.csv  one row per COLA approval with its product_id (for event windows)
"""
import argparse, pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data", help="where the match outputs live and the panel is written")
    ap.add_argument("--datadir", default=None, help="where item_month.csv and item_master.csv live (default: outdir)")
    a = ap.parse_args()
    d = a.outdir
    dd = a.datadir or d
    im = pd.read_csv(f"{dd}/item_month.csv", dtype={"item_number": str})
    master = pd.read_csv(f"{dd}/item_master.csv", dtype={"item_number": str})
    xw = pd.read_csv(f"{d}/cola_item_crosswalk.csv", dtype={"item_number": str})
    prods = pd.read_csv(f"{d}/cola_products.csv")
    c2p = pd.read_csv(f"{d}/cola_to_product.csv")

    panel = (xw.merge(im, on="item_number")
               .merge(master[["item_number", "item_description", "vendor_name", "bottle_volume_ml", "pack"]], on="item_number")
               .merge(prods[["product_id", "permit_no", "brand_name", "fanciful_name"]], on="product_id"))
    panel["price_per_750ml"] = panel["state_bottle_retail_median"] * 750 / panel["bottle_volume_ml"].replace(0, pd.NA)
    panel = panel.sort_values(["product_id", "item_number", "month"])
    panel.to_csv(f"{d}/panel.csv", index=False)

    ev = c2p.merge(xw[["product_id"]].drop_duplicates(), on="product_id")
    ev["approval"] = pd.to_datetime(ev["completed_date"], errors="coerce")
    ev["approval_month"] = ev["approval"].dt.strftime("%Y-%m")
    ev.to_csv(f"{d}/label_events.csv", index=False)
    print(f"panel rows {len(panel):,}  products {panel.product_id.nunique()}  items {panel.item_number.nunique()}  "
          f"months {panel.month.min()}..{panel.month.max()}  label events on matched products {len(ev):,}")

if __name__ == "__main__":
    main()
