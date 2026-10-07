#!/usr/bin/env python3
"""Match TTB COLA label records to Iowa item numbers.

  python3 match_cola.py --cola sample.csv --items data/item_master.csv \
      --seed permit_vendor_seed.csv --outdir data

Outputs in --outdir:
  cola_products.csv        one row per (permit, brand, fanciful) product with COLA counts and dates
  cola_to_product.csv      COLA id -> product_id
  match_candidates.csv     top candidates per product with score and status (accept/review/reject)
  cola_item_crosswalk.csv  accepted product_id -> item_number pairs (one product, many sizes)
  unmapped_permits.csv     permits with no vendor regex in the seed, ranked by COLA count

Rules. Candidates come from the permit's vendor (seed file) when one is mapped, else from all
items. If the vendor-gated best score is below the accept threshold, all items are also tried and
flagged gate=fallback; those are never auto-accepted. A pair is accepted when the token-set score
clears --accept, the brand (or a 2+ token fanciful name) is found inside the item description, and
the pair came through the vendor gate (or scored 95+). Same brand but a different expression lands
in review so a person decides.
"""
import argparse, os, re, sys
import pandas as pd
from rapidfuzz import fuzz, process

STOP = set("""KENTUCKY STRAIGHT STR BOURBON BRBN WHISKEY WHISKY WHISKIES BOTTLED BOND BIB THE OF
DISTILLERY DISTILLERS DISTILLING DISTILLED CO COMPANY INC LLC LTD BRAND BRANDS LABEL PRODUCTS
SOUR MASH BLEND BLENDED BLENDS""".split())
EXPAND = {"YRS": "YR", "YEAR": "YR", "YEARS": "YR", "YO": "YR",
          "PF": "PROOF", "PRF": "PROOF", "PRO": "PROOF",
          "SGL": "SINGLE", "BBL": "BARREL", "SM": "SMALL", "RSV": "RESERVE", "RES": "RESERVE"}
NUMERIC = re.compile(r"^\d+(YR|PROOF|ML|L)?$|^PROOF$|^YR$")

def norm(s):
    s = str(s or "").upper().replace("&", " AND ").replace("'", "")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    toks = []
    for t in s.split():
        t = EXPAND.get(t, t)
        if t in STOP:
            continue
        if len(t) >= 4 and t.endswith("S") and not t.endswith("SS"):
            t = t[:-1]
        toks.append(t)
    return " ".join(toks)

def anchor_text(s):
    """Brand text without age/proof tokens, used to check the brand sits inside the item name."""
    return " ".join(t for t in s.split() if not NUMERIC.match(t))

