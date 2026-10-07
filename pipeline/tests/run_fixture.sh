#!/usr/bin/env bash
# Smoke test: COLA sample x synthetic Iowa-style item list. Not real Iowa data.
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-/tmp/bourbon_fixture_out}
cola=${2:-$here/cola_sample.csv}
mkdir -p "$out"
cp "$here/fixture_items.csv" "$out/item_master.csv"
python3 - "$out" <<'PY'
import sys, pandas as pd, random
out = sys.argv[1]; random.seed(1)
m = pd.read_csv(f"{out}/item_master.csv", dtype={"item_number": str})
rows = []
for it in m.itertuples():
    base = random.uniform(10, 40)
    for y in range(2012, 2014):
        for mo in range(1, 13):
            rows.append(dict(item_number=it.item_number, month=f"{y}-{mo:02d}", price_median=round(base * (1 + 0.02 * (y - 2012)), 2),
                             price_min=base, price_max=base, cost_median=round(base / 1.5, 2), bottles_sold=100, n_rows=10, n_stores=8))
pd.DataFrame(rows).to_csv(f"{out}/item_month.csv", index=False)
PY
python3 "$here/../match_cola.py" --cola "$cola" --items "$out/item_master.csv" --outdir "$out"
python3 "$here/../build_product_panel.py" --outdir "$out"
