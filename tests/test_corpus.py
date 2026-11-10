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
