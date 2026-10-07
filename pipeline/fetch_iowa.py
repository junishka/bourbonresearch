#!/usr/bin/env python3
"""Pull bourbon rows from Iowa Liquor Sales (Socrata dataset m3tr-qhgy) to a local CSV.

No account needed. An app token (env SOCRATA_APP_TOKEN) lifts throttling.
Pages month by month so offsets stay small. Resumable: re-running skips months
already present in the output file's companion .done file.

  python3 fetch_iowa.py --since 2012-01 --until 2026-09 --out data/iowa_bourbon_raw.csv
"""
import argparse, csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import date

BASE = "https://data.iowa.gov"
DATASET = "m3tr-qhgy"
PAGE = 50000

# canonical name -> acceptable Socrata display names (lowercased) or field names
CANON = {
    "invoice":            ["invoice/item number", "invoice_line_no"],
    "date":               ["date"],
    "store_number":       ["store number", "store"],
    "store_name":         ["store name", "name"],
    "category":           ["category"],
    "category_name":      ["category name", "category_name"],
    "vendor_number":      ["vendor number", "vendor_no"],
    "vendor_name":        ["vendor name", "vendor_name"],
    "item_number":        ["item number", "itemno"],
    "item_description":   ["item description", "im_desc"],
    "pack":               ["pack"],
    "bottle_volume_ml":   ["bottle volume (ml)", "bottle_volume_ml"],
    "state_bottle_cost":  ["state bottle cost", "state_bottle_cost"],
    "state_bottle_retail":["state bottle retail", "state_bottle_retail"],
    "bottles_sold":       ["bottles sold", "sale_bottles"],
    "sale_dollars":       ["sale (dollars)", "sale_dollars"],
    "volume_sold_liters": ["volume sold (liters)", "sale_liters"],
}

def get(url, token, tries=6):
    req = urllib.request.Request(url, headers={"X-App-Token": token} if token else {})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:  # noqa
            wait = 2 ** i
            print(f"  retry {i+1} after error: {e} (sleep {wait}s)", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("gave up on " + url)

def resolve_fields(token):
    meta = get(f"{BASE}/api/views/{DATASET}.json", token)
    by_disp = {c["name"].strip().lower(): c["fieldName"] for c in meta["columns"]}
    by_field = {c["fieldName"]: c["fieldName"] for c in meta["columns"]}
    out = {}
    for canon, names in CANON.items():
        for n in names:
            f = by_disp.get(n) or by_field.get(n)
            if f:
                out[canon] = f
                break
        if canon not in out:
            raise SystemExit(f"could not resolve column {canon}; dataset columns: {sorted(by_field)}")
    return out

def months(since, until):
    y, m = map(int, since.split("-"))
    uy, um = map(int, until.split("-"))
    while (y, m) <= (uy, um):
        nxt = (y + (m == 12), 1 if m == 12 else m + 1)
        yield f"{y:04d}-{m:02d}", date(y, m, 1).isoformat(), date(*nxt, 1).isoformat()
        y, m = nxt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2012-01")
    ap.add_argument("--until", default=date.today().strftime("%Y-%m"))
    ap.add_argument("--out", default="data/iowa_bourbon_raw.csv")
    ap.add_argument("--where", default="upper(category_name) like '%BOURBON%'",
                    help="SoQL filter on category (field name is substituted from metadata)")
    args = ap.parse_args()
    token = os.environ.get("SOCRATA_APP_TOKEN", "")
    fields = resolve_fields(token)
    where_tpl = args.where.replace("category_name", fields["category_name"])
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    done_path = args.out + ".done"
    done = set(open(done_path).read().split()) if os.path.exists(done_path) else set()
    new_file = not os.path.exists(args.out)
    select = ",".join(f"{f} as {c}" for c, f in fields.items())
    with open(args.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields))
        if new_file:
            w.writeheader()
        for ym, lo, hi in months(args.since, args.until):
            if ym in done:
                continue
            offset, n = 0, 0
            while True:
                q = {"$select": select,
                     "$where": f"{where_tpl} AND {fields['date']} >= '{lo}' AND {fields['date']} < '{hi}'",
                     "$order": fields["invoice"], "$limit": PAGE, "$offset": offset}
                rows = get(f"{BASE}/resource/{DATASET}.json?" + urllib.parse.urlencode(q), token)
                for r in rows:
                    w.writerow({c: r.get(c, "") for c in fields})
                n += len(rows)
                if len(rows) < PAGE:
                    break
                offset += PAGE
            fh.flush()
            with open(done_path, "a") as d:
                d.write(ym + "\n")
            print(f"{ym}: {n} rows", file=sys.stderr)

if __name__ == "__main__":
    main()
