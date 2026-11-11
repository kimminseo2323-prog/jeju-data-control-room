"""RAG 문서 모음 만들기.

포함: docs/sources/**/*.txt(허브 데이터 페이지·반출 기준, 첫 줄 '출처: ...'), 게시판 공식 답변 정리(02_게시판_QA정리.md),
이 프로젝트의 데이터 활용 명세·설치 매뉴얼(docs/*.md, 절 단위), 센터 데이터명세서(공개 자료, 시트별). 제외: 대회 제공 허브 데이터 목록 파일(외부 배포 금지).
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
        lines_ = [l.strip() for l in body.splitlines() if l.strip()]
        hub = next((l for l in lines_ if l.startswith("인증 ")), None)   # 허브 페이지: '인증 [분류] 데이터명' 줄이 이름
        if hub:
            title = "허브 데이터 — " + re.sub(r"^인증\s*(\[[^\]]*\])?\s*", "", hub)
        else:
            title = next((l for l in lines_ if l != "관리자"), p.stem)
        title = title[:80]
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


OWN_DOCS = {"데이터_활용_명세": "데이터 활용 명세", "설치_실행_매뉴얼": "설치·실행 매뉴얼"}


def _own_doc_sections(root: Path) -> list[dict]:
    """docs/의 우리 문서를 '## 절' 단위로. 질문에 답하는 문서(데이터 출처·쿼터·문제 해결)라 검색 대상에 넣는다."""
    docs = []
    for stem, name in OWN_DOCS.items():
        p = root / "docs" / f"{stem}.md"
        if not p.exists():
            continue
        parts = re.split(r"^## +(.+)$", p.read_text("utf-8"), flags=re.M)
        for i in range(1, len(parts), 2):
            h = parts[i].strip()
            docs.append({"doc_id": f"md:{stem}§{h}", "title": f"{name} — {h}", "locator": f"docs/{stem}.md §{h}", "text": parts[i + 1]})
    return docs


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
    docs = _txt_sources(root) + _board_sections(root) + _own_doc_sections(root)
    if spec_xlsx:
        x = root / spec_xlsx
        if x.exists():
            docs += _spec_sheets(x)
    return docs
