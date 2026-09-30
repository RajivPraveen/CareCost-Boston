from __future__ import annotations

import html
import json
import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import streamlit as st

from carecost.bills import check_bill, extract_structured_text, extract_with_ollama, read_document
from carecost.estimator import estimate_cost
from carecost.mapview import comparison_map, hospital_map_points, map_points
from carecost.models import BillLine
from carecost.repository import Repository, distance_miles, load_public_overview
from carecost.search import ProcedureSearch, load_search_catalog

st.set_page_config(page_title="CareCost · Understand your care costs", page_icon="✳️", layout="wide")
st.markdown(f"<style>{Path('assets/style.css').read_text()}</style>", unsafe_allow_html=True)

DB = os.getenv("CARECOST_DB", "data/processed/boston.sqlite")
if not Path(DB).exists():
    st.title("Welcome to CareCost")
    st.write("Compare hospital prices, estimate your share, and review an itemized bill.")
    st.info(
        "Load published price files for eight Boston-area hospitals. The download is about 115 MB and may take a few minutes."
    )
    if st.button("Load published hospital prices", type="primary"):
        from carecost.cli import load_manifest

        with st.spinner("Downloading and validating hospital price files…"):
            try:
                load_manifest("config/boston_sources.json", DB, download=True)
            except Exception:
                st.error(
                    "The hospital refresh could not finish. Check the source URLs or run the ingestion command in the README for details."
                )
                st.stop()
        st.rerun()
    st.stop()


@st.cache_data(show_spinner=False, ttl=300)
def public_overview(database, snapshot_stamp):
    return load_public_overview(database, snapshot_stamp)


@st.cache_data(show_spinner=False, ttl=300)
def bill_defaults(database, snapshot_stamp, hospital_id, basis):
    with Repository(database) as repo:
        billing_class = repo.connection.execute(
            "SELECT billing_class, COUNT(*) n FROM prices WHERE hospital_id=? AND price_type=? "
            "GROUP BY billing_class ORDER BY n DESC LIMIT 1",
            (hospital_id, basis),
        ).fetchone()
        setting = repo.connection.execute(
            "SELECT setting, COUNT(*) n FROM prices WHERE hospital_id=? AND price_type=? "
            "GROUP BY setting ORDER BY n DESC LIMIT 1",
            (hospital_id, basis),
        ).fetchone()
    return billing_class[0] if billing_class else "unknown", setting[0] if setting else "both"


@st.cache_resource(show_spinner=False)
def search_engine(database, snapshot_stamp, model):
    catalog = load_search_catalog(database, snapshot_stamp)
    return ProcedureSearch(catalog, model_path=model)


snapshot_stamp = tuple(
    (Path(p).stat().st_mtime_ns, Path(p).stat().st_size) for p in [DB, DB + "-wal"] if Path(p).exists()
)
with st.spinner("Loading the published procedure catalog…"):
    stats, hospitals = public_overview(DB, snapshot_stamp)

if not stats["prices"]:
    st.error("The selected database has no validated prices. Run carecost demo or ingest a source manifest.")
    st.stop()

if stats["demo_prices"]:
    st.warning("DEMO · All hospitals and prices below are fictional. Do not use them to plan real care.")

st.markdown(
    '<div class="brand-bar"><div class="brand"><span class="brand-symbol">✳</span>CareCost</div>'
    '<span class="brand-note">A little clarity. A better plan.</span></div>',
    unsafe_allow_html=True,
)
with st.container(key="navigation"):
    page = st.radio(
        "Explore",
        ["Compare prices", "Hospital map", "Estimate my cost", "Check my bill", "Data & methodology"],
        format_func=lambda x: "About the prices" if x == "Data & methodology" else x,
        label_visibility="collapsed",
        horizontal=True,
        key="navigation_page",
    )


def footer():
    coverage = (
        "Fictional demo prices — do not use to plan care."
        if stats["demo_prices"]
        else f"{stats['hospitals']} Boston-area hospitals · {len({h['health_system'] for h in hospitals.values()})} health systems · Latest published file: {stats['latest']}"
    )
    st.markdown(
        f'<div class="footnote">{coverage}<br>Prices are estimates, not guarantees. Confirm the full cost with the hospital before booking.</div>',
        unsafe_allow_html=True,
    )


def step(number, title):
    st.markdown(f'<div class="step-label">{number:02d} / {title}</div>', unsafe_allow_html=True)


def set_query(query):
    st.session_state["service_query"] = query


def plans():
    with Repository(DB) as repo:
        return [
            tuple(r)
            for r in repo.connection.execute(
                "SELECT DISTINCT payer,plan FROM prices WHERE price_type='negotiated' ORDER BY payer,plan"
            )
        ]


