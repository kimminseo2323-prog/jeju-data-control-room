"""화면 스모크 테스트: 수집 캐시가 있을 때 앱 전체를 한 번 실행해 예외가 없는지 본다(약 15초)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "cache" / "pop_domestic.parquet").exists(), reason="수집 캐시 없음")


def test_app_renders_all_tabs_without_exceptions():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "ui" / "app.py"), default_timeout=180).run()
    assert not at.exception, [e.message for e in at.exception]
    assert [t.label for t in at.tabs] == ["관제판", "상세 분석·브리핑", "질문하기", "데이터 품질"]
    assert any(c.value.startswith("원인 판정 모델:") for c in at.sidebar.caption)
