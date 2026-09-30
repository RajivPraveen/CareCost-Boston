"""Exercise image and scanned-PDF OCR using a generated, non-patient test bill."""

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from carecost.bills import read_document, tesseract_executable

image = Image.new("RGB", (1600, 550), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=28)
lines = [
    "TEST BILL - NOT A REAL PATIENT",
    "Massachusetts General Hospital",
    "Service date: 2026-09-01",
    "CPT 73721 MRI lower extremity joint without contrast",
    "Quantity 1    Line total $3600.00",
]
for i, line in enumerate(lines):
    draw.text((40, 40 + i * 70), line, fill="black", font=font)
results = {}
for fmt, filename in [("PNG", "test.png"), ("PDF", "test.pdf")]:
    buf = io.BytesIO()
    image.save(buf, format=fmt, resolution=150)
    text = read_document(buf.getvalue(), filename)
    passed = all(token in text for token in ["73721", "3600.00", "2026-09-01"])
    results[fmt] = dict(passed=passed, extracted_text=text)
Path("evaluations/ocr-smoke.json").write_text(
    json.dumps(
        {
            "executable": Path(tesseract_executable()).name,
            "tests": results,
            "note": "Generated legible test image and a scanned PDF of that image; not a representative OCR accuracy benchmark.",
        },
        indent=2,
    )
    + "\n"
)
print(json.dumps(results, indent=2))
if not all(v["passed"] for v in results.values()):
    raise SystemExit("OCR smoke check failed")
