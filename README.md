<h1 align="center">✳ CareCost</h1>

<p align="center">
  <strong>Know what care may cost. Understand the bill afterward.</strong><br>
  Real hospital prices, explained for people.
</p>

<p align="center">
  <a href="#try-carecost">Try the app</a> ·
  <a href="#what-it-does">What it does</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#what-is-working-today">What is working</a> ·
  <a href="#run-it-yourself">Set up</a>
</p>

---

Hospital price files are public, but they are difficult to search, compare, or connect to a bill. CareCost turns those files into three useful answers: **Where can I go? What might I pay? Does this bill deserve a closer look?**

**8 Boston-area hospitals** · **20,540 procedure codes** · **777,059 published price records** · **3 health systems**

## Try CareCost

From this project folder, run:

~~~sh
./scripts/start.sh
~~~

Open [the local app](http://127.0.0.1:8501/) and try this short path:

1. Open **Hospital map**. Choose a hospital to focus its location, see the address, and open directions.
2. Return to **Compare prices**. Choose **Knee MRI**, then **Paying cash**, to compare prices from the hospitals that publish a matching charge.
3. Open **Where these prices come from** to see the hospital's wording, publication date, and original source.

The link works while CareCost is running on your computer. If you have a fresh checkout without the data yet, open [first-time setup](#run-it-yourself).

<details>
<summary><strong>See one real comparison from this snapshot</strong></summary>

For outpatient cash prices under code **73721** (a knee MRI without contrast), CareCost lists **$2,075.85** at Boston Medical Center, **$2,499.00** at Massachusetts General Hospital, and **$4,222.00** at Mount Auburn Hospital. That is roughly a 2× span in listed prices. The hospitals' descriptions and fee types differ, so these numbers are a starting point for asking what each charge includes, not a promise of savings. Use the app's source panel to inspect each record.

</details>

## What it does

**Before care · Compare.** Search with ordinary words or a billing code. See cash and plan-specific prices, sort by price or distance, and check each hospital's location. CareCost shows the code and the hospital's description so you can confirm you are looking at the right service.

**Before care · Estimate.** Enter your deductible, how much you have already paid toward it, and your coinsurance. CareCost applies those numbers to a published insurance rate and shows an estimated amount you may owe.

**After care · Review.** Upload an itemized bill or enter its lines yourself. Review the extracted codes and charges before CareCost compares them with that hospital's published prices. It highlights possible duplicates, higher charges, and lines with no matching published price.

A flag is **a question to take to the hospital**, not proof of an error. The estimate is **a planning aid**, not a quote.

## How it works

**Public hospital files → cleaned and checked prices → local app → a result linked to its source**

**Your bill → local text reading → your review → possible questions about its charges**

Open a question to see what happens at each step.

<details>
<summary><strong>Where do the prices come from?</strong></summary>

CareCost downloads public price files from eight hospitals in the Mass General Brigham, Beth Israel Lahey Health, and BMC Health systems. The current files were published between March 13 and April 1, 2026 and retrieved September 29, 2026. The [source list](config/boston_sources.json) records the exact file locations and fingerprints.

Hospitals use different file layouts and names for similar fields. CareCost puts the service code, description, hospital, cash or insurance price, plan, and publication date into one consistent format. It sets aside rows with missing codes, invalid amounts, or prices that are not fixed dollar charges. Each displayed price retains the original file and row it came from.

</details>

<details>
<summary><strong>Why is Snowflake involved if the app runs locally?</strong></summary>

Snowflake holds a second, organized copy of the **public hospital data**. dbt checks that prices connect to valid hospitals, services, and plans, and catches missing or duplicate values. This makes the data pipeline easier to inspect and refresh. The current warehouse contains the same 777,059 accepted prices as the local snapshot, and its last build passed all 31 steps.

The app reads a validated local copy for fast clicks. It does not wake the paid warehouse for each search. **Patient bills are never loaded into Snowflake.**

</details>

<details>
<summary><strong>How does “knee MRI” find a billing code?</strong></summary>

CareCost pairs procedure codes with clearer names and common phrases. For less familiar wording, a locally installed search model looks for descriptions with similar meaning. Its search index is prepared once and saved on the computer so normal searches do not rebuild it. The result always shows the code; similar names do not necessarily mean identical care, so confirm the code with your care team.

</details>

<details>
<summary><strong>Try an estimate: $1,000 rate · $300 deductible left · 20% coinsurance. What might you pay?</strong></summary>

CareCost starts with the hospital's published rate for your chosen plan. It applies your remaining deductible first, then your coinsurance to the rest. For a **$1,000** rate, **$300** of deductible remaining, and **20%** coinsurance, the estimate is **$440**: $300 + 20% of $700.

This assumes covered, in-network care. Copays, family deductibles, separate clinician fees, and services outside the listed charge can change the final bill.

</details>

<details>
<summary><strong>What happens to an uploaded bill?</strong></summary>

Local software reads text from the PDF or photo. An optional AI model running through Ollama can help identify each service, code, quantity, and charge. **You check and edit those lines before any comparison.** CareCost does not intentionally save the upload or send its contents to an outside AI provider; bill text remains in the app session until cleared or ended.

On a hosted installation, this processing would happen on that host's server and would need a separate privacy review. Map tiles load from CARTO; directions open Google Maps only when clicked. Neither receives bill text.

</details>

## What is working today

- **Real coverage:** 8 hospitals, 20,540 procedure codes, and 777,059 accepted price records. The normal app does not show fictional demo prices.
- **Source checks:** 253 of 253 sampled prices matched the hospitals' original files. This is a sample audit, not a check of every row.
- **Warehouse checks:** 31 of 31 Snowflake/dbt build steps passed without warnings; 24 further records matched the local snapshot across hospitals and price types.
- **Search benchmark:** The right code ranked first for 63 of 100 authored development phrases, versus 23 for a basic keyword search. These phrases were written for development, not collected from patients.
- **App checks:** 63 automated tests pass. A small test bill's three planted issues were caught without extra flags; real-world bill accuracy has not been measured.

See the [verification record](docs/verification.md), [search results](evaluations/live-search-results.json), and [Snowflake run record](evaluations/snowflake-deployment.json).

## Run it yourself

<details>
<summary><strong>First-time setup · install and load real prices</strong></summary>

Use Python 3.11 or 3.12 from the project folder:

~~~sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,semantic,ocr,warehouse]'
carecost ingest config/boston_sources.json --download
python scripts/download_model.py
streamlit run app.py
~~~

Allow several gigabytes of disk space for the downloaded and processed files. The model step prepares local search once. Tesseract is needed to read image-based bills; a local Ollama model is optional for identifying bill lines. You can enter bill lines manually without either AI tool.

</details>

<details>
<summary><strong>Refresh the public data or run the checks</strong></summary>

~~~sh
./scripts/refresh.sh
pytest -q
python scripts/audit_live_prices.py
~~~

A refresh re-downloads the configured hospital files and rebuilds the local snapshot and search index. If a hospital changes its file URL, update the [source list](config/boston_sources.json).

</details>

<details>
<summary><strong>Rebuild the Snowflake copy</strong></summary>

Copy <code>.env.example</code> to the Git-ignored <code>.env</code> and fill in your own Snowflake account settings locally. The role needs permission to create the CareCost warehouse, database, and schemas. Keep credentials out of Git and chat.

~~~sh
python scripts/deploy_snowflake.py
python scripts/verify_snowflake.py
~~~

The X-Small warehouse auto-suspends after 60 seconds. Only public prices are uploaded. The app continues to use its local price snapshot.

</details>

## Know the limits

CareCost covers eight hospitals, not every option around Boston. A shared billing code can still describe different service components or fee types. Published prices may change, and an actual bill may include doctor, anesthesia, or other charges not in the displayed price. Bill photos can be misread. There has been no real-patient usability study or clinical validation yet. CareCost does not provide medical or legal advice.

For more detail, read the [methodology](docs/methodology.md), [privacy statement](docs/privacy.md), [data dictionary](docs/data-dictionary.md), [price variation report](docs/price-variation.md), and [user-testing plan](docs/user-testing.md).

<details>
<summary><strong>Find the code and original data sources</strong></summary>

- [Patient-facing app](app.py) and [visual style](assets/style.css)
- [Hospital file reader](carecost/ingestion.py), [search](carecost/search.py), [estimate](carecost/estimator.py), and [bill review](carecost/bills.py)
- [Snowflake loader](carecost/warehouse.py), [warehouse models](dbt/models/), and [tests](tests/)
- [Mass General Brigham price files](https://www.massgeneralbrigham.org/en/patients-visitors/billing-insurance/billing/cms-required-hospital-charge-data)
- [Beth Israel Lahey Health price files](https://bilh.org/billing-financial-services/price-transparency)
- [BMC Health System pricing](https://www.bmchealthsystem.org/pricing-and-estimates)
- [CMS procedure-code guide](https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system)

</details>
