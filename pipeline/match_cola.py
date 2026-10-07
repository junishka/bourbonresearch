#!/usr/bin/env python3
"""Match TTB COLA label records to Iowa item numbers.

  python3 match_cola.py --cola cola.csv --items data/item_master.csv --outdir data

Outputs in --outdir:
  cola_products.csv        one row per (permit, brand, fanciful) product with COLA counts and dates
  cola_to_product.csv      COLA id -> product_id
  match_candidates.csv     top candidates per product with coverage, extras and status
  cola_item_crosswalk.csv  accepted product_id -> item_number pairs
  unmapped_permits.csv     permits with no vendor regex in the seed, ranked by COLA count

Decision rule, per candidate pair
  anchored   every brand token is found in the item name (fuzzy, per token), or a 2+ token
             fanciful name is fully found
  covered    the fanciful name, if any, is fully found
  extras     item tokens that no COLA token explains. TRIVIAL extras are ages, proofs,
             numbers and packaging codes. Anything else (SMALL BATCH, SINGLE BARREL, another
             brand's words) blocks an accept.
  accept     anchored and covered and extras trivial and the pair came through the vendor gate
  review     anchored on the brand's core words (same brand, different expression), or a
             fallback or ungated pair that would otherwise accept, or a high fuzzy score
  reject     everything else
"""
import argparse, os, re, sys
import pandas as pd
from rapidfuzz import fuzz, process

STOP = set("""KENTUCKY KY STRAIGHT STR BOURBON BRBN WHISKEY WHISKY WHISKIES BOTTLED BOND BIB THE OF AND
DISTILLERY DISTILLERS DISTILLING DISTILLED CO COMPANY INC LLC LTD BRAND BRANDS LABEL PRODUCTS
SOUR MASH BLEND BLENDED BLENDS HA DNO PET MO""".split())
EXPAND = {"YRS": "YR", "YEAR": "YR", "YEARS": "YR", "YO": "YR",
          "PF": "PROOF", "PRF": "PROOF", "PRO": "PROOF",
          "SGL": "SINGLE", "BBL": "BARREL", "SM": "SMALL", "RSV": "RESERVE", "RES": "RESERVE"}
NUMERIC = re.compile(r"^\d+(YR|PROOF|PRF|PF|ML|L|TH|ND|RD|ST)?$|^PROOF$|^YR$")
TRIVIAL = set("OLD NO".split())   # extras that never change the expression

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

def tok_in(t, toks):
    return any(t == u or (len(t) >= 4 and len(u) >= 4 and fuzz.ratio(t, u) >= 88) for u in toks)

def coverage(src, item_toks):
    src = [t for t in src if t]
    return 1.0 if not src else sum(tok_in(t, item_toks) for t in src) / len(src)

