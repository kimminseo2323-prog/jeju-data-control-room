"""제출 폴더 만들기: 프로젝트에서 제출할 파일만 골라 `숨비소리/` 폴더로 복사한다(이 폴더를 그대로 압축해 제출).

실행: python docs/_build/make_submission.py
결과: <프로젝트>/숨비소리/  (다시 실행하면 이 폴더만 지우고 새로 만든다)

넣는 것: 실행 소스(app), 테스트, 평가 스크립트·결과, 노트북, 문서(README·설치 매뉴얼·데이터 활용 명세·결과 설명서),
         허브 공개 데이터 캐시(parquet)·축제 CSV, 센터 데이터명세서(공개 자료, 문서 검색용), 게시판 답변 정리(문서 검색용), 기획서 PDF
빼는 것: .env(API 키), 허브 데이터목록 xlsx(배포 금지), 가상환경·모델 파일(.venv, .tools), 수집 상태·로그(data/state),
         저장 결과(data/results), git 기록, 개인·내부 작업 메모(00·01·04·05), 기획서 작업 파일(docx·생성기)
"""
from __future__ import annotations

import fnmatch
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "숨비소리"
PLAN_PDF = "숨비소리_AI_Agent_기획서_v0.4.pdf"

FILES = ["README.md", "install.bat", "run.bat", "requirements.txt", "requirements-dev.txt", "pytest.ini", ".env.example",
         ".streamlit/config.toml", "02_게시판_QA정리.md", "데이터명세서_kr.xlsx"]
DIRS = ["app", "tests", "eval", "notebooks", "docs", "data/cache", "data/manual"]
SKIP = ["__pycache__", "*.pyc", ".pytest_cache", ".ipynb_checkpoints", "~$*"]
FORBIDDEN = ["제주데이터허브 데이터목록*", ".env", ".venv", ".tools", "state", "results/briefing*"]


def _skip(p: Path) -> bool:
    return any(fnmatch.fnmatch(part, pat) for part in p.parts for pat in SKIP)


def build() -> Path:
    assert OUT.parent == ROOT and OUT.name == "숨비소리"
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for f in FILES:
        (OUT / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, OUT / f)
    for d in DIRS:
        for src in (ROOT / d).rglob("*"):
            if src.is_file() and not _skip(src.relative_to(ROOT)):
                dst = OUT / src.relative_to(ROOT)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    (OUT / "기획서").mkdir()
    shutil.copy2(ROOT / "기획서" / PLAN_PDF, OUT / "기획서" / PLAN_PDF)
    return OUT


def check(out: Path) -> list[str]:
    """제출 금지 파일·API 키가 들어가지 않았는지 확인한다."""
    problems = []
    for p in out.rglob("*"):
        rel = p.relative_to(out)
        if any(fnmatch.fnmatch(part, pat) for part in rel.parts for pat in FORBIDDEN) and str(rel) != ".env.example":
            problems.append(f"금지 파일: {rel}")
    key = ""
    env = ROOT / ".env"
    if env.exists():
        m = re.search(r"^JEJU_HUB_PROJECT_KEY=(\S+)", env.read_text("utf-8"), re.M)
        key = m[1] if m else ""
    if key:
        for p in out.rglob("*"):
            if p.is_file() and key.encode() in p.read_bytes():
                problems.append(f"허브 키가 들어 있음: {p.relative_to(out)}")
    return problems


if __name__ == "__main__":
    out = build()
    files = [p for p in out.rglob("*") if p.is_file()]
    size = sum(p.stat().st_size for p in files)
    print(f"{out} — 파일 {len(files)}개, {size / 1e6:.1f}MB")
    probs = check(out)
    print("검사: 이상 없음" if not probs else "\n".join(probs))
    sys.exit(1 if probs else 0)
