"""설정: 프로젝트 폴더의 .env를 읽는다(없으면 환경변수·기본값만 사용). 키 값은 출력하지 않는다."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env", override=False)
