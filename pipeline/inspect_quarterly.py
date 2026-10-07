#!/usr/bin/env python3
"""First look at an Iowa Liquor Quarterly PDF: is it text or scanned, how many pages, and what
the price-list rows look like. Run this before writing the parser.

  python3 inspect_quarterly.py data/quarterly_pdfs/iowa_liquor_quarterly_2004_02.pdf [--pages 0-3]
"""
import argparse, re, pdfplumber

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--pages", default="0-2", help="page range to print, e.g. 0-2 or 10-12")
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.pages.split("-"))
    with pdfplumber.open(a.pdf) as pdf:
        n = len(pdf.pages)
        chars = sum(len(p.chars) for p in pdf.pages[: min(n, 5)])
        print(f"{a.pdf}: {n} pages, {chars} text chars in first 5 pages -> {'TEXT' if chars > 200 else 'SCANNED (needs OCR)'}")
        # find pages that look like price lists: many lines starting with an item number
        hits = []
        for i, p in enumerate(pdf.pages):
            txt = p.extract_text() or ""
            k = len(re.findall(r"^\s*\d{4,6}\s+\S", txt, re.M))
            if k >= 10:
                hits.append((i, k))
        print(f"pages with 10+ lines starting with a 4-6 digit code: {len(hits)} (first: {hits[:5]})")
        for i in range(lo, min(hi + 1, n)):
            print(f"\n===== page {i} =====")
            print((pdf.pages[i].extract_text() or "")[:3000])
            tables = pdf.pages[i].extract_tables()
            if tables:
                print(f"-- {len(tables)} table(s) detected; first rows of table 0:")
                for row in tables[0][:8]:
                    print(row)

if __name__ == "__main__":
    main()
