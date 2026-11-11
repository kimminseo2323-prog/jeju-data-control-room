from app.rag.index import Passage, build_index, chunk_text


DOCS = [
    {"doc_id": "api_583", "title": "읍면동 단위 내국인 유동인구 API 가이드", "locator": "허브 데이터 583 기술문서",
     "text": "resdPop 거주인구 workPop 근무인구 visitPop 방문자수. 하루 동안 거주·근무·방문 시간대로 설정된 시간대별 인구를 더한 값입니다. 단위는 명이며 연인원 성격입니다."},
    {"doc_id": "api_613", "title": "일일 정류소별 버스 이용자 정보 API 가이드", "locator": "허브 데이터 613 기술문서",
     "text": "stationId 정류소ID stationName 정류소명 moveType 승차 환승 userCount 이용자수. 페이지당 최대 100행."},
    {"doc_id": "export_rule", "title": "제주빅데이터센터 데이터 반출 기준", "locator": "허브 공지 48",
     "text": "단순집계 결과는 10 미만 값이 없을 때 반출할 수 있습니다. 역산이 가능한 경우 반출이 제한됩니다."},
    {"doc_id": "weather", "title": "일별 기상 정보 API 가이드", "locator": "허브 데이터 579 기술문서",
     "text": "averageTemperature 평균기온 dailyRainfall 일일강수량 maximumWindSpeed 최대풍속 관측소명."},
]


def test_visitpop_unit_query_finds_population_doc_top3():
    idx = build_index(DOCS)
    hits = idx.search("visitPop 단위가 뭐야? 방문인구는 어떻게 계산돼?", k=3)
    assert "api_583" in [h.doc_id for h in hits]
    assert hits[0].doc_id == "api_583"


def test_export_rule_query():
    hits = build_index(DOCS).search("10 미만 값 반출 가능해?", k=3)
    assert hits[0].doc_id == "export_rule"


def test_every_passage_has_locator_and_score():
    hits = build_index(DOCS).search("버스 정류소 이용자", k=5)
    assert hits and all(isinstance(h, Passage) and h.locator and h.score > 0 for h in hits)


def test_unrelated_query_returns_nothing_with_positive_score():
    assert build_index(DOCS).search("양자역학 슈뢰딩거", k=3) == []


def test_chunk_text_splits_long_text_with_overlap():
    text = "가" * 1200
    chunks = chunk_text(text, size=500, overlap=50)
    assert len(chunks) == 3 and all(len(c) <= 500 for c in chunks)


def test_title_match_outranks_boilerplate_in_many_short_docs():
    """명세서 시트마다 '반출' 칸이 있어도, 제목이 '반출 기준'인 문서가 먼저 나와야 한다."""
    sheets = [{"doc_id": f"spec_{i}", "title": f"명세서 — 재무정보 {i}", "locator": f"시트 {i}",
               "text": f"설명 기간 2019년 기준 본 데이터는 가공 형태로만 반출 가능합니다 반출 데이터 반출 불가능 항목{i}"} for i in range(30)]
    policy = {"doc_id": "policy", "title": "데이터 반출 기준", "locator": "공지 48",
              "text": "통계 결과물은 10 미만 값을 마스킹해야 반출할 수 있습니다. 역산 가능하면 제한됩니다. " * 3}
    hits = build_index(sheets + [policy]).search("반출 가능한 데이터 기준이 뭐야?", k=3)
    assert hits[0].doc_id == "policy"


def test_one_passage_per_document():
    long = {"doc_id": "long", "title": "버스 승하차 명세", "locator": "시트", "text": "버스 승하차 카드 " * 400}
    hits = build_index(DOCS + [long]).search("버스 승하차 카드", k=3)
    ids = [h.doc_id for h in hits]
    assert len(ids) == len(set(ids))
