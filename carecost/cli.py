from __future__ import annotations

import argparse
import json
import os
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from carecost.ingestion import ingest_file
from carecost.repository import Repository


def load_manifest(manifest, database, download=False):
    sources = json.loads(Path(manifest).read_text())
    aliases = json.loads(Path("config/payer_aliases.json").read_text())
    if len({s["hospital_id"] for s in sources}) != len(sources):
        raise ValueError("Manifest must contain one current snapshot per hospital")
    if len({bool(s.get("is_demo", False)) for s in sources}) > 1:
        raise ValueError("Do not mix demo and real sources in a manifest")
    with Repository(database) as repo:
        stats = repo.statistics()
        if stats["prices"] and sources:
            existing_demo = stats["demo_prices"] > 0
            if existing_demo != bool(sources[0].get("is_demo", False)):
                raise ValueError("Use a separate database for demo and real data")
        for source in sources:
            path = Path(source["path"])
            if source["hospital"]["hospital_id"] != source["hospital_id"]:
                raise ValueError("Hospital identifiers must match")
            if not source.get("is_demo") and urlparse(source["url"]).scheme != "https":
                raise ValueError("Real data requires an HTTPS source URL for lineage")
            if download:
                if source.get("archive_path"):
                    archive = Path(source["archive_path"])
                    download_file(source["url"], archive)
                    extract_price_archive(archive, path)
                else:
                    download_file(source["url"], path)
            print(
                json.dumps(
                    {
                        "hospital": source["hospital_id"],
                        **ingest_file(repo, path, source, source["hospital"], aliases),
                    }
                )
            )


def extract_price_archive(archive, destination, max_bytes=2_000_000_000):
    """Extract one explicit CSV/JSON member without trusting archive path names."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with zipfile.ZipFile(archive) as z:
            members = [
                i
                for i in z.infolist()
                if not i.is_dir()
                and i.filename.lower().endswith((".csv", ".json"))
                and not i.filename.startswith("__MACOSX/")
            ]
            if len(members) != 1 or members[0].file_size > max_bytes:
                raise ValueError("Archive must contain one CSV/JSON file smaller than the extraction limit")
            with z.open(members[0]) as src, temporary.open("wb") as out:
                written = 0
                while block := src.read(1024 * 1024):
                    written += len(block)
                    if written > max_bytes:
                        raise ValueError("Uncompressed price file exceeds extraction limit")
                    out.write(block)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_file(url, path, max_bytes=2_000_000_000):
    if urlparse(url).scheme != "https":
        raise ValueError("Public source downloads require HTTPS")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=(15, 90)) as response:
            response.raise_for_status()
            if urlparse(response.url).scheme != "https":
                raise ValueError("Source redirected to an insecure URL")
            size = 0
            with temporary.open("wb") as f:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Source exceeds configured 2 GB download limit")
                    f.write(chunk)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="CareCost pipeline and evaluations; run from the repository root"
    )
    parser.add_argument("--db", default=os.getenv("CARECOST_DB"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Load clearly labeled synthetic data")
    ingest = commands.add_parser("ingest", help="Validate and atomically replace each hospital's snapshot")
    ingest.add_argument("manifest")
    ingest.add_argument("--download", action="store_true")
    commands.add_parser("stats")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--model-path", default=None)
    evaluate.add_argument("--output", default="evaluations/results.json")
    commands.add_parser("warehouse-load")
    commands.add_parser("warehouse-bootstrap")
    export = commands.add_parser("warehouse-export")
    export.add_argument("output", help="New local SQLite database populated from tested dbt mart")
    args = parser.parse_args()
    if not args.db:
        args.db = "data/processed/demo.sqlite" if args.command == "demo" else "data/processed/boston.sqlite"
    try:
        if args.command == "demo":
            load_manifest("config/demo_sources.json", args.db)
        elif args.command == "ingest":
            load_manifest(args.manifest, args.db, args.download)
        elif args.command == "stats":
            with Repository(args.db) as repo:
                print(json.dumps(repo.statistics(), indent=2))
        elif args.command == "evaluate":
            from carecost.evaluation import evaluate

            print(json.dumps(evaluate(args.db, args.output, args.model_path), indent=2))
        elif args.command == "warehouse-load":
            from carecost.warehouse import load

            print(load(args.db))
        elif args.command == "warehouse-bootstrap":
            from carecost.warehouse import bootstrap

            print(json.dumps(bootstrap(), indent=2))
        elif args.command == "warehouse-export":
            from carecost.warehouse import export

            print(export(args.output))
    except (ValueError, OSError, requests.RequestException) as exc:
        parser.exit(1, f"CareCost: {exc}\n")


if __name__ == "__main__":
    main()
