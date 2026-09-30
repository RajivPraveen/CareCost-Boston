# Onboarding real hospital files

Start with the hospital's own page and follow its machine-readable standard-charges link. Confirm the legal facility, campuses, publication date, included services and file format. Do not use insurer Transparency in Coverage files as though they were hospital MRFs.

Official starting points checked on 2026-09-29:

- [Mass General Brigham billing overview](https://www.massgeneralbrigham.org/en/patients-visitors/billing-insurance/billing) links CMS-required hospital charge data and distinguishes hospital from professional billing.
- [BMC Health System pricing and estimates](https://www.bmchealthsystem.org/pricing-and-estimates) provides the system's pricing information.
- [CMS format guide and examples](https://github.com/CMSgov/hospital-price-transparency) defines current CSV and JSON structures.

The active manifest `config/boston_sources.json` contains eight direct official MRF links across three health systems. It loads 777,059 accepted public prices. The latest independent source audit checked 253 records with no mismatches. The four newer sources are Beth Israel Deaconess Medical Center, Mount Auburn Hospital, New England Baptist Hospital, and Boston Medical Center. The BMC negotiated-rate adapter excludes per diem, percentage, case-rate and other non-fee-schedule rows from per-service comparisons.

1. Copy `config/sources.example.json` and replace every placeholder. Record a direct HTTPS CSV/JSON URL, local raw-file destination and verified hospital coordinates. Use a separate database from demo data.
2. Download or run `carecost --db data/processed/real.sqlite ingest config/sources.local.json --download`. Single-file ZIP archives are downloaded to `archive_path` and safely streamed into the configured `path`; no archive-controlled filesystem path is used. For GZIP input, unpack it separately under `data/raw/` and retain the original archive and its checksum in your audit log. CMS v2/v3 nested JSON and tall/wide CSV are supported for comparable explicit dollar records.
3. Inspect rejection and duplicate counts; review quarantine reasons. Missing setting, drug units, unsupported code systems and multi-code bundles are intentionally not guessed. Very large rejection counts indicate an adapter/coverage problem, not necessarily a bad hospital disclosure.
4. Check a stratified sample of at least 30 accepted rows per hospital against the exact source bytes: code/system, unit, service description, payer/plan, modifier, setting, class, amount and publication. Include each price type and high/low amounts. Use the stored SHA and row index to locate each source.
5. Have a reviewer verify payer mappings. Do not merge products on fuzzy similarity or brand name alone. A PPO label does not establish that two networks are the same.
6. Record the sample, mismatches and corrections in `evaluations/price-audit.example.json`. Check current versus older snapshots and preserve originals for historical review.
7. Load the dedicated Snowflake schema, run `dbt build`, inspect quarantined records and warnings, then export a new serving snapshot. Confirm the dbt artifact and warehouse target correspond.
8. Only then show real prices; keep dates and source links visible. Document missing hospitals/procedures and the exact coverage denominator.

For legacy/custom files, implement an explicit adapter that emits the canonical Price fields and add a representative fixture plus tests before enabling it. Do not silently rename unknown columns or infer bundled clinical services.

An explicit legacy CSV adapter can be configured in each source entry:

```json
{
  "column_map": {
    "Service Name": "description",
    "CPT Code": "code",
    "Self Pay": "amount"
  },
  "defaults": {
    "code_type": "CPT",
    "setting": "outpatient",
    "billing_class": "facility",
    "price_type": "cash"
  }
}
```

Defaults are permitted only for reviewed code system, setting, billing class, price type and payer/plan context. Never label unknown rows as outpatient or facility merely to pass validation. Dollar amounts, descriptions and codes must be read from the file. The manifest's context is part of the ingestion configuration and should be version controlled with any private credentials removed.
