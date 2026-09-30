# Methodology and limitations

CareCost separates public price data from private bill processing. A price is an observed hospital disclosure, not a binding quote, a measure of quality, or the patient's final obligation.

## Ingestion and lineage

The active app uses eight official hospital files across Mass General Brigham, Beth Israel Lahey Health, and BMC Health System. These include MGB ZIP/CSV files with explicit Windows-1252 decoding, Beth Israel Lahey JSON files, and BMC ZIP/CSV data with an explicit U.S. date format. The parser streams individual records, preserves source URL, file date, SHA-256 and logical record position, and validates before storage. CSV source positions count parsed records (including metadata); JSON positions are one-based indexes into `standard_charge_information`. Embedded newlines in CSV fields mean these are not necessarily physical text line numbers. Publication date is not assumed to be the start of a contract's validity.

Only one unambiguous CPT/HCPCS code, explicit positive dollar values up to the configurable-in-code $1,000,000 ceiling, a care setting, and valid lineage are admitted. The price ceiling is a review heuristic, not a claim that greater prices are impossible. Unsupported coding systems and bundles are quarantined, which reduces coverage. Negotiated amounts disclosed as per diem, case rates, percentages, or other non-fee-schedule methods are also quarantined because they cannot safely be treated as a price for one service. BMC cash and gross amounts can have three decimals and are rounded to cents using half-up rounding. Code shape validation is not a licensed code-set validity check. Patient-facing labels are authored examples; production reference data needs versioning, source/licensing review and clinician review.

Amount, payer/plan, care setting, billing class, modifiers, service identity, publication and source fingerprint all affect row identity. Service identity preserves description and associated codes rather than discarding bundle context. Different descriptions remain distinct in storage. The patient comparison groups five-digit numeric CPT and HCPCS Level I disclosures by code, while showing each hospital’s original code system, wording, class and setting. HCPCS Level II alphanumeric codes remain separate. Identical repeated cash/gross entries in tall files are deduplicated; other variants remain visible under each hospital card. Unknown payer names are whitespace/case normalized, never fuzzy-merged. Unknown billing class is explicitly retained.

The pipeline is a comparison adapter, not a complete CMS compliance validator. It does not assess every mandated field, attestations, organizational NPIs or all conditional requirements. In particular, it does not reinterpret 2026 historical median/percentile allowed amounts as fixed negotiated dollar charges. Refer to the CMS validator for regulatory file validation.

## Search

Default search combines token overlap with manually authored aliases and exact-code matching. Optional BGE embeddings use a local SentenceTransformer and FAISS index. Hybrid scores rank candidates; they are not probabilities. Patients confirm code, contrast, service definition and context. No minimum semantic score has been clinically calibrated; a nearest neighbor can be wrong.

The benchmark is a development fixture: 100 phrases over 20 example procedures, five phrases each, with 40 aliases explicitly overlapping reference data. Full-set and non-alias scores are both reported. A defensible production benchmark needs independent patient-authored phrases, multiple valid answers when appropriate, held-out tuning/evaluation splits and reviewer agreement. The keyword baseline uses procedure descriptions without aliases.

## Cost estimation

Let A be the negotiated allowed amount, D the annual deductible, P the amount already met, and C the coinsurance fraction.

```text
remaining deductible = D - P
deductible share = min(A, remaining deductible)
coinsurance share = (A - deductible share) × C
patient share = deductible share + coinsurance share
```

Inputs require 0 ≤ P ≤ D and 0 ≤ C ≤ 1. Money uses Decimal and cent rounding. A known remaining in-network out-of-pocket maximum caps patient share; deductible and coinsurance components are adjusted to reconcile. This models one covered service. It is not a benefits adjudication engine: copays, family accumulators, embedded deductibles, exclusions, out-of-network care, referrals, authorizations and separate fees are not modeled. Plan selection is not proof of in-network status. Cash purchases may not contribute to insurance accumulators.

## Bill review

A line total is compared to published unit price × confirmed quantity. Users choose gross, agreed cash, or negotiated allowed amounts; the default gross basis avoids equating pre-adjustment charges with patient responsibility. Matching is strict on hospital, setting, billing class, modifiers, and exact payer/plan when relevant. A five-digit numeric CPT code may match a hospital file labeled HCPCS Level I; the original source label remains visible. Alphanumeric HCPCS Level II codes are never merged with CPT. A missing code, missing match, different service variants, a newer publication than service date, or a source older than one year yields an uncertainty flag instead of an overcharge claim.

Potential duplicates require matching code, system, description, quantity, total, date and modifiers. Legitimate repeated services can still trigger a question. Different printed descriptions can hide actual duplicates; the rule deliberately favors explainability. No flagged amount is labeled guaranteed savings or proof of an error. A missing match does not imply the hospital failed to publish a price.

OCR and AI are fallible and can omit rows. Extraction requires evidence strings in source text and schema-valid values, but that cannot establish complete or correct extraction. Patients must confirm all fields and add missing rows before comparison. Plain-language findings are deterministic templates grounded in prices; a language model does not decide whether a charge is excessive.

## Reporting

Price variation groups identical code system/code, care setting, billing class, modifiers and payment type, with payer/plan separated for insured rates. Report min/max and hospital count; retain multiple service variants and audit inclusions before interpreting the spread. Demo multipliers deliberately produce variation and are not evidence about Boston prices.

CMS defines five-digit numeric HCPCS Level I as the CPT code system: [HCPCS overview](https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system).
