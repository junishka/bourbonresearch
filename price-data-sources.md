# Longitudinal bourbon price data sources

Two different price series exist for one bottle. Keep them separate.

## Secondary market (auction hammer prices)

Best for allocated and vintage bottles. Lot pages carry fill level, condition, and release year, so they match the covariates already collected.

| Source | Coverage | Access |
|---|---|---|
| Whisky Auctioneer (UK) | Past lots searchable since 2016, hammer price per lot, strong US whiskey section | Site search; third-party scrapers exist (Apify) |
| Unicorn Auctions (US) | Bourbon-focused, monthly auctions since about 2020, pre-Prohibition to current | Past results on site |
| whiskyauction.com (DE) | 2011 onward, used by Lennon and Shohfi (2021) | Site archive |
| Whisky Hammer, Scotch Whisky Auctions, Bonhams, Sotheby's | Fewer bourbon lots, high-end only | Site archives |
| WhiskyStats | Aggregates 2.3M auction prices across houses, publishes a bourbon index built from the 100 most traded bourbons | Subscription |
| Bottle Blue Book, Bourbon Brown Book (Bourbon Culture, annual since 2021), BAXUS | Self-reported or listing prices, not transactions | Free, use as a cross-check only |

Caveats. Auction prices run above peer-to-peer prices. Record buyer's premium, currency, auction house, fill level, and condition per lot. Facebook peer-to-peer groups were shut in 2019 to 2020, so that series ends there.

## Retail (shelf or state price)

| Source | Coverage | Access |
|---|---|---|
| Iowa Liquor Sales | Every state-to-retailer transaction since Jan 2012, daily, with item description, category, bottle volume, state bottle cost, state bottle retail, bottles sold | Free. data.iowa.gov CSV/API, or `bigquery-public-data.iowa_liquor_sales.sales` |
| Other control-state price books (PA, VA, OH, MI, NC, OR, UT, NH) | Monthly or quarterly price lists | State sites; past issues via Wayback Machine |
| NABCA | Brand-level monthly sales and price across 17 control states | Paid, academic access has been granted before |
| NielsenIQ retail scanner data (Kilts Center, Chicago Booth) | Weekly UPC-level price and units from 2006, includes the liquor channel, expanded in 2024 | University subscription. Check whether IESE has one |
| Wine-Searcher Pro | Price history chart per product across listed retailers, spirits included | Subscription, listing prices only |

Caveats. Iowa "state bottle retail" is the state's price to the store, not the shelf price. Control states post allocated bottles at state price, so these series will not show scarcity premia. Scanner data under-covers independent liquor stores.

## Method notes

1. Build a product key before pulling prices. Brand, expression, age, proof, size, release year or batch. Annual releases are distinct products.
2. For auction series use repeat sales or hedonic regression with fill level, house, and premium controls. Precedents are Lennon and Shohfi (2021, J. Econ. Behav. Organ. 191) and "That's the Spirit" (2020, 60k lots from two houses, 2011 to 2020).
3. Keep raw pulls with retrieval date and URL. Check terms of service before scraping; auction houses have supplied data on request for academic use.

## Matching COLA records to a retail price series

The label data is keyed by permit number, brand name, fanciful name, class/type, and approval date. No UPC, no size. So any price source must be joined on names.

Most efficient option is Iowa Liquor Sales. It is free, bulk-downloadable, one table, 2012 to present, and carries vendor name, item description, bottle volume, pack, and state bottle retail. Steps.

1. Filter Iowa to bourbon categories (straight bourbon, bottled in bond, single barrel). Collapse to item number by month using median state bottle retail and bottles sold.
2. Build a permit-to-vendor crosswalk. A few dozen DSP numbers cover most volume (DSP-KY-113 Sazerac, DSP-KY-14 and 230 Beam, KY-I-344 Heaven Hill, DSP-KY-52 Brown-Forman, DSP-KY-67 Wild Turkey, DSP-MO-16 Luxco, DSP-KY-24 Barton).
3. Within vendor, fuzzy-match brand plus fanciful name to item description. Review the top candidates by hand. One COLA brand will map to several Iowa items (sizes, proofs).
4. Collapse COLAs to product by year so the approval date marks a label event on a continuous Iowa item series. Iowa item numbers usually persist across label changes, which is what you want.

What will not match. Private labels for bars and retailers (DSP-OH-22 rows like Leather Stallion Saloon), tiny distilleries, and anything before 2012. Expect the match rate by COLA row to be low and the match rate by sales volume to be high.

If IESE has NielsenIQ via Kilts, use it for a national shelf-price panel with UPCs from 2006. Access takes weeks and the join is still name-based. For 2000 to 2011 the only product-level sources are archived control-state price books, which are PDFs.