def choose_service():
    estimating = page == "Estimate my cost"
    st.markdown('<div class="hero-tag">Plan your care</div>', unsafe_allow_html=True)
    st.title("What could you pay?" if estimating else "Find care. Know the cost.")
    st.markdown(
        '<p class="intro">See what you might pay after insurance, using your plan’s deductible and coinsurance.</p>'
        if estimating
        else '<p class="intro">Compare hospital prices around Boston. Start with the care you need.</p>',
        unsafe_allow_html=True,
    )
    step(1, "Find your service")
    query = st.text_input(
        "What care are you looking for?",
        key="service_query",
        placeholder="Try knee MRI, colonoscopy, or a billing code",
    )
    if not query.strip():
        st.caption("Want to find a hospital first? Open **Hospital map** above.")
        st.caption("Try a common search")
        examples = st.columns(3)
        for column, phrase in zip(examples, ["Knee MRI", "Colonoscopy", "Blood test"]):
            column.button(phrase, on_click=set_query, args=(phrase,), width="stretch")
        st.markdown(
            '<div class="guide">'
            '<div><div class="guide-num">01</div><strong>Find your service</strong><p>Use everyday words or the billing code from your doctor.</p></div>'
            '<div><div class="guide-num">02</div><strong>Choose how to pay</strong><p>See cash prices or select your insurance plan.</p></div>'
            '<div><div class="guide-num">03</div><strong>Compare hospitals</strong><p>See prices side by side, then confirm the details before booking.</p></div>'
            "</div>",
            unsafe_allow_html=True,
        )
        footer()
        st.stop()
    model_path = (
        os.getenv(
            "CARECOST_EMBEDDING_MODEL",
            "data/models/bge-small-en-v1.5" if Path("data/models/bge-small-en-v1.5").is_dir() else "",
        )
        or None
    )

    basic_engine = search_engine(DB, snapshot_stamp, None)
    results = basic_engine.search(query)
    # Exact codes and known everyday aliases do not need to load the AI model.
    if not results or results[0]["score"] < 10:
        try:
            with st.spinner("Preparing local search…"):
                engine = search_engine(DB, snapshot_stamp, model_path)
            results = engine.search(query)
        except (ImportError, ValueError, OSError):
            st.caption("Search is running in basic mode. Try an exact service name or billing code.")
    # CMS HCPCS Level I is the numeric CPT code set. Hospitals label it either way.
    # Keep each source's original code system in price records and provenance.
    seen_codes = set()
    distinct_results = []
    for item in results:
        key = item["code"] if item["code"].isdigit() else (item["code_type"], item["code"])
        if key not in seen_codes:
            seen_codes.add(key)
            distinct_results.append(item)
    results = distinct_results
    if not results:
        st.info("No match found. Try a shorter phrase or ask your care team for the exact billing code.")
        st.stop()
    chosen = st.selectbox(
        "Choose the matching service",
        range(len(results)),
        format_func=lambda i: f"{results[i].get('name', results[i]['description'])} · {results[i]['code']}",
    )
    procedure = results[chosen]
    with Repository(DB) as repo:
        filters = {"code": procedure["code"]}
        if not procedure["code"].isdigit():
            filters["code_type"] = procedure["code_type"]
        all_prices = repo.query(**filters)
    with st.expander("Service details · check these before booking"):
        st.caption(
            f"Billing code: {procedure['code']}. Hospitals may call five-digit numeric codes CPT or HCPCS Level I. Similar names can mean different services; confirm this code with your care team."
        )
        st.caption(
            "Hospital descriptions can differ even for the same code. Each card shows the hospital's wording and fee type."
        )
        visit = st.selectbox("Type of visit", ["Outpatient / same day", "Inpatient / admitted"])
        fee_type = st.selectbox("Type of fee", ["Hospital or unspecified fees", "Clinician fees"])
        modifiers = sorted({p.modifiers for p in all_prices})
        modifier = st.selectbox("Extra billing modifier", modifiers, format_func=lambda x: x or "None")
        st.caption(
            "A 'both' setting in the hospital file can apply to inpatient or outpatient care. Confirm which fees are included."
        )
    expected_setting = "outpatient" if visit.startswith("Outpatient") else "inpatient"
    allowed_classes = {"facility", "unknown", "both"} if fee_type.startswith("Hospital") else {"professional"}
    prices = [
        p
        for p in all_prices
        if p.setting in {expected_setting, "both"}
        and p.billing_class in allowed_classes
        and p.modifiers == modifier
    ]
    st.caption(
        f"Showing {visit.lower()} prices with {fee_type.lower()}. Confirm the included fees with each hospital."
    )
    return procedure, prices


