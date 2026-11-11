from app.rag.corpus import load_corpus


def test_load_corpus_reads_txt_sources_and_md_sections(tmp_path):
    src = tmp_path / "docs" / "sources"
    src.mkdir(parents=True)
    (src / "583.txt").write_text("출처: https://jejudatahub.net/data/view/data/583\n유동인구 본문", "utf-8")
    (tmp_path / "02_게시판_QA정리.md").write_text("# 제목\n서문\n## 1. 데이터 범위\n답변 A\n## 2. 접근\n답변 B\n", "utf-8")
    docs = load_corpus(tmp_path, spec_xlsx=None)
    by_id = {d["doc_id"]: d for d in docs}
    assert by_id["src:583"]["locator"] == "https://jejudatahub.net/data/view/data/583"
    assert by_id["src:583"]["text"] == "유동인구 본문"
    assert by_id["board:1. 데이터 범위"]["text"].strip() == "답변 A"
    assert by_id["board:2. 접근"]["locator"].startswith("대회 게시판 공식 답변")


def test_own_docs_are_searchable_by_section(tmp_path):
    """우리 데이터 활용 명세·설치 매뉴얼도 검색 대상(절 단위). '버스 데이터 어디서?'의 답이 여기에 있다."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "데이터_활용_명세.md").write_text("# 데이터 활용 명세\n## 1. 한눈에 보기\n버스는 613\n## 2. 수집 현황\n표\n", "utf-8")
    (tmp_path / "docs" / "설치_실행_매뉴얼.md").write_text("# 설치\n## 문제 해결\n연결 안 됨\n", "utf-8")
    by_id = {d["doc_id"]: d for d in load_corpus(tmp_path, spec_xlsx=None)}
    d = by_id["md:데이터_활용_명세§1. 한눈에 보기"]
    assert d["text"].strip() == "버스는 613"
    assert d["title"] == "데이터 활용 명세 — 1. 한눈에 보기"
    assert d["locator"] == "docs/데이터_활용_명세.md §1. 한눈에 보기"
    assert "md:설치_실행_매뉴얼§문제 해결" in by_id


def test_hub_page_title_is_dataset_name_not_author(tmp_path):
    src = tmp_path / "docs" / "sources" / "hub_api"
    src.mkdir(parents=True)
    (src / "613.txt").write_text("출처: https://jejudatahub.net/data/view/data/613\n관리자\n인증 [교통, 안전] 일일 정류소별 버스 이용자 정보\n본문", "utf-8")
    d = load_corpus(tmp_path, spec_xlsx=None)[0]
    assert d["title"] == "허브 데이터 — 일일 정류소별 버스 이용자 정보"
