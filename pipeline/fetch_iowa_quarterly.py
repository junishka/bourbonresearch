#!/usr/bin/env python3
"""Download the Iowa Liquor Quarterly PDFs (monthly wholesale price list booklets) from
publications.iowa.gov. Needs network access to that host.

  python3 fetch_iowa_quarterly.py --outdir data/quarterly_pdfs

Discovers record ids from the subject listing (BBA = Alcoholic Beverages Division), keeps the
records whose title starts with "Iowa Liquor Quarterly", and saves each PDF as
iowa_liquor_quarterly_<YYYY>_<MM>.pdf. Re-running skips files already present.
"""
import argparse, os, re, sys, time, urllib.request

BASE = "https://publications.iowa.gov"
LISTING = BASE + "/view/subjects/BBA.html"
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}

def get(url, binary=False, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as r:
                return r.read() if binary else r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"  retry {i+1} on {url}: {e}", file=sys.stderr); time.sleep(2 ** i)
    raise SystemExit("gave up on " + url)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="data/quarterly_pdfs")
    ap.add_argument("--since", type=int, default=2003)
    ap.add_argument("--until", type=int, default=2013)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    html = get(LISTING)
    recs = {}
    for m in re.finditer(r'href="(?:%s)?/(\d+)/?"[^>]*>([^<]*Iowa Liquor Quarterly[^<]*)<' % re.escape(BASE), html):
        rid, title = m.group(1), m.group(2)
        mm = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", title, re.I)
        if mm:
            recs[rid] = (int(mm.group(2)), MONTHS[mm.group(1).lower()])
    if not recs:
        sys.exit("no records found on the listing page; page layout may have changed")
    print(f"{len(recs)} quarterly records found on listing", file=sys.stderr)
    for rid, (y, mo) in sorted(recs.items(), key=lambda kv: kv[1]):
        if not (a.since <= y <= a.until):
            continue
        out = f"{a.outdir}/iowa_liquor_quarterly_{y}_{mo:02d}.pdf"
        if os.path.exists(out):
            continue
        page = get(f"{BASE}/{rid}/")
        pdfs = re.findall(r'href="(%s/%s/\d+/[^"]+\.pdf)"' % (re.escape(BASE), rid), page) or \
               re.findall(r'href="([^"]+\.pdf)"', page)
        if not pdfs:
            print(f"  no pdf link on record {rid} ({y}-{mo:02d})", file=sys.stderr); continue
        url = pdfs[0] if pdfs[0].startswith("http") else BASE + pdfs[0]
        data = get(url, binary=True)
        open(out, "wb").write(data)
        print(f"{y}-{mo:02d} record {rid} {len(data)/1e6:.1f} MB", file=sys.stderr)

if __name__ == "__main__":
    main()