def show_sources(prices):
    with st.expander("Where these prices come from"):
        for p in prices:
            st.write(
                f"**{hospitals[p.hospital_id]['name']}** · {p.description} · {p.price_type} · ${p.amount:,.2f}"
            )
            st.caption(f"Published {p.source_date} · source row {p.source_row} · SHA-256 {p.source_sha256}")
            if p.is_demo:
                st.caption(f"Synthetic fixture: {p.source_url}")
            elif p.source_url.startswith("https://"):
                st.link_button("Hospital source file", p.source_url)
            if p.notes:
                st.text(p.notes[:1500])


if page in {"Compare prices", "Estimate my cost"}:
    procedure, prices = choose_service()
    step(2, "Choose how to pay")
    available_plans = sorted({(p.payer, p.plan) for p in prices if p.price_type == "negotiated"})
    payment_method = st.radio(
        "How will you pay?",
        ["Paying cash", "Using insurance"],
        index=1 if page == "Estimate my cost" else 0,
        horizontal=True,
    )
    payment = None
    if payment_method == "Using insurance":
        if not available_plans:
            st.info(
                "No insurance prices are available for this service. Choose paying cash to see cash prices."
            )
            footer()
            st.stop()
        left, right = st.columns(2)
        insurer = left.selectbox(
            "Insurance company", sorted({x[0] for x in available_plans}), format_func=str.title
        )
        payment = right.selectbox(
            "Your exact plan",
            [x for x in available_plans if x[0] == insurer],
            format_func=lambda x: x[1].upper(),
            help="Plan names come from the hospital file. Ask your insurer if you are unsure which is yours.",
        )
        st.caption("Choose your exact plan. The same insurer can have different prices for different plans.")
    selected = [
        p
        for p in prices
        if p.price_type == ("cash" if payment is None else "negotiated")
        and (payment is None or (p.payer, p.plan) == payment)
    ]
    estimating = page == "Estimate my cost"
    annual = paid = 0.0
    coins = 20.0
    oop_remaining = None
    if estimating:
        st.subheader("A few details from your insurance plan")
        if payment is None:
            st.info("Select an insurance plan above to estimate cost sharing. Cash prices are shown below.")
        else:
            a, b, c = st.columns(3)
            annual = a.number_input(
                "Annual deductible ($)",
                min_value=0.0,
                value=2000.0,
                step=100.0,
                help="The amount your plan asks you to pay each year before it starts sharing these costs.",
            )
            paid = b.number_input(
                "Deductible already paid ($)",
                min_value=0.0,
                value=750.0,
                step=50.0,
                help="How much of your deductible you have met so far this year. Find this in your insurer’s app.",
            )
            coins = c.number_input(
                "Your coinsurance (%)",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=1.0,
                help="The percentage you pay after meeting your deductible. For example, enter 20 if your plan pays 80%.",
            )
            if st.checkbox("I know my remaining in-network out-of-pocket maximum"):
                oop_remaining = st.number_input(
                    "Remaining out-of-pocket maximum ($)", min_value=0.0, value=5000.0, step=100.0
                )
            if paid > annual:
                st.error("Deductible already paid cannot exceed the annual deductible.")
                st.stop()
            st.caption(
                "Assumes a covered, in-network service subject to the deductible and coinsurance. Confirm network status with your insurer. Copays, family deductibles, excluded care, and separate clinician fees are not modeled."
            )
    if not selected:
        st.info(
            "No comparable fixed-dollar prices are available for this selection. Try another plan or ask the hospital for a quote."
        )
        st.stop()
    step(3, "Compare your options")
    sorting, location = st.columns(2)
    sort = sorting.selectbox(
        "Sort results", ["Lowest estimated cost" if estimating else "Lowest published price", "Nearest to me"]
    )
    locations = {
        "Downtown Boston": (42.3601, -71.0589),
        "Cambridge": (42.3736, -71.1097),
        "Somerville": (42.3876, -71.0995),
        "Brookline": (42.3318, -71.1212),
        "Newton": (42.337, -71.2092),
    }
    area = location.selectbox("Near", list(locations))
    lat, lon = locations[area]
    rows = []
    for p in selected:
        h = hospitals[p.hospital_id]
        estimate = (
            estimate_cost(p.amount, annual, paid, coins / 100, oop_remaining)
            if estimating and payment
            else None
        )
        rows.append(
            {
                "price": p,
                "hospital": h,
                "distance": distance_miles(lat, lon, h["latitude"], h["longitude"]),
                "display": estimate.patient_total if estimate else p.amount,
                "estimate": estimate,
            }
        )
    rows.sort(key=lambda r: r["distance"] if sort == "Nearest to me" else r["display"])
    hospital_rows = {}
    for row in rows:
        hospital_rows.setdefault(row["price"].hospital_id, []).append(row)
    a, b = st.columns(2)
    a.metric("Hospitals to compare", len(hospital_rows))
    b.metric(
        "Estimated you pay, from" if estimating and payment else "Published prices, from",
        f"${min(r['display'] for r in rows):,.2f}",
    )
    st.caption(
        "Estimated costs for a covered, in-network service."
        if estimating and payment
        else "These are hospital rates, not your final bill. "
        + (
            "Cash payments may not count toward your deductible."
            if payment is None
            else "Choose Estimate my cost to see your share after insurance."
        )
    )
    points = map_points(rows)
    st.markdown("#### Hospitals on the map")
    st.caption(
        "Green markers show hospitals with matching prices. Use the address link under a hospital card for directions. The dark marker is your selected starting area."
    )
    event = st.pydeck_chart(
        comparison_map(points, (lat, lon)),
        key="comparison_map",
        on_select="rerun",
        selection_mode="single-object",
        height=380,
    )
    picked = event.selection.objects.get("hospitals", [])
    if picked:
        selected_point = picked[0]
        st.markdown(
            f"**{selected_point['name']}** · {selected_point['price']} · {selected_point['distance']}"
        )
        st.caption(selected_point["address"])
        st.link_button(
            "Get directions",
            f"https://www.google.com/maps/dir/?api=1&destination={quote(selected_point['address'])}",
        )
    st.caption(
        "Map tiles load from CARTO; opening directions goes to Google Maps. Neither receives bill content. Distances are straight-line estimates."
    )
    for variants in hospital_rows.values():
        row = min(variants, key=lambda r: r["display"])
        p, h = row["price"], row["hospital"]
        label = (
            "Estimated you pay"
            if row["estimate"]
            else "Published cash price"
            if payment is None
            else "Insurance rate · before your share"
        )
        lowest = row["display"] == min(r["display"] for r in rows)
        badge = '<span class="pill">LOWEST LISTED</span>' if lowest else ""
        highest = max(r["display"] for r in variants)
        range_note = f"From {label.lower()} · up to ${highest:,.2f}" if highest > row["display"] else label
        st.markdown(
            f'<div class="hospital-card {"lowest" if lowest else ""}"><div>{badge}'
            f'<h3>{html.escape(h["name"])}</h3><div class="subtle">{html.escape(p.description)} · {html.escape(p.billing_class)} fee</div><div class="subtle">{html.escape(h["city"])} · {row["distance"]:.1f} miles from {html.escape(area)}</div>'
            f'</div><div class="card-amount"><div class="price">${row["display"]:,.2f}</div><div class="subtle">{range_note}</div></div></div>',
            unsafe_allow_html=True,
        )
        if h.get("address") and not p.is_demo:
            st.link_button(
                f"{h['address']} · directions ↗",
                f"https://www.google.com/maps/dir/?api=1&destination={quote(h['address'])}",
            )
        if len(variants) > 1:
            with st.expander(f"{len(variants)} published entries at {h['name']}"):
                st.caption(
                    "Same billing code, but setting or service wording may differ. Check the matching entry with the hospital."
                )
                for variant in sorted(variants, key=lambda r: r["display"]):
                    item = variant["price"]
                    st.write(
                        f"${variant['display']:,.2f} · {item.description} · {item.setting} · {item.billing_class} fee · {item.code_type} {item.code}"
                    )
        if row["estimate"]:
            e = row["estimate"]
            st.caption(
                f"Allowed rate ${e.allowed_amount:,.2f} = your deductible ${e.deductible_portion:,.2f} + your coinsurance ${e.coinsurance_portion:,.2f} + plan share ${e.plan_total:,.2f}."
            )
            cash = [
                x.amount
                for x in prices
                if x.hospital_id == p.hospital_id and x.price_type == "cash" and x.service_id == p.service_id
            ]
            if cash:
                st.caption(
                    f"Published cash option: ${min(cash):,.2f}. Cash payments may not count toward insurance deductibles or out-of-pocket limits. Confirm eligibility and included services."
                )
    show_sources(selected)
    with st.expander("What should I ask before booking?"):
        st.write(
            "1. Is this the exact service and billing code I need?\n2. Does the price include hospital, doctor, anesthesia, and lab fees?\n3. Is this hospital in my plan’s network?"
        )
        st.caption(
            "Prices may cover different packages. Multiple entries at one hospital remain available under its card. Distance is straight-line, not driving time. Price does not measure quality."
        )
    footer()