def colkey(c):
    return re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cola", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--seed", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "permit_vendor_seed.csv"))
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--accept", type=float, default=90)
    ap.add_argument("--review", type=float, default=75)
    ap.add_argument("--topk", type=int, default=5)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    cola = pd.read_csv(a.cola, dtype=str, keep_default_na=False)
    cola.columns = [colkey(c) for c in cola.columns]
    need = {"id", "permit_no", "brand_name", "fanciful_name", "completed_date"}
    if need - set(cola.columns):
        sys.exit(f"COLA file missing columns {need - set(cola.columns)}; have {list(cola.columns)}")
    for c in ("class_type_desc", "applicant_name"):
        if c not in cola:
            cola[c] = ""
    cola["approval"] = pd.to_datetime(cola["completed_date"], errors="coerce")
    cola["brand_norm"] = cola["brand_name"].map(norm)
    cola["fanciful_norm"] = cola["fanciful_name"].map(norm)
    cola["prod_norm"] = (cola["brand_norm"] + " " + cola["fanciful_norm"]).str.strip()

    key = ["permit_no", "brand_norm", "fanciful_norm"]
    prods = (cola.groupby(key, sort=False)
             .agg(brand_name=("brand_name", "first"), fanciful_name=("fanciful_name", "first"),
                  prod_norm=("prod_norm", "first"), n_colas=("id", "size"),
                  first_approval=("approval", "min"), last_approval=("approval", "max"),
                  class_types=("class_type_desc", lambda s: "|".join(sorted(set(s)))),
                  applicant=("applicant_name", lambda s: next((x for x in s if x), "")))
             .reset_index())
    prods.insert(0, "product_id", [f"P{i:06d}" for i in range(1, len(prods) + 1)])
    cola = cola.merge(prods[key + ["product_id"]], on=key, how="left")
    prods.to_csv(f"{a.outdir}/cola_products.csv", index=False)
    cola[["id", "product_id", "permit_no", "brand_name", "fanciful_name", "completed_date"]].to_csv(
        f"{a.outdir}/cola_to_product.csv", index=False)

    items = pd.read_csv(a.items, dtype={"item_number": str}, keep_default_na=False).reset_index(drop=True)
    items["item_norm"] = items["item_description"].map(norm)
    items["vendor_u"] = items["vendor_name"].astype(str).str.upper()
    items["total_bottles"] = pd.to_numeric(items.get("total_bottles", 0), errors="coerce").fillna(0)
    all_norms = items["item_norm"].tolist()

    seed = (pd.read_csv(a.seed, dtype=str, keep_default_na=False) if os.path.exists(a.seed)
            else pd.DataFrame(columns=["permit_no", "vendor_regex"]))
    vendor_rx = {r.permit_no.strip().upper(): re.compile(r.vendor_regex, re.I)
                 for r in seed.itertuples() if r.vendor_regex}
    pool_cache = {}

    def pool_for(permit):
        rx = vendor_rx.get(permit)
        if rx is None:
            return None
        if permit not in pool_cache:
            idx = items.index[items["vendor_u"].str.contains(rx, regex=True, na=False)].tolist()
            pool_cache[permit] = idx
        return pool_cache[permit] or None

    def score_pool(p, idx, gate):
        choices = all_norms if idx is None else [all_norms[i] for i in idx]
        hits = process.extract(p.prod_norm, choices, scorer=fuzz.token_set_ratio, limit=a.topk)
        b_anchor_txt = anchor_text(p.brand_norm)
        f_anchor_txt = p.fanciful_norm if len(p.fanciful_norm.split()) >= 2 else ""
        out = []
        for _, s, j in hits:
            it = items.iloc[j if idx is None else idx[j]]
            b_anchor = fuzz.partial_ratio(b_anchor_txt, it.item_norm) if b_anchor_txt else 0
            f_anchor = fuzz.partial_ratio(f_anchor_txt, it.item_norm) if f_anchor_txt else 0
            anchored = b_anchor >= 85 or f_anchor >= 95
            item_toks = set(it.item_norm.split())
            fanciful_missing = bool(p.fanciful_norm) and not any(t in item_toks for t in p.fanciful_norm.split())
            if gate == "vendor" and s >= a.accept and anchored and not fanciful_missing:
                st = "accept"
            elif gate == "none" and s >= 95 and anchored and not fanciful_missing:
                st = "accept"
            elif s >= a.review or (b_anchor >= 95 and s >= 60):
                st = "review"
            else:
                st = "reject"
            out.append(dict(product_id=p.product_id, permit_no=p.permit_no, brand_name=p.brand_name,
                            fanciful_name=p.fanciful_name, prod_norm=p.prod_norm, n_colas=p.n_colas,
                            item_number=it.item_number, item_description=it.item_description,
                            vendor_name=it.vendor_name, bottle_volume_ml=it.bottle_volume_ml,
                            total_bottles=it.total_bottles, score=round(s, 1),
                            brand_anchor=round(b_anchor, 1), fanciful_anchor=round(f_anchor, 1),
                            gate=gate, status=st))
        return out

    cands = []
    for p in prods.itertuples():
        if not p.prod_norm:
            continue
        permit = str(p.permit_no).strip().upper()
        idx = pool_for(permit)
        rows = score_pool(p, idx, "vendor" if idx else "none")
        if idx and max((r["score"] for r in rows), default=0) < a.accept:
            rows += score_pool(p, None, "fallback")
        cands.extend(rows)
    cand = pd.DataFrame(cands).sort_values(["product_id", "score"], ascending=[True, False])
    cand.to_csv(f"{a.outdir}/match_candidates.csv", index=False)
    xw = cand[cand.status == "accept"][["product_id", "item_number", "score", "gate"]].drop_duplicates(["product_id", "item_number"])
    xw.to_csv(f"{a.outdir}/cola_item_crosswalk.csv", index=False)

    unm = (prods[~prods.permit_no.str.strip().str.upper().isin(vendor_rx)]
           .groupby("permit_no").agg(n_colas=("n_colas", "sum"), n_products=("product_id", "size"),
                                     example_brands=("brand_name", lambda s: "; ".join(list(dict.fromkeys(s))[:4])))
           .sort_values("n_colas", ascending=False).reset_index())
    unm.to_csv(f"{a.outdir}/unmapped_permits.csv", index=False)

    rank = {"accept": 0, "review": 1, "reject": 2}
    best = cand.assign(r=cand.status.map(rank)).sort_values(["product_id", "r", "score"], ascending=[True, True, False]).drop_duplicates("product_id")
    n_acc, n_rev = (best.status == "accept").sum(), (best.status == "review").sum()
    vol_share = items[items.item_number.isin(set(xw.item_number))].total_bottles.sum() / max(items.total_bottles.sum(), 1)
    print(f"products {len(prods)}  accept {n_acc}  review {n_rev}  no match {len(prods) - n_acc - n_rev}")
    print(f"COLA rows with an accepted item: {cola.product_id.isin(set(xw.product_id)).mean():.1%}   "
          f"Iowa bourbon volume covered: {vol_share:.1%}")
    print(f"permits without vendor mapping: {len(unm)} (see unmapped_permits.csv)")

if __name__ == "__main__":
    main()
