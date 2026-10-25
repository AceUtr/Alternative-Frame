"""Dependency-free lexical retrieval with optional vector ranking and RRF fusion."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4


class VectorRetriever(Protocol):
    def search(self, query: str, records: list["MemoryRecord"], limit: int) -> list[tuple[str, float]]: ...


@dataclass
class MemoryRecord:
    id: str
    namespace: str
    content: str
    metadata: dict = field(default_factory=dict)


def _terms(text: str) -> list[str]:
    parts = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", text.casefold())
    terms = []
    for part in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            terms.extend(part[index:index + 2] for index in range(max(1, len(part) - 1)))
        else:
            terms.append(part)
    return terms


class HybridMemory:
    """BM25 lexical search optionally fused with an injected embedding retriever."""

    def __init__(self, vector_retriever: VectorRetriever | None = None, rrf_k: int = 60):
        self.vector_retriever = vector_retriever
        self.rrf_k = rrf_k
        self._records: list[MemoryRecord] = []

    def add(self, namespace: str, content: str, metadata: dict | None = None, record_id: str | None = None) -> str:
        if not namespace or not content.strip():
            raise ValueError("namespace and non-empty content are required")
        record_id = record_id or uuid4().hex
        self._records.append(MemoryRecord(record_id, namespace, content, dict(metadata or {})))
        return record_id

    def _lexical(self, query: str, records: list[MemoryRecord], limit: int) -> list[tuple[str, float]]:
        query_terms = set(_terms(query))
        docs = [_terms(record.content) for record in records]
        if not query_terms or not docs:
            return []
        avg_len = sum(map(len, docs)) / len(docs) or 1.0
        scores = []
        for record, terms in zip(records, docs):
            length = len(terms) or 1
            score = 0.0
            for term in query_terms:
                tf = terms.count(term)
                if not tf:
                    continue
                df = sum(term in doc for doc in docs)
                idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
                score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / avg_len))
            if score > 0:
                scores.append((record.id, score))
        return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]

    def search(self, namespace: str, query: str, limit: int = 5) -> list[dict]:
        if limit <= 0:
            return []
        records = [item for item in self._records if item.namespace == namespace]
        rankings = [self._lexical(query, records, max(limit * 4, limit))]
        if self.vector_retriever is not None:
            rankings.append(self.vector_retriever.search(query, records, max(limit * 4, limit)))
        fused: dict[str, float] = {}
        for ranking in rankings:
            for rank, (record_id, _score) in enumerate(ranking, start=1):
                fused[record_id] = fused.get(record_id, 0.0) + 1.0 / (self.rrf_k + rank)
        by_id = {item.id: item for item in records}
        ordered = sorted(fused, key=lambda record_id: (-fused[record_id], record_id))[:limit]
        return [{"id": record_id, "namespace": by_id[record_id].namespace, "content": by_id[record_id].content,
                 "metadata": dict(by_id[record_id].metadata), "score": fused[record_id]} for record_id in ordered]
