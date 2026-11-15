"""제주 윤곽 지도: 시군구 경계 GeoJSON에서 제주시·서귀포시만 골라 화면용(해안선·두 시 경계)으로 줄인다.

원본: 행정구역 시군구 경계 BND_SIGUNGU_PG(기준일 2024-06-30)를 경위도(WGS84) GeoJSON으로 바꾼 파일
      (사용자의 다른 프로젝트에서 만든 변환본을 data/raw/geo/sigungu.geojson 으로 복사해 씀, 원 출처 확인은 문서 참고).
실행: python -m app.store.jeju_map [원본 geojson]  →  data/geo/jeju_outline.json (화면이 읽는 파일, 수십 KB)

- 바깥 고리만 쓴다(구멍 없음). 넓이가 아주 작은 바위섬 조각은 뺀다(우도·비양도·가파도·추자군도 등은 남김).
- 추자면(본섬 북쪽 약 45km)은 화면에서 본섬 가까이 옮겨 그리므로, 그 조각도 같은 만큼 옮길 수 있게 위도로 구분한다.
- geopandas 없이 표준 json만 쓴다(설치 패키지를 늘리지 않음).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "raw" / "geo" / "sigungu.geojson"
OUT = ROOT / "data" / "geo" / "jeju_outline.json"
JEJU = "제주특별자치도"
CHUJA_LAT = 33.7          # 이 위도보다 북쪽 조각 = 추자군도
MIN_AREA = 1e-6           # 도(°)² 단위. 약 0.01km² 미만 바위섬은 그리지 않는다
SOURCE = "행정구역 시군구 경계 BND_SIGUNGU_PG(기준일 2024-06-30), 경위도 GeoJSON 변환본에서 제주 2개 시만 사용"


def _area(ring: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def build_outline(src: Path | str = SRC) -> dict:
    feats = json.loads(Path(src).read_text("utf-8"))["features"]
    cities = []
    for f in feats:
        p, g = f["properties"], f["geometry"]
        if p.get("SIDO") != JEJU:
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = [[[round(x, 4), round(y, 4)] for x, y in poly[0]] for poly in polys if _area(poly[0]) >= MIN_AREA]
        cities.append({"name": p["SIGUNGU"], "label": [p.get("label_lon"), p.get("label_lat")], "rings": rings})
    cities.sort(key=lambda c: c["name"] != "제주시")   # 제주시, 서귀포시 순
    return {"source": SOURCE, "cities": cities}


def load_outline(path: Path | str = OUT) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def outline_traces(outline: dict, chuja_shift: tuple[float, float] | None = None, include_chuja: bool = True) -> list[dict]:
    """시마다 하나씩 {name, lon, lat} (고리 사이는 None으로 끊음). chuja_shift=(경도, 위도)를 주면 추자 조각을 그만큼 옮기고,
    include_chuja=False면 추자 조각을 빼서 본섬만 크게 그린다."""
    out = []
    for c in outline["cities"]:
        lon, lat = [], []
        for ring in c["rings"]:
            far = sum(y for _, y in ring) / len(ring) > CHUJA_LAT
            if far and not include_chuja:
                continue
            dx, dy = chuja_shift if (far and chuja_shift) else (0.0, 0.0)
            lon += [x + dx for x, _ in ring] + [None]
            lat += [y + dy for _, y in ring] + [None]
        out.append({"name": c["name"], "lon": lon, "lat": lat})
    return out


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    res = build_outline(src)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"{OUT} — " + ", ".join(f"{c['name']} 조각 {len(c['rings'])}개" for c in res["cities"]) + f", {OUT.stat().st_size / 1024:.0f}KB")
