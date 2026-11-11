import pandas as pd
import pytest

from app.agent.tools import ToolError
from app.store.cache import CacheStore


@pytest.fixture
def cache_dir(tmp_path):
    c = tmp_path / "cache"
    c.mkdir()
    pd.DataFrame({"stationId": ["1", "2"], "stationName": ["성산항", "한국병원"],
                  "stationAddress": ["서귀포시 성산읍", "제주시 삼도1동"],
                  "longitude": ["126.93", "126.518"], "latitude": ["33.47", "33.500"]}).to_parquet(c / "bus_stations.parquet")
    pd.DataFrame({"apGroupName": ["성산일출봉", "성산일출봉", "제주시청"], "category": ["관광지", "관광지", "공공기관"],
                  "addressDong": ["제주특별자치도 서귀포시 성산읍 성산리"] * 2 + ["제주특별자치도 제주시 이도2동"],
                  "latitude": ["33.46", "33.461", "33.499"], "longitude": ["126.93", "126.931", "126.531"],
                  "macAddress": ["a", "b", "c"]}).to_parquet(c / "wifi_ap_info.parquet")
    pd.DataFrame({"baseDate": ["20250101", "20250101", "20250102"], "city": ["서귀포시"] * 3, "emd": ["성산읍"] * 3,
                  "gender": ["남", "여", "남"], "ageGroup": ["20대"] * 3, "visitPop": [100, 50, 70]}).to_parquet(c / "pop_domestic.parquet")
    pd.DataFrame({"apGroupName": ["성산일출봉", "제주시청"], "baseDate": ["20250101", "20250101"],
                  "userCount": ["30", "9"]}).to_parquet(c / "wifi_ap_daily.parquet")
    pd.DataFrame({"baseDate": ["20250101", "20250101"], "stationId": ["1", "2"], "userCount": [12, 40]}).to_parquet(c / "bus_station_daily.parquet")
    pd.DataFrame({"observatoryName": ["성산", "제주"], "longitude": ["126.88", "126.53"], "latitude": ["33.39", "33.51"]}).to_parquet(c / "weather_stations.parquet")
    pd.DataFrame({"observatoryName": ["성산"], "baseDate": ["20250101"], "dailyRainfall": ["85.0"], "maximumWindSpeed": ["9.0"]}).to_parquet(c / "weather_daily.parquet")
    return c


def test_population_series_sums_gender_age_and_keeps_gaps(cache_dir):
    s = CacheStore(cache_dir).series("유동인구", "서귀포시 성산읍")
    assert s["2025-01-01"] == 150 and s["2025-01-02"] == 70


def test_wifi_series_maps_ap_group_to_emd(cache_dir):
    st = CacheStore(cache_dir)
    assert st.series("와이파이", "서귀포시 성산읍")["2025-01-01"] == 30
    assert st.series("와이파이", "제주시 이도2동")["2025-01-01"] == 9


def test_bus_series_maps_station_to_emd(cache_dir):
    assert CacheStore(cache_dir).series("버스", "제주시 삼도1동")["2025-01-01"] == 40


def test_unknown_region_raises_tool_error(cache_dir):
    with pytest.raises(ToolError):
        CacheStore(cache_dir).series("버스", "서귀포시 대정읍")


def test_weather_and_station_mapping_for_context(cache_dir):
    st = CacheStore(cache_dir)
    assert st.station_of_emd["서귀포시 성산읍"] == "성산"
    w = st.weather
    assert set(w.columns) >= {"date", "station", "rain_mm", "wind_max"} and w["rain_mm"].iloc[0] == 85.0


def test_data_quality_report_counts_mapping(cache_dir):
    q = CacheStore(cache_dir).quality()
    assert q["wifi_ap_groups"]["mapped"] == 2 and q["bus_stations"]["mapped"] == 2
    assert q["as_of"]["유동인구"] == "2025-01-02"


def test_visitors_monthly_total_sums_purposes(cache_dir):
    pd.DataFrame({"dtYearMonth": ["202407", "202407", "202408"], "visitPurpose": ["개별여행", "패키지", "개별여행"],
                  "visitorCnt": ["100", "50", "200"]}).to_parquet(cache_dir / "visitors_purpose.parquet")
    v = CacheStore(cache_dir).visitors
    assert v[pd.Timestamp("2024-07-01")] == 150 and v[pd.Timestamp("2024-08-01")] == 200


def test_island_series_sums_all_mapped_regions(cache_dir):
    s = CacheStore(cache_dir).island_series("와이파이")
    assert s["2025-01-01"] == 39


def test_events_loaded_from_manual_folder_next_to_cache(cache_dir):
    manual = cache_dir.parent / "manual"
    manual.mkdir()
    pd.DataFrame({"콘텐츠명": ["이호테우축제"], "시작일": ["2024-08-02"], "종료일": ["2024-08-04"]}).to_csv(
        manual / "제주특별자치도주요행사정보.csv", index=False, encoding="cp949")
    st = CacheStore(cache_dir)
    assert st.events["emd"].tolist() == ["제주시 이호동"]


def test_no_event_file_means_empty_events(cache_dir):
    assert CacheStore(cache_dir).events.empty


def test_region_without_bus_stops_uses_wifi_ap_location_for_weather(cache_dir):
    # 이도2동에는 정류소가 없고 AP만 있다(우도면과 같은 경우) → AP 좌표로 가장 가까운 관측소를 정한다
    st = CacheStore(cache_dir)
    assert "제주시 이도2동" not in set(st.stations["emd"])
    assert st.station_of_emd["제주시 이도2동"] == "제주"
    assert st.station_of_emd["서귀포시 성산읍"] == "성산"


def test_bus_usage_ids_differ_so_map_by_unambiguous_station_name(cache_dir):
    # 실제 허브 데이터: 이용자(613) 정류소ID는 7자리, 정류소 정보(612)는 9자리라 ID가 겹치지 않는다 → 이름으로 연결
    pd.DataFrame({"stationId": ["405000001", "405000002", "405000003", "405000004"],
                  "stationName": ["성산항", "한국병원", "시민회관", "시민회관"],
                  "stationAddress": ["서귀포시 성산읍", "제주시 삼도1동", "제주시 이도1동", "제주시 삼도2동"],
                  "longitude": ["126.93", "126.518", "126.53", "126.52"], "latitude": ["33.47", "33.500", "33.51", "33.51"]}
                 ).to_parquet(cache_dir / "bus_stations.parquet")
    pd.DataFrame({"baseDate": ["20250101"] * 4, "stationId": ["6115001", "6115002", "6115003", "6115004"],
                  "stationName": ["성산 항", "한국병원", "시민회관", "없는정류소"], "userCount": [10, 30, 50, 10]}
                 ).to_parquet(cache_dir / "bus_station_daily.parquet")
    st = CacheStore(cache_dir)
    assert st.series("버스", "서귀포시 성산읍")["2025-01-01"] == 10     # 공백 차이는 정규화로 연결
    assert st.series("버스", "제주시 삼도1동")["2025-01-01"] == 30
    q = st.quality()["bus_usage"]   # 이용자 수 기준 비율(%)
    assert q == {"by_id": 0.0, "by_name": 40.0, "ambiguous_name": 50.0, "unmatched": 10.0}
