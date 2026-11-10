"""RAG 문서 모음 만들기.

포함: docs/sources/**/*.txt(허브 데이터 페이지·반출 기준, 첫 줄 '출처: ...'), 게시판 공식 답변 정리(02_게시판_QA정리.md),
센터 데이터명세서(공개 자료, 시트별). 제외: 대회 제공 허브 데이터 목록 파일(외부 배포 금지).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def _txt_sources(root: Path) -> list[dict]:
    docs = []
    for p in sorted((root / "docs" / "sources").rglob("*.txt")):
        lines = p.read_text("utf-8").splitlines()
        loc = lines[0].removeprefix("출처:").strip() if lines and lines[0].startswith("출처:") else str(p.name)
        body = "\n".join(lines[1:] if lines and lines[0].startswith("출처:") else lines)
        title = next((l for l in body.splitlines() if l.strip()), p.stem)[:80]
        docs.append({"doc_id": f"src:{p.stem}", "title": title, "locator": loc, "text": body})
    return docs


def _board_sections(root: Path) -> list[dict]:
    p = root / "02_게시판_QA정리.md"
    if not p.exists():
        return []
    parts = re.split(r"^## +(.+)$", p.read_text("utf-8"), flags=re.M)
    return [{"doc_id": f"board:{parts[i].strip()}", "title": f"게시판 답변 — {parts[i].strip()}",
             "locator": f"대회 게시판 공식 답변 정리 §{parts[i].strip()}", "text": parts[i + 1]}
            for i in range(1, len(parts), 2)]


def _spec_sheets(xlsx: Path) -> list[dict]:
    docs = []
    for name, df in pd.read_excel(xlsx, sheet_name=None, header=None).items():
        rows = [" | ".join(str(v).replace("\n", " ") for v in r if str(v) != "nan") for r in df.values]
        text = "\n".join(r for r in rows if r)
        docs.append({"doc_id": f"spec:{name.strip()}", "title": f"센터 데이터명세서 v13 — {name.strip()}",
                     "locator": f"제주빅데이터센터 데이터명세서 v13, 시트 「{name.strip()}」", "text": text})
    return docs


def load_corpus(root: Path | str, spec_xlsx: Path | str | None = "데이터명세서_kr.xlsx") -> list[dict]:
    root = Path(root)
    docs = _txt_sources(root) + _board_sections(root)
    if spec_xlsx:
        x = root / spec_xlsx
        if x.exists():
            docs += _spec_sheets(x)
    return docs