elif page == "Hospital map":
    st.markdown('<div class="hero-tag">Explore nearby care</div>', unsafe_allow_html=True)
    st.title("Find a hospital.")
    st.markdown(
        '<p class="intro">Explore the Boston-area hospitals in CareCost. Choose one to see its address and open directions.</p>',
        unsafe_allow_html=True,
    )
    points = hospital_map_points(hospitals)
    if not points:
        st.info("No hospital locations are available in this price snapshot.")
        st.stop()
    options = ["all", *[point["hospital_id"] for point in points]]
    focused_id = st.selectbox(
        "Find a hospital",
        options,
        format_func=lambda hospital_id: (
            f"All {len(points)} hospitals" if hospital_id == "all" else hospitals[hospital_id]["name"]
        ),
    )
    st.caption(
        "Choose a hospital to focus its location. Drag to move the map or scroll to zoom. The map does not show travel times."
    )
    event = st.pydeck_chart(
        comparison_map(points, focused_hospital=None if focused_id == "all" else focused_id),
        key="hospital_directory_map",
        on_select="rerun",
        selection_mode="single-object",
        height=510,
    )
    picked = event.selection.objects.get("hospitals", [])
    selected_id = picked[0]["hospital_id"] if picked else focused_id
    if selected_id != "all":
        hospital = hospitals[selected_id]
        st.markdown(f"### {html.escape(hospital['name'])}")
        st.write(hospital.get("address") or "Address not available in this snapshot")
        st.caption(f"{hospital['city']} · {hospital['health_system']}")
        if hospital.get("address") and not stats["demo_prices"]:
            st.link_button(
                "Open directions",
                f"https://www.google.com/maps/dir/?api=1&destination={quote(hospital['address'])}",
            )
    else:
        st.caption("Select a hospital above to see its exact address and directions.")
    st.caption(
        "Map tiles load from CARTO. Directions open Google Maps only when clicked. Neither receives bill content."
    )
    footer()

