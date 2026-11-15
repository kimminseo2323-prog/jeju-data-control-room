"""제주 지도: 행정동 경계 GeoJSON에서 제주 읍면동 43곳만 골라 화면용으로 줄인다.
관제판 '어디서' 지도와 상세 탭 위치 지도에서 동마다 칠한다.

실행: python -m app.store.jeju_map  →  data/geo/jeju_emd.json (화면이 읽는 파일, 약 50KB)
원본: 행정동 경계 admdongkor ver20260701(vuski/admdongkor, 통계청 SGIS 행정동 경계 기반,
      공공누리 제1유형 + CC BY 4.0, 출처 표시). data/raw/geo/HangJeongDong_ver20260701.geojson 으로 받아 둠.

- 바깥 고리만 쓴다(구멍 없음). 넓이가 아주 작은 바위섬 조각은 뺀다(우도·비양도·가파도·추자군도 등은 남김).
- 추자면(본섬 북쪽 약 45km)은 화면에서 본섬 가까이 옮겨 그리므로, 대표점의 위도로 구분해 같은 만큼 옮길 수 있게 한다.
- 11/15 이전에 쓰던 시군구 윤곽(다른 프로젝트의 BND_SIGUNGU_PG 변환본, 원 출처·이용조건 미확인)은 읍면동 경계로 바꾸면서 뺐다.
- geopandas 없이 표준 json만 쓴다(설치 패키지를 늘리지 않음).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JEJU = "제주특별자치도"
CHUJA_LAT = 33.7          # 이 위도보다 북쪽 조각 = 추자군도
MIN_AREA = 1e-6           # 도(°)² 단위. 약 0.01km² 미만 바위섬은 그리지 않는다
EMD_SRC = ROOT / "data" / "raw" / "geo" / "HangJeongDong_ver20260701.geojson"
EMD_OUT = ROOT / "data" / "geo" / "jeju_emd.json"
EMD_SOURCE = ("행정동 경계 admdongkor ver20260701 (github.com/vuski/admdongkor, 통계청 SGIS 행정동 경계 기반, "
              "공공누리 제1유형·CC BY 4.0), 제주 43개 읍면동만 단순화해 사용")
EMD_TOL = 0.0006          # 단순화 허용 오차(도). 약 60m — 화면 지도에서는 차이가 보이지 않는다


def _area(ring: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def _simplify(pts: list, tol: float) -> list:
    """Douglas-Peucker. 첫 점과 끝 점은 남긴다."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = (dx * dx + dy * dy) ** 0.5
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / n if n else ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def _simplify_ring(ring: list, tol: float) -> list:
    """닫힌 고리는 시작점과 가장 먼 점에서 둘로 나눠 단순화한다(시작=끝이라 한 번에 하면 다 지워짐)."""
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    out = _simplify(ring[:far + 1], tol)[:-1] + _simplify(ring[far:], tol)
    if len(out) < 4:    # 너무 줄면 원래 점에서 고르게 뽑는다
        step = max(1, (len(ring) - 1) // 3)
        out = ring[:-1:step][:3] + [ring[0]]
    return out


def _centroid(ring: list) -> list:
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        c = x1 * y2 - x2 * y1
        a, cx, cy = a + c, cx + (x1 + x2) * c, cy + (y1 + y2) * c
    if not a:
        return [sum(x for x, _ in ring) / len(ring), sum(y for _, y in ring) / len(ring)]
    return [round(cx / (3 * a), 4), round(cy / (3 * a), 4)]


def build_emd(src: Path | str = EMD_SRC, tol: float = EMD_TOL) -> dict:
    """제주 읍면동 경계 → {"source", "emd": [{"name": "제주시 한림읍", "rings": [...], "label": [경도, 위도]}]} (이름순).
    이름은 우리 데이터의 읍면동 이름(시 + 읍면동)과 같게 시도 이름을 뗀다. label = 가장 큰 조각의 무게중심."""
    feats = json.loads(Path(src).read_text("utf-8"))["features"]
    out = []
    for f in feats:
        p, g = f["properties"], f["geometry"]
        if p.get("sidonm") != JEJU:
            continue
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        outer = [poly[0] for poly in polys if _area(poly[0][:-1]) >= MIN_AREA]
        big = max(outer, key=lambda r: _area(r[:-1]))
        rings = [[[round(x, 4), round(y, 4)] for x, y in _simplify_ring(r, tol)] for r in outer]
        out.append({"name": p["adm_nm"].replace(JEJU + " ", ""), "rings": rings, "label": _centroid(big)})
    return {"source": EMD_SOURCE, "emd": sorted(out, key=lambda e: e["name"])}


def emd_shapes(emd: dict, chuja_shift: tuple[float, float] | None = None, include_chuja: bool = True) -> dict:
    """{읍면동: {lon, lat (고리 사이 None), label}}. 추자면(대표점이 CHUJA_LAT 북쪽)은 chuja_shift만큼 옮기거나 뺀다."""
    out = {}
    for e in emd["emd"]:
        far = e["label"][1] > CHUJA_LAT
        if far and not include_chuja:
            continue
        dx, dy = chuja_shift if (far and chuja_shift) else (0.0, 0.0)
        lon, lat = [], []
        for ring in e["rings"]:
            lon += [x + dx for x, _ in ring] + [None]
            lat += [y + dy for _, y in ring] + [None]
        out[e["name"]] = {"lon": lon, "lat": lat, "label": [e["label"][0] + dx, e["label"][1] + dy]}
    return out


def load_emd(path: Path | str = EMD_OUT) -> dict | None:
    p = Path(path)
    return json.loads(p.read_text("utf-8")) if p.exists() else None


if __name__ == "__main__":
    EMD_OUT.parent.mkdir(parents=True, exist_ok=True)
    emd = build_emd(EMD_SRC)
    EMD_OUT.write_text(json.dumps(emd, ensure_ascii=False, separators=(",", ":")), "utf-8")
    pts = sum(len(r) for e in emd["emd"] for r in e["rings"])
    print(f"{EMD_OUT} — 읍면동 {len(emd['emd'])}곳, 점 {pts}개, {EMD_OUT.stat().st_size / 1024:.0f}KB")