def colkey(c):
    return re.sub(r"[^a-z0-9]+", "_", c.strip().lower()).strip("_")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cola", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--seed", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "permit_vendor_seed.csv"))
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--review", type=float, default=85, help="fuzzy score that forces review even without an anchor")
    ap.add_argument("--topk", type=int, default=6)
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
            pool_cache[permit] = items.index[items["vendor_u"].str.contains(rx, regex=True, na=False)].tolist()
        return pool_cache[permit] or None

    def score_pool(p, idx, gate):
        choices = all_norms if idx is None else [all_norms[i] for i in idx]
        hits = process.extract(p.prod_norm, choices, scorer=fuzz.token_set_ratio, limit=a.topk)
        b_toks = p.brand_norm.split()
        b_core = [t for t in b_toks if not NUMERIC.match(t)]
        f_toks = p.fanciful_norm.split()
        out = []
        for _, s, j in hits:
            it = items.iloc[j if idx is None else idx[j]]
            i_toks = it.item_norm.split()
            b_cov, bc_cov, f_cov = coverage(b_toks, i_toks), coverage(b_core, i_toks), coverage(f_toks, i_toks)
            extras = [t for t in i_toks if not tok_in(t, b_toks + f_toks)]
            num_extras = [t for t in extras if NUMERIC.match(t)]
            word_extras = [t for t in extras if not NUMERIC.match(t) and t not in TRIVIAL]
            anchored = b_cov == 1 or (len(f_toks) >= 2 and f_cov == 1)
            core_anchored = (bc_cov == 1 and b_core) or (len(f_toks) >= 2 and f_cov == 1)
            exact = anchored and f_cov == 1 and not word_extras and not num_extras
            near = anchored and f_cov == 1 and not word_extras and num_extras
            if exact and gate == "vendor":
                st, note = "accept", "exact"
            elif exact:
                st, note = "review", "exact but " + gate
            elif near:
                st, note = "review", "age/proof/year on item: " + " ".join(num_extras)
            elif anchored and f_cov == 1:
                st, note = "review", "extra words: " + " ".join(word_extras)
            elif core_anchored:
                st, note = "review", "fanciful or number not found" if f_cov < 1 or b_cov < 1 else "extra words: " + " ".join(word_extras)
            elif s >= a.review:
                st, note = "review", "fuzzy only"
            else:
                st, note = "reject", ""
            out.append(dict(product_id=p.product_id, permit_no=p.permit_no, brand_name=p.brand_name,
                            fanciful_name=p.fanciful_name, prod_norm=p.prod_norm, n_colas=p.n_colas,
                            item_number=it.item_number, item_description=it.item_description,
                            vendor_name=it.vendor_name, total_bottles=it.total_bottles,
                            first_month=it.get("first_month", ""), last_month=it.get("last_month", ""),
                            score=round(s, 1), brand_cov=round(b_cov, 2), fanciful_cov=round(f_cov, 2),
                            extras=" ".join(extras), gate=gate, status=st, note=note))
        return out

    cands = []
    for p in prods.itertuples():
        if not p.prod_norm:
            continue
        permit = str(p.permit_no).strip().upper()
        idx = pool_for(permit)
        rows = score_pool(p, idx, "vendor" if idx else "none")
        if idx and not any(r["status"] == "accept" for r in rows):
            rows += score_pool(p, None, "fallback")
        cands.extend(rows)
    cand = pd.DataFrame(cands)
    rank = {"accept": 0, "review": 1, "reject": 2}
    cand = cand.assign(r=cand.status.map(rank)).sort_values(["product_id", "r", "score", "total_bottles"],
                                                            ascending=[True, True, False, False]).drop(columns="r")
    cand.to_csv(f"{a.outdir}/match_candidates.csv", index=False)
    xw = cand[cand.status == "accept"][["product_id", "item_number", "score", "gate"]].drop_duplicates(["product_id", "item_number"])
    xw.to_csv(f"{a.outdir}/cola_item_crosswalk.csv", index=False)

    unm = (prods[~prods.permit_no.str.strip().str.upper().isin(vendor_rx)]
           .groupby("permit_no").agg(n_colas=("n_colas", "sum"), n_products=("product_id", "size"),
                                     example_brands=("brand_name", lambda s: "; ".join(list(dict.fromkeys(s))[:4])))
           .sort_values("n_colas", ascending=False).reset_index())
    unm.to_csv(f"{a.outdir}/unmapped_permits.csv", index=False)

    best = cand.drop_duplicates("product_id")
    n_acc, n_rev = (best.status == "accept").sum(), (best.status == "review").sum()
    vol_share = items[items.item_number.isin(set(xw.item_number))].total_bottles.sum() / max(items.total_bottles.sum(), 1)
    print(f"products {len(prods)}  accept {n_acc}  review {n_rev}  no match {len(prods) - n_acc - n_rev}")
    print(f"COLA rows with an accepted item: {cola.product_id.isin(set(xw.product_id)).mean():.1%}   "
          f"Iowa bourbon volume covered: {vol_share:.1%}")
    print(f"permits without vendor mapping: {len(unm)} (see unmapped_permits.csv)")

if __name__ == "__main__":
    main()
