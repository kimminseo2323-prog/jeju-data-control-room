import random

from app.ingest.union import union_until_stable

TRUE = [{"mac": f"m{i}", "v": i} for i in range(250)]


def unstable_fetch_factory(seed=0):
    """매번 순서가 바뀌는 페이지네이션 흉내: 전체 중 일부만, 일부는 중복으로 돌려줌."""
    rng = random.Random(seed)

    def fetch():
        picked = [rng.choice(TRUE) for _ in range(len(TRUE))]  # 복원 추출 → 빠짐·중복 발생
        return picked
    return fetch


def test_union_recovers_all_rows_from_unstable_source():
    rows, rounds = union_until_stable(unstable_fetch_factory(), key=lambda r: r["mac"], max_rounds=20, stable_rounds=2)
    assert len(rows) == 250 and rounds <= 20


def test_union_stops_early_when_source_is_stable():
    rows, rounds = union_until_stable(lambda: list(TRUE), key=lambda r: r["mac"], max_rounds=10, stable_rounds=2)
    assert len(rows) == 250 and rounds == 3  # 1회차로 다 받고, 2·3회차에 새 행 없음
