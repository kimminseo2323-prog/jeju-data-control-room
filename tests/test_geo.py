import pandas as pd

from app.store.geo import EMD_43, assign_emd, haversine_m, normalize_emd


def test_canonical_list_has_43():
    assert len(EMD_43) == 43
    assert "서귀포시 성산읍" in EMD_43


def test_normalize_exact_and_longer_address():
    assert normalize_emd("제주시 삼도1동") == "제주시 삼도1동"
    assert normalize_emd("제주특별자치도 서귀포시 성산읍 성산리") == "서귀포시 성산읍"


def test_normalize_short_eup_name_with_city():
    assert normalize_emd("성산", city="서귀포시") == "서귀포시 성산읍"


def test_normalize_legal_dong_is_not_guessed():
    # 법정동(일도일동)은 행정동 목록에 없으므로 추측하지 않는다
    assert normalize_emd("제주시 일도일동") is None


def test_haversine_known_distance():
    # 위도 0.01도 ≈ 1,112m
    assert abs(haversine_m(33.50, 126.50, 33.51, 126.50) - 1112) < 5


def test_assign_uses_address_then_nearest_reference_and_reports_failures():
    ref = pd.DataFrame({"lat": [33.4996, 33.4580], "lon": [126.5310, 126.9400],
                        "emd": ["제주시 일도1동", "서귀포시 성산읍"]})
    pts = pd.DataFrame({
        "name": ["주소로 매칭", "좌표로 매칭", "멀리 떨어짐", "제주 밖"],
        "address": ["서귀포시 성산읍 고성리", "제주시 일도일동 1", "주소없음", "서울시"],
        "lat": [33.43, 33.4997, 33.30, 37.5],
        "lon": [126.92, 126.5312, 126.20, 127.0],
    })
    res = assign_emd(pts, ref, address_col="address", max_dist_m=2000)
    got = dict(zip(res.assigned["name"], res.assigned["emd"]))
    assert got == {"주소로 매칭": "서귀포시 성산읍", "좌표로 매칭": "제주시 일도1동"}
    assert dict(zip(res.assigned["name"], res.assigned["method"])) == {"주소로 매칭": "address", "좌표로 매칭": "nearest"}
    assert list(res.unmatched["name"]) == ["멀리 떨어짐"]
    assert list(res.out_of_range["name"]) == ["제주 밖"]
