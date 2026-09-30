# What the published prices show

CareCost currently contains **777,059 accepted prices from eight Boston-area hospitals in three health systems**. All prices come from the hospitals' own published files dated between March 13 and April 1, 2026. See `evaluations/live-data-report.json` for the exact grouped results and source hashes.

For one narrowly matched example, the published cash price for **comprehensive metabolic panel, code 80053**, described as “CHG COMPREHENSIVE METABOLIC PANEL,” spans **$136–$658** at two Beth Israel Lahey Health hospitals. That is a **4.84×** ratio. The group matches code system, code, exact hospital wording, setting, billing class, and modifiers. Matching those fields does not prove every component of the service is identical; ask for a quote before making a decision.

For a **knee MRI, numeric code 73721**, the app shows prices from hospitals that disclose the code as CPT or HCPCS Level I. Published cash entries differ by hospital and sometimes by entry at one hospital. The app shows the original description and fee type beside each amount because billing packages may differ. It does not turn the cheapest disclosed entry into a guaranteed savings claim.

The generated report finds 19,749 groups with prices at two or more hospitals using strict source descriptions and contexts. Its raw highest ratio is from a one-cent drug entry, which is not a meaningful patient savings claim and is excluded from the examples above. A new file refresh can change all results.

An independent source check matched **253/253 sampled rows** to the original files. This verifies transcription of those sampled prices, not clinical comparability or every row in the dataset. The data covers eight hospitals, not the entire Boston market, and it does not include separate fees unless the hospital's source does.
