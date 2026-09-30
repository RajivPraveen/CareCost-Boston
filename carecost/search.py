from __future__ import annotations

import json
import re
import tempfile
from hashlib import sha256
from pathlib import Path


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold())) - {"a", "the", "of", "for", "my", "i", "need", "an"}


def load_search_catalog(database, snapshot_stamp, index_dir="data/index"):
    """Load the public code catalog without rescanning the price table on every app start."""
    from carecost.repository import Repository

    directory = Path(index_dir)
    cache_key = sha256(
        json.dumps([str(Path(database).resolve()), snapshot_stamp]).encode("utf-8")
    ).hexdigest()[:20]
    cache_file = directory / f"catalog-{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    with Repository(database) as repo:
        catalog = repo.catalog()
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as temporary:
        json.dump(catalog, temporary, ensure_ascii=False)
    Path(temporary.name).replace(cache_file)
    return catalog


class ProcedureSearch:
    def __init__(
        self,
        catalog,
        reference_path="data/reference/procedures.json",
        model_path=None,
        index_dir="data/index",
    ):
        reference = json.loads(Path(reference_path).read_text()) if Path(reference_path).exists() else []
        self.reference = reference
        lookup = {(p["code_type"], p["code"]): p for p in reference}
        numeric_labels = {p["code"]: p for p in reference if p["code_type"] == "CPT" and p["code"].isdigit()}
        # Some hospital files label numeric CPT (HCPCS Level I) codes as HCPCS.
        # Enrich their display labels without changing the disclosed code system or price identity.
        self.procedures = [
            {
                **p,
                **lookup.get((p["code_type"], p["code"]), numeric_labels.get(p["code"], {})),
                "code_type": p["code_type"],
            }
            for p in catalog
        ]
        self.model = self.index = None
        if model_path:
            # A local path and local_files_only prevent inference-time model downloads.
            if not Path(model_path).is_dir():
                raise ValueError("Download an embedding model explicitly before enabling semantic search.")
            import faiss
            import torch
            from sentence_transformers import SentenceTransformer

            faiss.omp_set_num_threads(1)
            torch.set_num_threads(1)
            self.model = SentenceTransformer(
                str(model_path), local_files_only=True, trust_remote_code=False, device="cpu"
            )
            import numpy as np

            # The embedding step is slow for a full hospital catalog. Keep a local,
            # content-addressed copy so normal app clicks only load ready vectors.
            index_path = Path(index_dir)
            fingerprint = sha256(
                json.dumps(self.procedures, sort_keys=True, ensure_ascii=False).encode("utf-8")
                + str(Path(model_path).resolve()).encode("utf-8")
            ).hexdigest()[:20]
            vector_file = index_path / f"procedures-{fingerprint}.npy"
            if vector_file.exists():
                vectors = np.load(vector_file, allow_pickle=False)
                if vectors.shape[0] != len(self.procedures):
                    raise ValueError("Cached search index does not match the procedure catalog")
            else:
                vectors = self.model.encode(
                    [self._text(p) for p in self.procedures], normalize_embeddings=True
                ).astype("float32")
                index_path.mkdir(parents=True, exist_ok=True)
                temporary = vector_file.with_suffix(".tmp.npy")
                np.save(temporary, vectors, allow_pickle=False)
                temporary.replace(vector_file)
            self.index = faiss.IndexFlatIP(vectors.shape[1])
            self.index.add(vectors.astype("float32"))

    @staticmethod
    def _text(p):
        return " ".join([p.get("name", ""), p["description"], " ".join(p.get("aliases", []))])

    def search(self, query, limit=5, baseline=False):
        if not query.strip():
            return []
        if re.fullmatch(r"(?:[A-Z]\d{4}|\d{5}|\d{4}[A-Z])", query.strip().upper()):
            return [{**p, "score": 10.0} for p in self.procedures if p["code"] == query.strip().upper()][
                :limit
            ]
        if not baseline:
            exact_codes = {
                p["code"]
                for p in self.reference
                if query.strip().casefold()
                in {x.casefold() for x in [p.get("name", ""), *p.get("aliases", [])]}
            }
            if exact_codes:
                return [{**p, "score": 10.0} for p in self.procedures if p["code"] in exact_codes][:limit]
        query_tokens = tokens(query)
        semantic = {}
        if self.model and not baseline:
            q = self.model.encode(
                ["Represent this sentence for searching relevant passages: " + query],
                normalize_embeddings=True,
            )
            scores, ids = self.index.search(q.astype("float32"), min(limit * 3, len(self.procedures)))
            semantic = dict(zip(ids[0].tolist(), scores[0].tolist()))
        results = []
        for idx, p in enumerate(self.procedures):
            text = p["description"] if baseline else self._text(p)
            if not baseline and "menisc" in query.casefold() and "menisc" not in text.casefold():
                continue
            words = tokens(text)
            score = len(query_tokens & words) / max(1, len(query_tokens))
            if not baseline:
                phrases = [p.get("name", ""), *p.get("aliases", [])]
                if any(query.casefold().strip() == x.casefold() for x in phrases):
                    score += 1
                if self.model:
                    score = 0.4 * score + 0.6 * semantic.get(idx, 0)
            if query.strip().upper() == p["code"]:
                score = 10
            if score > 0:
                results.append({**p, "score": round(score, 4)})
        return sorted(results, key=lambda p: (-p["score"], p["code"]))[:limit]
