# User-testing protocol and current status

**Status: not conducted. Participants: 0. Task completion, ratings and decision impact: unmeasured.** This is a protocol and results template, not a completed study.

Recruit 5–8 adult classmates, friends, caregivers or patient advocates. Use the real published-data app for navigation tasks, explain that prices are snapshots rather than quotes, and use a fictional bill for bill-review tasks. Obtain consent to record anonymous observations; allow withdrawal at any time. Do not request real medical records, member IDs or identifiable health information. Assign participant IDs such as P01.

## Tasks

1. Find the lowest published cash price for a knee MRI; explain which service code and setting you selected.
2. Select the published Harvard Pilgrim “HB AMC HPHC PPO” plan where a dollar rate is available. With a $2,000 deductible, $750 already paid and 20% coinsurance, compare your estimated share at two hospitals. Explain one fee the estimate might omit.
3. Review a fabricated MGH bill containing a $3,600 line total for CPT 73721 and compare it with the published gross price. Confirm the extracted fields, identify questions for billing, and explain why a flag is not proof of an error.
4. Find the source date and source row for a displayed price.
5. Clear the uploaded/extracted bill and explain where processing occurred.

Record completion (unassisted, assisted, failed), time in seconds, incorrect selections and confusion points. Do not lead participants toward a correct choice. Record whether they distinguish the fabricated bill from actual published prices, and gross charges from allowed amounts.

Ask 1–5 ratings for ease, confidence in understanding, and perceived usefulness. Separately ask whether verified prices could change where they seek care, with yes/no/unsure options and an optional explanation. Trust ratings should reflect understood limitations, not persuasive design.

## Results template

Use `evaluations/usability-template.json` per participant. Summarize counts and denominators, median task time and assistance rate; report each survey item separately. With small convenience samples, do not generalize to all patients. Include recruitment bias and accessibility limitations.

For each change, record observed problem → implementation → retest result. Suggested accessibility checks: keyboard-only navigation, zoom at 200%, contrast, screen-reader labels, field-level validation, and interpretation of medical terminology.
