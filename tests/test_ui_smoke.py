"""화면 스모크 테스트: 수집 캐시가 있을 때 앱 전체를 한 번 실행해 예외가 없는지 본다(약 15초)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "cache" / "pop_domestic.parquet").exists(), reason="수집 캐시 없음")


def test_app_renders_all_tabs_without_exceptions():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "ui" / "app.py"), default_timeout=180).run()
    assert not at.exception, [e.message for e in at.exception]
    assert [t.label.split(": ")[-1] for t in at.tabs] == ["관제판", "상세 분석·브리핑", "질문하기", "데이터 품질"]
    assert any(c.value.startswith("원인 판정 모델:") for c in at.sidebar.caption)


def test_switching_signal_after_using_board_does_not_crash():
    """관제판에서 상세 보기를 누르거나 상세 구간을 고른 뒤 신호를 바꿔도 오류가 나지 않아야 한다(2026-11-13 화면에서 TypeError)."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app" / "ui" / "app.py"), default_timeout=300).run()
    go = [b for b in at.button if b.label == "상세 분석 보기"]
    if go:
        go[0].click().run()
    assert not at.exception, [e.message for e in at.exception]
    pick = next(s for s in at.selectbox if s.label.startswith("이상 구간"))
    pick.select_index(min(2, len(pick.options) - 1)).run()
    at.sidebar.selectbox[0].set_value("와이파이").run()
    assert not at.exception, [e.message for e in at.exception]
    at.sidebar.selectbox[0].set_value("외국인").run()
    assert not at.exception, [e.message for e in at.exception]
