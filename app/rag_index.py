"""Thread-safe corpus snapshots and bounded, permission-scoped TF-IDF caches."""
import hashlib
import json
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from datetime import datetime, timezone
from sqlalchemy import select
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.recommendation import content_visible
from app.source_metadata import content_active, source_details


def chunks(text, target=360, overlap=50):
    text = re.sub(r"\r\n?", "\n", text or "").strip()
    result, current = [], ""
    for paragraph in [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]:
        if len(paragraph) <= target and len(current) + len(paragraph) + 1 <= target:
            current = f"{current}\n{paragraph}".strip()
            continue
        if current:
            result.append(current)
            current = ""
        if len(paragraph) <= target:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            end = min(len(paragraph), start + target)
            result.append(paragraph[start:end])
            if end == len(paragraph):
                break
            start = end - overlap
    if current:
        result.append(current)
    return result


@dataclass
class Snapshot:
    version: str
    contents: dict
    chunks: list
    scopes: OrderedDict = field(default_factory=OrderedDict)


class RagIndex:
    def __init__(self, engine, contents, documents, scope_limit=16):
        self.engine, self.contents, self.documents = engine, contents, documents
        self.scope_limit = scope_limit
        self.lock = RLock()
        self.snapshot = None
        self.fit_count = 0
        self.rebuild_count = 0

    def get(self, force=False):
        # Hash actual data rather than trusting timestamps: direct SQL edits,
        # permission changes and same-ID replacements must invalidate the index.
        with self.lock:
            with self.engine.begin() as conn:
                rows = [dict(r) for r in conn.execute(select(self.contents).where(self.contents.c.status == "published").order_by(self.contents.c.id)).mappings()]
                version = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
                if not force and self.snapshot and self.snapshot.version == version:
                    return self.snapshot
                payload = []
                for row in rows:
                    for index, text in enumerate(chunks(row.get("body") or row.get("summary"))):
                        payload.append(dict(source_content_id=row["id"], chunk_index=index, title=row["title"], chunk_text=text,
                            **{key: row.get(key) for key in ("content_type", "target_roles", "target_colleges", "target_majors", "target_grades", "publish_time", "source_url")},
                            embedding="[]", embed_model="tfidf-char-2-4", content_hash=hashlib.sha256(f"{row['id']}:{index}:{text}".encode()).hexdigest(), created_at=datetime.now(timezone.utc).isoformat()))
                conn.execute(self.documents.delete())
                if payload:
                    conn.execute(self.documents.insert(), payload)
                records = [dict(r) for r in conn.execute(select(self.documents).order_by(self.documents.c.id)).mappings()]
            snapshot = Snapshot(version, {r["id"]: r for r in rows}, records)
            self.snapshot = snapshot
            self.rebuild_count += 1
            return snapshot

    def search(self, snapshot, user, question, threshold=0.30):
        at = datetime.now(timezone.utc)
        eligible = {identifier for identifier, row in snapshot.contents.items()
                    if content_visible(user, row) and content_active(row, at)}
        key = tuple(sorted(eligible))
        with self.lock:
            if key not in snapshot.scopes:
                visible = [c for c in snapshot.chunks if c["source_content_id"] in eligible]
                texts = [f"{c['title']} {c['chunk_text']}" for c in visible]
                vectorizer, matrix = None, None
                if texts:
                    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1)
                    try:
                        matrix = vectorizer.fit_transform(texts)
                        self.fit_count += 1
                    except ValueError:
                        vectorizer = None  # Empty vocabulary still permits keyword retrieval.
                snapshot.scopes[key] = (visible, texts, vectorizer, matrix)
                while len(snapshot.scopes) > self.scope_limit:
                    snapshot.scopes.popitem(last=False)
            visible, texts, vectorizer, matrix = snapshot.scopes[key]
            snapshot.scopes.move_to_end(key)
        if not visible:
            return []
        sims = cosine_similarity(vectorizer.transform([question]), matrix)[0] if vectorizer is not None else [0.0] * len(visible)
        tokens = [token for token in re.findall(r"[\w\u4e00-\u9fff]+", question.lower()) if len(token) > 1]
        terms = set(tokens)
        for token in tokens:
            if len(token) > 2:
                terms.update(token[i:i+2] for i in range(len(token)-1))
        keywords = [sum(term in text.lower() for term in terms) for text in texts]
        # Gate each source, not just the highest scoring source, so a strong hit
        # cannot pull unrelated chunks into the answer/citations.
        reliable = {i for i, text in enumerate(texts)
                    if any(token in text.lower() for token in tokens) or float(sims[i]) >= threshold}
        ranks = {}
        for values in (sims, keywords):
            ordered = sorted((i for i in reliable if values[i] > 0), key=lambda i: (-float(values[i]), i))[:20]
            for rank, i in enumerate(ordered, 1):
                ranks[i] = ranks.get(i, 0.0) + 1 / (60 + rank)
        ordered = sorted(ranks, key=lambda i: (-ranks[i], -float(sims[i]), i))
        sources, seen = [], set()
        for i in ordered:
            chunk = visible[i]
            identifier = chunk["source_content_id"]
            if identifier in seen:
                continue
            seen.add(identifier)
            source = snapshot.contents[identifier]
            sources.append(dict(chunk_id=chunk["id"], content_id=identifier, title=chunk["title"], snippet=chunk["chunk_text"],
                                similarity_score=round(float(sims[i]), 4), rrf_score=round(ranks[i], 6), **source_details(source)))
            if len(sources) == 5:
                break
        return sources