elif page == "Check my bill":
    st.markdown('<div class="hero-tag">After your visit</div>', unsafe_allow_html=True)
    st.title("Make sense of your bill.")
    st.markdown(
        '<p class="intro">Upload an itemized bill. Check the details, then see which charges to ask the hospital about.</p>',
        unsafe_allow_html=True,
    )
    st.caption("Private by design · Processed on the computer running CareCost · No outside AI service")
    with st.expander("How your bill stays private"):
        st.write(
            "Your bill is processed on the machine running CareCost. If this app is hosted, that means the host server. CareCost does not intentionally save uploads. Text stays in session memory until you clear it or the session ends."
        )
    step(1, "Tell us about your bill")
    hospital_id = st.selectbox(
        "Hospital on your bill", list(hospitals), format_func=lambda x: hospitals[x]["name"]
    )
    basis = st.selectbox(
        "Which amounts are you checking?",
        ["gross", "cash", "negotiated"],
        format_func=lambda x: {
            "gross": "Original charges before insurance adjustments",
            "cash": "Agreed cash / self-pay amounts",
            "negotiated": "Allowed amounts after insurance adjustments",
        }[x],
    )
    st.caption(
        "Compare the same kind of amount. A bill's original charge can legitimately exceed a negotiated rate. Never compare the remaining patient balance as a line-item charge."
    )
    payer, plan = "", ""
    if basis == "negotiated":
        options = plans()
        if not options:
            st.warning("No negotiated rates available.")
            st.stop()
        payer, plan = st.selectbox(
            "Exact insurer and plan", options, format_func=lambda x: f"{x[0].title()} · {x[1].upper()}"
        )
    preferred_class, preferred_setting = bill_defaults(DB, snapshot_stamp, hospital_id, basis)
    with st.expander("Visit details · change if needed"):
        st.caption(
            "Use the visit and fee type printed on your bill. If unsure, ask the hospital’s billing team."
        )
        a, b = st.columns(2)
        setting = a.selectbox(
            "Care setting",
            [preferred_setting, *[x for x in ["outpatient", "inpatient", "both"] if x != preferred_setting]],
            format_func=lambda x: {
                "outpatient": "Outpatient · no overnight admission",
                "inpatient": "Inpatient · admitted to hospital",
                "both": "Not specified / both",
            }[x],
        )
        billing_class = b.selectbox(
            "Fee type",
            [
                preferred_class,
                *[x for x in ["facility", "professional", "both", "unknown"] if x != preferred_class],
            ],
            format_func=lambda x: {
                "facility": "Hospital fees",
                "professional": "Clinician fees",
                "both": "Hospital and clinician fees",
                "unknown": "Not specified",
            }[x],
        )
    step(2, "Add your bill")
    mode = st.radio(
        "Input method",
        (
            ["Try sample / enter structured lines", "Upload or paste text for local AI"]
            if stats["demo_prices"]
            else ["Upload or paste text for local AI", "Enter line items manually"]
        ),
        format_func=lambda x: (
            "Upload a bill"
            if x == "Upload or paste text for local AI"
            else "Try a sample bill"
            if x.startswith("Try")
            else x
        ),
        horizontal=True,
        label_visibility="collapsed",
    )
    if mode.startswith("Try") or mode == "Enter line items manually":
        st.caption(
            "Copy one row per service from your bill. Use the whole line charge, not your remaining balance."
        )
        manual_rows = st.data_editor(
            pd.DataFrame(
                columns=[
                    "code",
                    "description",
                    "quantity",
                    "charge",
                    "service_date",
                    "code_type",
                    "modifiers",
                ]
            ),
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key="bill_manual_editor",
            column_config={
                "code": st.column_config.TextColumn("Billing code", required=True),
                "description": st.column_config.TextColumn("Service"),
                "quantity": st.column_config.NumberColumn(
                    "Quantity", min_value=0.01, default=1, required=True
                ),
                "charge": st.column_config.NumberColumn("Line charge ($)", min_value=0, required=True),
                "service_date": st.column_config.DateColumn("Service date"),
                "code_type": st.column_config.SelectboxColumn(
                    "Code type", options=["CPT", "HCPCS", "unknown"], default="unknown"
                ),
                "modifiers": st.column_config.TextColumn("Modifier (if shown)"),
            },
        )
        with st.expander("Or paste formatted line items", expanded=bool(stats["demo_prices"])):
            text = st.text_area(
                "code | description | quantity | line total | date | code type | modifiers",
                value=Path("data/demo/sample_bill.txt").read_text() if stats["demo_prices"] else "",
                height=150,
                key="bill_manual",
                help="Example: 73721 | Knee MRI | 1 | 3600.00 | 2026-09-01 | CPT |",
            )

        def extract():
            from carecost.models import ExtractedBill

            if text.strip():
                return extract_structured_text(text)
            return ExtractedBill(
                lines=[
                    BillLine.model_validate(
                        {
                            k: (None if k == "service_date" else "unknown" if k == "code_type" else "")
                            if pd.isna(v)
                            else v
                            for k, v in row.items()
                        }
                    )
                    for row in manual_rows.to_dict("records")
                ]
            )
    else:
        uploaded = st.file_uploader(
            "Choose a photo or PDF of your itemized bill",
            type=["pdf", "png", "jpg", "jpeg", "txt"],
            key=f"bill_upload_{st.session_state.get('upload_generation', 0)}",
            help="PDF, PNG, JPG, or TXT. Up to 10 MB. Use a clear image with every line visible.",
        )
        with st.expander("Or paste the bill text"):
            text = st.text_area("Bill text", height=180, key="bill_text")
        with st.expander("Advanced · local AI settings"):
            local_model = st.text_input(
                "Locally installed Ollama model",
                value=os.getenv("CARECOST_OLLAMA_MODEL", "mistral:7b-instruct"),
            )
            st.caption("Requires a locally installed Ollama model. No cloud endpoint is used.")
        st.caption("We’ll read the bill and show you the line items to check before comparing prices.")

        def extract():
            content = read_document(uploaded.getvalue(), uploaded.name) if uploaded else text
            return extract_with_ollama(content, model=local_model)

    if st.button(
        "Read my bill",
        type="primary",
        disabled=(not uploaded and not text.strip())
        if mode == "Upload or paste text for local AI"
        else False,
    ):
        # Remove stale results before attempting a new extraction.
        st.session_state.pop("bill_lines", None)
        st.session_state.pop("bill_editor", None)
        st.session_state["bill_confirm"] = False
        try:
            with st.spinner("Reading your bill on this computer. This may take a minute…"):
                bill = extract()
            if not bill.lines:
                st.warning("No itemized lines found. Enter them manually or try clearer text.")
            else:
                st.session_state["bill_lines"] = [line.model_dump(mode="json") for line in bill.lines]
        except Exception:
            st.error(
                "Extraction could not be completed. Check the structured format, or confirm Ollama is running with the configured model. No bill content was written to a log by CareCost."
            )
    if "bill_lines" in st.session_state:
        step(3, "Check the details")
        st.subheader("Does this match your bill?")
        st.caption(
            "Edit mistakes and add missing items. Quantity is the number of published units; charge is the entire line total. Remove subtotals, payments, and summary balances."
        )
        edited = st.data_editor(
            pd.DataFrame(st.session_state["bill_lines"]),
            num_rows="dynamic",
            hide_index=True,
            key="bill_editor",
            width="stretch",
            column_config={
                "code": "Billing code",
                "description": "Service",
                "quantity": "Quantity",
                "charge": "Line charge ($)",
                "service_date": "Service date",
                "code_type": "Code type",
                "modifiers": "Modifier",
                "evidence": "Text from your bill",
            },
        )
        confirmed = st.checkbox(
            "I checked the codes, dates, modifiers, quantities, and line totals against the bill.",
            key="bill_confirm",
        )
        if st.button("Check these charges", disabled=not confirmed, type="primary"):
            try:
                lines = [
                    BillLine.model_validate(
                        {
                            k: (None if k == "service_date" else "") if pd.isna(v) else v
                            for k, v in row.items()
                        }
                    )
                    for row in edited.to_dict("records")
                ]
                with Repository(DB) as repo:
                    prices = repo.for_codes(hospital_id, [line.code for line in lines])
                results = check_bill(lines, prices, hospital_id, basis, payer, plan, setting, billing_class)
                count = sum(bool(r["flags"]) for r in results)
                st.subheader(f"{count} of {len(results)} lines to ask about")
                st.caption("These are questions for the billing team, not proof of an error.")
                for result in results:
                    with st.expander(
                        f"Line {result['line']} · {result['description']} · ${float(result['charge']):,.2f}",
                        expanded=bool(result["flags"]),
                    ):
                        for flag in result["flags"]:
                            st.warning(flag["message"])
                        if not result["flags"]:
                            st.write(
                                "No discrepancy detected against the selected published price. This is not a guarantee the bill is correct."
                            )
                        for source in result["sources"]:
                            st.caption(
                                f"Published {source['publication_date']} · ${source['unit_price']} per unit · row {source['row']}"
                                + (" · SYNTHETIC DEMO" if source["is_demo"] else "")
                            )
                            if not source["is_demo"] and source["url"].startswith("https://"):
                                st.link_button("View published source", source["url"])
                st.download_button(
                    "Download my review (contains bill details)",
                    json.dumps(
                        {
                            "hospital": hospitals[hospital_id]["name"],
                            "basis": basis,
                            "notice": "Possible discrepancies, not proof of a billing error.",
                            "results": results,
                        },
                        indent=2,
                    ),
                    "carecost-bill-review.json",
                    "application/json",
                )
                st.info(
                    "Ask the hospital for an explanation of each flagged line and the price effective on your service date. Repeated services, bundles, discounts, and separate fees may explain differences."
                )
            except Exception:
                st.error(
                    "Some edited rows are incomplete or invalid. Check quantities, line totals, dates (YYYY-MM-DD), and code types (CPT, HCPCS, unknown)."
                )

    if any(key.startswith("bill_") for key in st.session_state):
        st.divider()
        if st.button("Clear bill and review"):
            for key in list(st.session_state):
                if key.startswith("bill_"):
                    del st.session_state[key]
            st.session_state["upload_generation"] = st.session_state.get("upload_generation", 0) + 1
            st.rerun()
    footer()

