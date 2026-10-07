# COLA to Iowa price pipeline

Goal. A monthly price panel from 2012 for every bourbon label in the TTB COLA file that is sold in Iowa, with the COLA approval dates attached as label events. Later, extend to 2003 from the Iowa Liquor Quarterly PDFs.

## Access needed

The session that runs this needs one of

- network access to data.iowa.gov (Socrata API, no account), or
- a Google Cloud account to run `iowa_bourbon_monthly.sql` against the public BigQuery table.

In the Claude cloud environment, data.iowa.gov and publications.iowa.gov are denied by the network policy. Add them under Allowed domains in the environment settings, or authorize the BigQuery connector.

## Steps and time

| Step | Command | Time |
|---|---|---|
| 1. Pull bourbon rows 2012 to now | `python3 fetch_iowa.py --out data/iowa_bourbon_raw.csv` | 20 to 60 min via Socrata (about 3 to 4 million rows). Under a minute on BigQuery. |
| 2. Build item master and item by month panel | `python3 build_panel.py --in data/iowa_bourbon_raw.csv --outdir data` | Minutes |
| 3. Match COLA products to items | `python3 match_cola.py --cola cola.csv --items data/item_master.csv --outdir data` | Minutes to run. Then hand review of `match_candidates.csv` rows with status review, and fill `unmapped_permits.csv` into `permit_vendor_seed.csv`. Budget half a day for the full COLA file. |
| 4. Build the product panel | `python3 build_product_panel.py --outdir data` | Seconds |

Total for 2012 onward is one working day, most of it review in step 3. Re-run steps 3 and 4 after each round of review.

## How the merge works

The COLA file has no UPC or size. The join is by name, gated by company.

1. COLA rows collapse to a product keyed on permit, brand name, fanciful name. Each product keeps its COLA ids and approval dates.
2. `permit_vendor_seed.csv` maps a permit (DSP-KY-113) to a regex on the Iowa vendor name (SAZERAC). Candidates are drawn from that vendor's items. Entries are marked `verify`; confirm them against the Iowa vendor list once the data is in.
3. Names are normalized the same way on both sides (drop KENTUCKY, STRAIGHT, BOURBON, WHISKEY, expand YR and PROOF, strip plural S) and scored with a token-set ratio. A pair is accepted when the score clears 90, the brand text sits inside the item description, and the pair came through the vendor gate.
4. Same brand but a different expression (Blanton's Silver Edition vs Blanton's Single Barrel) lands in review. Products whose vendor gate finds nothing are retried against all items and flagged `fallback`, also review only. This catches brands that changed hands.
5. One product maps to several item numbers (sizes, proofs). `panel.csv` keeps item granularity and adds `price_per_750ml` for comparison. `label_events.csv` lists each COLA approval with its product so an event window can be cut around it.

Expect a low match rate by COLA row and a high one by Iowa volume. Private labels (DSP-OH-22, WI-P-4887, DSP-MA-18) never reach Iowa shelves.

## Smoke test

`bash tests/run_fixture.sh` runs the matcher on the 100-row COLA sample against a synthetic item list in `tests/fixture_items.csv`. The fixture imitates Iowa naming and is not real data.

## 2003 to 2011

Iowa Liquor Quarterly PDFs at publications.iowa.gov (records 2789 onward, May 2003) contain the monthly price list. Parse with pdfplumber into the same `item_month.csv` layout. Item numbers should line up with the 2012 data. Budget one to three days depending on how stable the PDF layout is across years; this has not been checked because the host is blocked from this session.
