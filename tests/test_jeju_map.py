"""제주 윤곽(시군구 경계) 지도: 원본 GeoJSON에서 제주 2개 시만 골라 화면용으로 줄인다."""
import json

from app.store.jeju_map import CHUJA_LAT, build_outline, outline_traces


def _square(lon, lat, d):
    return [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]


def _src(tmp_path):
    feats = [
        {"type": "Feature", "properties": {"SIDO": "제주특별자치도", "SIGUNGU": "제주시", "label_lon": 126.48, "label_lat": 33.42},
         "geometry": {"type": "MultiPolygon", "coordinates": [_square(126.3, 33.3, 0.3),          # 본섬 북쪽
                                                               _square(126.95, 33.5, 0.03),        # 우도
                                                               _square(126.3, 33.95, 0.02),        # 추자도
                                                               _square(126.6, 33.6, 0.0005)]}},    # 아주 작은 바위섬
        {"type": "Feature", "properties": {"SIDO": "제주특별자치도", "SIGUNGU": "서귀포시", "label_lon": 126.59, "label_lat": 33.33},
         "geometry": {"type": "MultiPolygon", "coordinates": [_square(126.3, 33.2, 0.3)]}},
        {"type": "Feature", "properties": {"SIDO": "서울특별시", "SIGUNGU": "종로구", "label_lon": 127.0, "label_lat": 37.5},
         "geometry": {"type": "Polygon", "coordinates": _square(127.0, 37.5, 0.05)}},
    ]
    p = tmp_path / "sigungu.geojson"
    p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), "utf-8")
    return p


def test_outline_keeps_only_jeju_cities(tmp_path):
    out = build_outline(_src(tmp_path))
    assert [c["name"] for c in out["cities"]] == ["제주시", "서귀포시"]


def test_outline_keeps_islands_but_drops_specks(tmp_path):
    jeju = build_outline(_src(tmp_path))["cities"][0]
    assert len(jeju["rings"]) == 3     # 본섬 조각·우도·추자도는 남기고 아주 작은 바위섬은 뺀다


def test_chuja_rings_move_with_the_marker(tmp_path):
    out = build_outline(_src(tmp_path))
    shift = (0.1, -0.4)                            # (경도, 위도): 남쪽으로 0.4도
    lats = [y for tr in outline_traces(out, chuja_shift=shift) for y in tr["lat"] if y is not None]
    assert max(lats) < CHUJA_LAT                     # 추자 조각도 표시 위치로 옮겨져 본섬 근처에 그려진다


def test_chuja_can_be_left_out(tmp_path):
    out = build_outline(_src(tmp_path))
    lats = [y for tr in outline_traces(out, include_chuja=False) for y in tr["lat"] if y is not None]
    assert max(lats) < CHUJA_LAT
