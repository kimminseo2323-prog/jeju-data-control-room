import pandas as pd

from app.store.events import EVENT_MAX_DAYS, load_events


def _csv(tmp_path, rows):
    p = tmp_path / "events.csv"
    pd.DataFrame(rows, columns=["콘텐츠명", "시작일", "종료일"]).to_csv(p, index=False, encoding="cp949")
    return p


def test_place_name_in_title_maps_to_region(tmp_path):
    ev = load_events(_csv(tmp_path, [("이호테우축제", "2024-08-02", "2024-08-04"), ("제13회 우도소라축제", "2024-04-26", "2024-04-28")]))
    assert dict(zip(ev["name"], ev["emd"])) == {"이호테우축제": "제주시 이호동", "제13회 우도소라축제": "제주시 우도면"}
    assert ev["start"].dtype.kind == "M"


def test_cancelled_long_and_placeless_events_are_dropped(tmp_path):
    ev = load_events(_csv(tmp_path, [
        ("성산일출축제(2024년 취소)", "2024-12-31", "2025-01-01"),     # 취소
        ("한림공원 연꽃축제", "2024-07-19", "2024-08-31"),               # 7일 초과
        ("휴애리 유럽 수국축제", "2024-07-19", "2024-07-21"),            # 이름에 지명 없음
        ("2024 중문데이", "2024-11-15", "2024-11-16"),
    ]))
    assert ev["name"].tolist() == ["2024 중문데이"] and EVENT_MAX_DAYS == 7


def test_ambiguous_word_is_not_a_place(tmp_path):
    # '중앙'·'천지' 같은 일반 단어는 지명으로 보지 않는다
    assert load_events(_csv(tmp_path, [("중앙 무대 공연", "2024-05-01", "2024-05-01")])).empty


def test_missing_file_gives_empty_frame(tmp_path):
    ev = load_events(tmp_path / "none.csv")
    assert ev.empty and list(ev.columns) == ["name", "start", "end", "emd"]


def test_place_name_inside_another_word_is_not_matched():
    from app.store.events import place_of
    assert place_of("월대천 축제") is None            # 월대천(외도동)의 '대천' ≠ 대천동
    assert place_of("이호테우축제") == "제주시 이호동"  # 이름 맨 앞
    assert place_of("제3회 조천리용천수 축제") == "제주시 조천읍"
