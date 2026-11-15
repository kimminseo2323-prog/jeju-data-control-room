"""제주 읍면동(행정동) 경계 지도: 원본 GeoJSON에서 제주 43곳만 골라 화면용으로 줄인다."""
import json

from app.store.jeju_map import CHUJA_LAT


def _square(lon, lat, d):
    return [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]



def _wiggly(lon, lat, d, n=200):
    """점이 많은 사각형(변마다 잔물결) — 단순화하면 점 수가 줄어야 한다."""
    import math
    pts = []
    for k in range(n):
        t = k / n * 4
        side, f = int(t), t - int(t)
        x, y = [(lon + d * f, lat), (lon + d, lat + d * f), (lon + d - d * f, lat + d), (lon, lat + d - d * f)][side]
        pts.append([x + 1e-5 * math.sin(k), y + 1e-5 * math.cos(k)])
    return [pts + [pts[0]]]


def _emd_src(tmp_path):
    feats = [
        {"type": "Feature", "properties": {"adm_nm": "제주특별자치도 제주시 한림읍", "sidonm": "제주특별자치도"},
         "geometry": {"type": "MultiPolygon", "coordinates": [_wiggly(126.2, 33.35, 0.1)]}},
        {"type": "Feature", "properties": {"adm_nm": "제주특별자치도 제주시 추자면", "sidonm": "제주특별자치도"},
         "geometry": {"type": "MultiPolygon", "coordinates": [_square(126.3, 33.95, 0.02)]}},
        {"type": "Feature", "properties": {"adm_nm": "서울특별시 종로구 사직동", "sidonm": "서울특별시"},
         "geometry": {"type": "MultiPolygon", "coordinates": [_square(127.0, 37.5, 0.01)]}},
    ]
    p = tmp_path / "emd.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), "utf-8")
    return p


def test_emd_keeps_jeju_with_our_names(tmp_path):
    from app.store.jeju_map import build_emd
    out = build_emd(_emd_src(tmp_path))
    assert [e["name"] for e in out["emd"]] == ["제주시 추자면", "제주시 한림읍"]


def test_emd_rings_are_simplified_but_closed(tmp_path):
    from app.store.jeju_map import build_emd
    ring = next(e for e in build_emd(_emd_src(tmp_path))["emd"] if e["name"] == "제주시 한림읍")["rings"][0]
    assert 4 <= len(ring) < 50 and ring[0] == ring[-1]


def test_emd_label_point_is_inside_the_area(tmp_path):
    from app.store.jeju_map import build_emd
    e = next(e for e in build_emd(_emd_src(tmp_path))["emd"] if e["name"] == "제주시 한림읍")
    assert 126.2 < e["label"][0] < 126.3 and 33.35 < e["label"][1] < 33.45


def test_emd_shapes_move_chuja(tmp_path):
    from app.store.jeju_map import build_emd, emd_shapes
    shapes = emd_shapes(build_emd(_emd_src(tmp_path)), chuja_shift=(0.1, -0.4))
    chuja = shapes["제주시 추자면"]
    assert max(y for y in chuja["lat"] if y is not None) < CHUJA_LAT and chuja["label"][1] < CHUJA_LAT
    assert "제주시 추자면" not in emd_shapes(build_emd(_emd_src(tmp_path)), include_chuja=False)