else:
    st.markdown('<div class="hero-tag">Open methods. Traceable prices.</div>', unsafe_allow_html=True)
    st.title("Prices you can trace.")
    st.markdown(
        '<p class="intro">Real prices published by hospitals. Here’s what they include, where they come from, and what to keep in mind.</p>',
        unsafe_allow_html=True,
    )
    a, b, c = st.columns(3)
    a.metric("Hospitals", stats["hospitals"])
    b.metric("Procedure codes", stats["procedures"])
    c.metric("Validated price rows", stats["prices"])
    st.subheader("How prices enter CareCost")
    st.write(
        "Public hospital CSV and JSON files are streamed into a common format. Prices keep their code system, service definition, care setting, billing class, modifiers, payer, plan, publication date, source row and file fingerprint. Unsupported or invalid rows go to quarantine. Only explicit dollar prices for a single CPT/HCPCS code are shown."
    )
    st.write(
        "Files are snapshots, not guarantees of a future bill. Matching a code does not prove identical services. A missing price means this dataset could not provide a match, not that a hospital has no published price."
    )
    with Repository(DB) as repo:
        runs = pd.read_sql_query(
            "SELECT hospital_id,accepted,rejected,duplicates,finished_at FROM ingestion_runs ORDER BY finished_at DESC",
            repo.connection,
        )
    with st.expander("Technical details · data refresh history"):
        st.dataframe(runs, hide_index=True, width="stretch")
    st.subheader("Privacy in plain language")
    st.write(
        "The price pipeline stores public data. Uploaded bills, extracted text and reviews are not written to the database, application logs or disk by CareCost. OCR and the language model run on the app host. Session memory and operating-system swap can retain data temporarily; clearing a session is not cryptographic erasure. Hosting infrastructure, proxies and administrators need a separate privacy review before accepting real patient data."
    )
    with Repository(DB) as repo:
        active_sources = {
            (row[0], row[1])
            for row in repo.connection.execute("SELECT DISTINCT hospital_id,source_sha256 FROM prices")
        }
    live_report = Path("evaluations/live-data-report.json")
    live = json.loads(live_report.read_text()) if live_report.exists() else None
    report_is_current = (
        live and {(row["hospital_id"], row["sha256"]) for row in live["lineage"]} == active_sources
    )
    if not stats["demo_prices"] and live and not report_is_current:
        st.info(
            "The price snapshot changed after the last report. Run scripts/report_live_data.py and scripts/audit_live_prices.py to update reports."
        )
    if not stats["demo_prices"] and report_is_current:
        st.subheader("Published cash prices for common services")
        variation = pd.DataFrame(live["common_procedures"])
        if not variation.empty:
            chart = variation.set_index("description")[["min_cash", "max_cash"]].rename(
                columns={"min_cash": "Lowest cash price", "max_cash": "Highest cash price"}
            )
            st.bar_chart(
                chart,
                horizontal=True,
                stack=False,
                x_label="Published cash price (USD)",
                y_label="Published hospital service",
                height=540,
            )
        st.caption(
            f"Source: {stats['hospitals']} hospital files across {len({h['health_system'] for h in hospitals.values()})} health systems, latest publication {live['data']['published']}. Comparisons use exact service wording and pricing context; this is not the entire Boston market."
        )
        audit_path = Path("evaluations/live-price-audit.json")
        audit = json.loads(audit_path.read_text()) if audit_path.exists() else None
        audit_is_current = (
            audit and {(row["hospital_id"], row["source_sha256"]) for row in audit["rows"]} == active_sources
        )
        if audit_is_current:
            st.success(
                f"Source audit: {audit['passed']} of {audit['sample_size']} sampled records matched the original file fields."
            )
            st.caption(
                "Automated independent CSV comparison, not clinical validation. Prices are snapshots and may have changed since publication."
            )
        with st.expander("Live dataset coverage and exclusions"):
            st.json(live, expanded=False)
    st.subheader("What has been evaluated")
    result_path = Path(
        "evaluations/results.json" if stats["demo_prices"] else "evaluations/live-search-results.json"
    )
    if result_path.exists():
        results = json.loads(result_path.read_text())
        if not stats["demo_prices"] and results.get("data") != stats:
            st.info("Search scores are being refreshed for the expanded hospital catalog.")
            results = None
    else:
        results = None
    if results:
        st.caption(
            "Development search queries tested against the recorded published-code snapshot. Query labels are authored examples, not a patient study."
            if not stats["demo_prices"]
            else "Development benchmark against the synthetic fixture; separate from current live coverage."
        )
        x, y, z = st.columns(3)
        x.metric("Search top-1 · authored phrases", f"{results['search']['top1_accuracy']:.0%}")
        y.metric("Keyword baseline", f"{results['search']['keyword_top1_accuracy']:.0%}")
        z.metric(
            "Hand-calculated estimator cases",
            f"{results['estimator']['passed']}/{results['estimator']['hand_calculated_cases']}",
        )
        st.caption(
            "100 synthetic development phrases, including 40 reference aliases. These are not patient-study results."
        )
        if stats["demo_prices"] and results.get("price_variation"):
            st.subheader("Synthetic cash-price variation")
            variation = pd.DataFrame(results["price_variation"])
            variation = variation.set_index("description")[["min_cash", "max_cash"]].rename(
                columns={"min_cash": "Lowest cash price", "max_cash": "Highest cash price"}
            )
            st.bar_chart(
                variation,
                horizontal=True,
                stack=False,
                x_label="Published cash price (USD)",
                y_label="Example procedure",
                height=560,
            )
            st.caption(
                "Source: four fictional hospital fixtures dated 2026-01-01. Min/max by procedure and service context; hospital multipliers were chosen for demonstration."
            )
        with st.expander("Inspect full evaluation results"):
            st.json(results, expanded=False)
    st.write(
        "Demo evaluations use synthetic search phrases and planted billing discrepancies. They are development checks, not clinical validation or evidence of patient impact. Real user testing and clinician review are pending. The live source-record audit is reported separately above."
    )
    st.link_button(
        "CMS hospital price transparency technical guide",
        "https://github.com/CMSgov/hospital-price-transparency",
    )
