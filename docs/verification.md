# Verification record

Local verification date: 2026-09-29. The generated files in `evaluations/` contain timestamps, test cases, and individual predictions.

## What passed locally

- **Published data:** The normal app contains 777,059 accepted prices from 8 Boston-area hospitals across Mass General Brigham, Beth Israel Lahey Health, and BMC Health System. It contains no fictional prices. Source files are dated March 13–April 1, 2026.
- **Original-file audit:** 253/253 sampled prices matched the hospitals' source CSV or JSON files after the same cent-rounding rule. See `evaluations/live-price-audit.json`. This is a sample, not a full independent audit.
- **Python suite:** 63 tests passed with `pytest -q`, including ingestion, pricing rules, estimator boundaries, local AI guards, Snowflake bootstrap behavior, map marker generation, and Streamlit workflows against the live database. The fictional 20-code catalog remains an isolated development fixture.
- **Lint and formatting:** Ruff checks passed after formatting the latest edits.
- **Snowflake/dbt:** The public snapshot was uploaded to `CARECOST.RAW` on September 29, 2026. The X-Small warehouse has auto-suspend set to 60 seconds. `dbt build` passed all 31 steps (8 models, 22 tests, 1 seed) with zero warnings or errors. Raw and mart price counts both equal the local 777,059; the hospital dimension has 8 rows. A repeatable check matched 24 sampled mart records to local values and source hashes across every hospital and all three price types. See `evaluations/snowflake-deployment.json` and rerun `python scripts/verify_snowflake.py` when credentials are available.
- **Live search benchmark:** On 100 authored development phrases, local BGE/FAISS hybrid search ranked the labeled code first for 63/100 versus 23/100 for simple keyword search. All 100 labeled codes are now present in the expanded catalog. Among 60 phrases that are not aliases, the hybrid scored 23/60. These are development phrases, not a patient study. See `evaluations/live-search-results.json`.
- **Estimator:** 10/10 independently calculated cases passed, plus unit tests for cent rounding and invalid input.
- **Bill rules:** Three planted discrepancy flags were found with zero extra flags on the planted bill and three clean control lines. Structured extraction matched 4/4 expected code, quantity, and charge triples. This is a small fixture, not a real-world sensitivity claim.
- **OCR:** Tesseract 5.5.3 processed generated PNG and scanned-PDF examples with the expected code, date, and charge (`evaluations/ocr-smoke.json`).
- **Local LLM:** A synthetic four-line bill run through installed Mistral 7B matched 4/4 expected code, quantity, and charge triples after the client was revised to recover codes explicitly quoted in evidence. Some dates were omitted. See `evaluations/ollama-smoke.json`.
- **End-to-end bill smoke test:** OCR, the local LLM, and the real MGH price lookup flagged a fabricated $3,600 MRI charge against a published $3,332 gross charge, with source URL, row, and hash (`evaluations/bill-pipeline-smoke.json`).
- **Browser preview:** The localhost Streamlit app rendered the eight-hospital WebGL map with live map tiles. Selecting Massachusetts General Hospital from the map's list focused its location and displayed its address and directions. The Knee MRI comparison showed eight hospitals and direct address/directions links on all eight price cards. Streamlit's AppTest exercised comparison, estimate, bill review, map navigation, and clear-session flows. Marker-click selection itself has not been confirmed.

`constraints-tested.txt` records the installed package versions. Reproduce with `pip install -e '.[dev,semantic,ocr,warehouse]' -c constraints-tested.txt` in a compatible Python environment. The system OCR binary, model weights, and external services still need their own setup.

## What remains unverified

- **Serving path:** The running app still reads the local validated SQLite snapshot. The Snowflake mart is built and tested, but a fresh app-serving SQLite export from that mart was not made because the machine had only 5.8 GiB of free disk space at verification time; a second snapshot could consume several GiB. This does not affect the working local app or cloud warehouse.
- **Real-world study:** No representative OCR/LLM benchmark, clinician review, hosted privacy assessment, load test, or real patient usability study has been conducted.
- **Coverage:** Eight hospitals are still a subset of the Boston market. Source-row auditing is sampled; published prices may describe different service components or omit professional fees.
- **Deployment:** The app is running as a local development preview, not a public production service. The Docker image has not been built here.

Do not use the development-fixture results as claims about patient outcomes, actual savings, regulatory compliance, or typical bill-checker accuracy.
