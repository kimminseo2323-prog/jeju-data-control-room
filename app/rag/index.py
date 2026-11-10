"""문서 검색(RAG): 데이터 명세·API 기술문서·반출 기준·게시판 답변을 조각 내어 BM25로 검색.

한국어 형태소 분석기 없이도 동작하도록 한글은 글자 2-gram, 영문·숫자는 단어 단위로 토큰화한다.
모든 결과 조각에는 출처 위치(locator)가 붙는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

_WORD = re.compile(r"[A-Za-z]+|\d+|[가-힣]+")


def tokenize(text: str) -> list[str]:
    toks = []
    for w in _WORD.findall(text or ""):
        if re.fullmatch(r"[가-힣]+", w):
            toks.extend([w] if len(w) == 1 else [w[i:i + 2] for i in range(len(w) - 1)])
        else:
            toks.append(w.lower())
    return toks


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    if len(text) <= size:
        return [text]
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        if i + size >= len(text):
            break
        i += size - overlap
    return out


@dataclass(frozen=True)
class Passage:
    doc_id: str
    title: str
    locator: str
    text: str
    score: float


class Index:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([tokenize(c["title"] + " " + c["text"]) for c in chunks])

    def search(self, query: str, k: int = 5) -> list[Passage]:
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [Passage(self.chunks[i]["doc_id"], self.chunks[i]["title"], self.chunks[i]["locator"],
                        self.chunks[i]["text"], float(scores[i])) for i in order[:k] if scores[i] > 0]


def build_index(docs: list[dict], size: int = 500, overlap: int = 50) -> Index:
    chunks = []
    for d in docs:
        for n, part in enumerate(chunk_text(d["text"], size, overlap), 1):
            loc = d["locator"] if n == 1 and len(d["text"]) <= size else f"{d['locator']} (조각 {n})"
            chunks.append({"doc_id": d["doc_id"], "title": d["title"], "locator": loc, "text": part})
    return Index(chunks)
