"""제출 폴더 만들기: 프로젝트에서 제출할 파일만 골라 `숨비소리/` 폴더로 복사한다(이 폴더를 그대로 압축해 제출).

실행: python docs/_build/make_submission.py  (먼저 문서 PDF를 만든다: python docs/_build/build_results.py docs/결과_설명서.md docs/설치_실행_매뉴얼.md docs/데이터_활용_명세.md)
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


README_TXT = """제주 데이터 관제실 (팀 숨비소리)
제주 읍면동별 유동인구·외국인·와이파이·버스에서 평소와 다른 날을 찾고, 이유 후보를 근거와 함께 보여 주는 프로그램입니다.

[쓰는 순서]
  1. 1_설치.bat 더블클릭 (처음 한 번, 약 3분, 인터넷 필요)
     - 파이썬 3.12가 없으면 내려받기 페이지가 열립니다. 설치할 때 "Add python.exe to PATH"에 체크한 뒤, 1_설치.bat을 다시 더블클릭하세요.
     - Ollama(https://ollama.com/download)가 설치되어 있으면 판단 모델(tev1:4b, 4.6GB)도 자동으로 받습니다.
       없어도 실행되며, 이때 원인 판정과 질문 분류는 규칙 기반으로 동작합니다.
  2. 2_실행.bat 더블클릭 (쓸 때마다)
     - 브라우저에 http://127.0.0.1:8501 화면이 열립니다. 처음에는 30초쯤 걸립니다.
     - 끝낼 때는 검은 창을 닫습니다.

[폴더]
  문서       설치·실행 매뉴얼, 결과 설명서, 기획서, 데이터 활용 명세 (PDF)
  프로그램   실행 소스·데이터·평가 결과 (직접 열 필요 없음, 개발자용 안내는 프로그램/README.md)

[알아 둘 것]
  - 화면은 이 PC에서만 열리고, 분석·질문 중에는 데이터가 밖으로 나가지 않습니다.
  - 원인은 '후보'이며 인과를 뜻하지 않습니다.
  - 문제가 생기면 문서/설치_실행_매뉴얼.pdf 의 '문제 해결' 표를 보세요.
"""

WRAPPER = '@echo off\r\nchcp 65001 >nul\r\ncall "%~dp0프로그램\\{bat}"\r\n'   # 압축을 푼 맨 위에서 프로그램 폴더의 배치 파일을 부른다
DOC_PDFS = {"설치_실행_매뉴얼.pdf": ROOT / "docs" / "설치_실행_매뉴얼.pdf", "결과_설명서.pdf": ROOT / "docs" / "결과_설명서.pdf",
            "데이터_활용_명세.pdf": ROOT / "docs" / "데이터_활용_명세.pdf", PLAN_PDF: ROOT / "기획서" / PLAN_PDF}


def build() -> Path:
    """압축을 풀면 안내 파일, 설치·실행 배치 파일 두 개, 문서·프로그램 폴더만 보이게 만든다."""
    assert OUT.parent == ROOT and OUT.name == "숨비소리"
    if OUT.exists():
        shutil.rmtree(OUT)
    prog = OUT / "프로그램"
    prog.mkdir(parents=True)
    for f in FILES:
        (prog / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, prog / f)
    for d in DIRS:
        for src in (ROOT / d).rglob("*"):
            if src.is_file() and not _skip(src.relative_to(ROOT)):
                dst = prog / src.relative_to(ROOT)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    (OUT / "문서").mkdir()
    for name, src in DOC_PDFS.items():
        shutil.copy2(src, OUT / "문서" / name)
    (OUT / "1_설치.bat").write_bytes(WRAPPER.format(bat="install.bat").encode("utf-8"))
    (OUT / "2_실행.bat").write_bytes(WRAPPER.format(bat="run.bat").encode("utf-8"))
    # 메모장에서 한글이 깨지지 않게 UTF-8 BOM + 윈도 줄바꿈
    (OUT / "0_먼저_읽어주세요.txt").write_bytes(b"\xef\xbb\xbf" + README_TXT.replace("\n", "\r\n").encode("utf-8"))
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
