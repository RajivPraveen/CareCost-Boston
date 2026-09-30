"""Deterministic synthetic fixtures. These are not hospital disclosures or observed prices."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
procedures = [
    (
        "73721",
        "Knee MRI without contrast",
        "Imaging",
        640,
        [
            "knee MRI",
            "MRI of my knee",
            "knee scan no dye",
            "magnetic scan knee",
            "knee imaging without contrast",
        ],
    ),
    (
        "70551",
        "Brain MRI without contrast",
        "Imaging",
        850,
        [
            "brain MRI",
            "MRI of my head",
            "brain scan no dye",
            "magnetic brain scan",
            "head MRI without contrast",
        ],
    ),
    (
        "72148",
        "Lower back MRI without contrast",
        "Imaging",
        780,
        ["back MRI", "lumbar scan", "lower spine MRI", "MRI lower back no dye", "lumbar spine imaging"],
    ),
    (
        "74177",
        "Abdomen and pelvis CT with contrast",
        "Imaging",
        540,
        [
            "belly CT",
            "abdominal CT with dye",
            "abdomen pelvis scan",
            "CT stomach area",
            "pelvic CT with contrast",
        ],
    ),
    (
        "70450",
        "Head CT without contrast",
        "Imaging",
        320,
        ["head CT", "CT of brain", "head scan no contrast", "computed tomography head", "brain CT no dye"],
    ),
    (
        "71046",
        "Chest X-ray, two views",
        "Imaging",
        95,
        ["chest xray", "lung x-ray", "two view chest film", "chest radiograph", "x ray of lungs"],
    ),
    (
        "76700",
        "Complete abdominal ultrasound",
        "Imaging",
        210,
        [
            "belly ultrasound",
            "abdominal sonogram",
            "ultrasound stomach",
            "abdomen ultrasound",
            "complete abdominal scan ultrasound",
        ],
    ),
    (
        "77067",
        "Screening mammogram, both breasts",
        "Screening",
        170,
        [
            "mammogram",
            "breast cancer screening",
            "routine breast xray",
            "screening breast imaging",
            "both breasts mammography",
        ],
    ),
    (
        "45378",
        "Diagnostic colonoscopy",
        "Digestive care",
        1100,
        ["colonoscopy", "colon scope", "camera exam colon", "large intestine exam", "diagnostic bowel scope"],
    ),
    (
        "43235",
        "Upper digestive tract endoscopy",
        "Digestive care",
        900,
        ["upper endoscopy", "stomach scope", "EGD", "camera in stomach", "upper GI scope"],
    ),
    (
        "59409",
        "Vaginal delivery only",
        "Maternity",
        3200,
        [
            "baby delivery",
            "vaginal birth",
            "normal childbirth",
            "delivery without c section",
            "vaginal delivery only",
        ],
    ),
    (
        "59514",
        "Cesarean delivery only",
        "Maternity",
        4800,
        ["c section", "cesarean birth", "surgical baby delivery", "caesarean delivery", "cesarean only"],
    ),
    (
        "80053",
        "Comprehensive metabolic blood panel",
        "Lab tests",
        28,
        [
            "metabolic panel",
            "CMP blood test",
            "comprehensive blood chemistry",
            "liver kidney blood panel",
            "comprehensive metabolic testing",
        ],
    ),
    (
        "85025",
        "Blood count with differential",
        "Lab tests",
        19,
        [
            "blood count",
            "CBC with differential",
            "complete blood cell test",
            "red white blood count",
            "blood cells panel",
        ],
    ),
    (
        "80061",
        "Cholesterol and lipid panel",
        "Lab tests",
        24,
        ["cholesterol test", "lipid panel", "blood fat test", "cholesterol blood work", "HDL LDL test"],
    ),
    (
        "83036",
        "Hemoglobin A1c blood test",
        "Lab tests",
        23,
        [
            "A1c test",
            "three month blood sugar",
            "diabetes blood test A1c",
            "hemoglobin a1c",
            "average glucose test",
        ],
    ),
    (
        "93306",
        "Complete heart ultrasound",
        "Heart care",
        490,
        ["echocardiogram", "heart ultrasound", "cardiac echo", "complete echo test", "ultrasound of heart"],
    ),
    (
        "93000",
        "Electrocardiogram with interpretation",
        "Heart care",
        65,
        ["EKG", "ECG test", "heart electrical test", "electrocardiogram", "heart rhythm tracing"],
    ),
    (
        "97110",
        "Therapeutic exercises, 15 minutes",
        "Rehabilitation",
        48,
        [
            "physical therapy exercises",
            "PT exercise session",
            "therapeutic exercise",
            "rehab exercises 15 minutes",
            "physio exercises",
        ],
    ),
    (
        "29881",
        "Knee arthroscopy with meniscus procedure",
        "Surgery",
        2900,
        [
            "meniscus surgery",
            "knee arthroscopy",
            "torn meniscus procedure",
            "knee keyhole surgery",
            "arthroscopic meniscus repair cost",
        ],
    ),
]
ref, queries = [], []
for code, name, category, _, phrases in procedures:
    # Reference aliases and evaluation queries deliberately differ. The test set is synthetic,
    # authored for this prototype and not an independent clinical relevance benchmark.
    aliases = phrases[:2]
    ref.append(
        dict(code=code, code_type="CPT", name=name, description=name, category=category, aliases=aliases)
    )
    queries.extend(
        {"query": phrase, "expected_code": code, "code_type": "CPT", "overlaps_alias": phrase in aliases}
        for phrase in phrases
    )
(ROOT / "data/reference/procedures.json").write_text(json.dumps(ref, indent=2) + "\n")
(ROOT / "evaluations/search_queries.json").write_text(json.dumps(queries, indent=2) + "\n")
hospitals = [
    dict(
        hospital_id="demo_harbor",
        name="Harbor Medical Center · Demo",
        latitude=42.3601,
        longitude=-71.0589,
        city="Boston",
        health_system="Fictional Harbor Health",
    ),
    dict(
        hospital_id="demo_charles",
        name="Charles River Hospital · Demo",
        latitude=42.3736,
        longitude=-71.1097,
        city="Cambridge",
        health_system="Fictional Charles Health",
    ),
    dict(
        hospital_id="demo_fenway",
        name="Fenway Community Hospital · Demo",
        latitude=42.3429,
        longitude=-71.1003,
        city="Boston",
        health_system="Fictional Fenway Health",
    ),
    dict(
        hospital_id="demo_somerville",
        name="Somerville Care Center · Demo",
        latitude=42.3876,
        longitude=-71.0995,
        city="Somerville",
        health_system="Fictional Community Health",
    ),
]
sources = []
for h, factor in zip(hospitals, [1, 1.48, 2.35, 0.82]):
    filename = f"data/demo/{h['hospital_id']}.csv"
    with (ROOT / filename).open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "code",
                "code_type",
                "description",
                "setting",
                "billing_class",
                "price_type",
                "payer",
                "plan",
                "amount",
                "source_date",
            ],
        )
        writer.writeheader()
        for code, name, _, base, _ in procedures:
            for price_type, multiplier, payer, plan in [
                ("cash", 1, "", ""),
                ("gross", 2.9, "", ""),
                ("negotiated", 1.15, "BCBS MA", "PPO"),
                ("negotiated", 0.93, "Aetna", "PPO"),
            ]:
                writer.writerow(
                    dict(
                        code=code,
                        code_type="CPT",
                        description=name,
                        setting="inpatient" if code in {"59409", "59514"} else "outpatient",
                        billing_class="facility",
                        price_type=price_type,
                        payer=payer,
                        plan=plan,
                        amount=round(base * factor * multiplier, 2),
                        source_date="2026-01-01",
                    )
                )
    sources.append(
        dict(
            hospital_id=h["hospital_id"],
            path=filename,
            url=filename,
            source_date="2026-01-01",
            is_demo=True,
            hospital=h,
        )
    )
(ROOT / "config/demo_sources.json").write_text(json.dumps(sources, indent=2) + "\n")
(ROOT / "data/demo/sample_bill.txt").write_text(
    "73721 | Knee MRI without contrast | 1 | 2400.00 | 2026-09-01 | CPT |\n85025 | Blood count with differential | 1 | 55.10 | 2026-09-01 | CPT |\n85025 | Blood count with differential | 1 | 55.10 | 2026-09-01 | CPT |\n99999 | Unmatched service | 1 | 120.00 | 2026-09-01 | CPT |\n"
)
