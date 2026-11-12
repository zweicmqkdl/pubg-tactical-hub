"""
PUBG Tactical Hub - 메인 Streamlit 애플리케이션 엔트리포인트 (app.py)
핵심 기능:
- 특정 자기장 페이즈(P1~P6)와 중심 좌표가 주어졌을 때,
  자기장 내부의 주요 포인트들마다 스쿼드가 자리 잡고 있을 점유 확률(%)을 계산해서 시각화
- 마우스 드래그를 통한 자기장 원 실시간 이동 및 2048x2048 고화질 맵 줌인/줌아웃 지원
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

import streamlit as st

import config
from src.pipeline import run_pipeline, calculate_spot_probabilities
from ui.navbar import inject_theme_css, render_navbar
from ui.sidebar import render_phase_bar, render_bottom_controls
from ui.map_canvas import render_map_canvas


st.set_page_config(
    page_title="PUBG Tactical Hub - 스쿼드 점유 확률 분석기",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _init_session_state() -> None:
    """초기 세션 상태를 설정합니다."""
    if "theme" not in st.session_state:
        st.session_state["theme"] = "dark"
    if "selected_map" not in st.session_state:
        st.session_state["selected_map"] = "erangel"
    if "selected_phase" not in st.session_state:
        st.session_state["selected_phase"] = 3
    if "min_prob_filter" not in st.session_state:
        st.session_state["min_prob_filter"] = 0

    map_meta = config.SUPPORTED_MAPS[st.session_state["selected_map"]]
    default_cx, default_cy = map_meta["default_zone_center"]

    if "zone_center_x_norm" not in st.session_state:
        st.session_state["zone_center_x_norm"] = default_cx
    if "zone_center_y_norm" not in st.session_state:
        st.session_state["zone_center_y_norm"] = default_cy
    if "bookmarks" not in st.session_state:
        st.session_state["bookmarks"] = []
    if "data_profile" not in st.session_state:
        st.session_state["data_profile"] = "pro"
    if "selected_regions" not in st.session_state:
        st.session_state["selected_regions"] = list(config.ALL_PRO_REGION_KEYS)


@st.cache_data(show_spinner=False)
def _compute_filtered_pro_spots(
    map_id: str,
    regions_key: Tuple[str, ...],
    raw_mtime: float,
) -> Dict[str, Any] | None:
    """선택된 서버/권역(카배, 스배 지역별) 매치만 필터링하여 거점 점유 확률 및 생존율을 동적 산출합니다."""
    raw_pro_path = config.DATA_RAW_DIR / f"{map_id}_pro_matches.json"
    if not raw_pro_path.exists():
        return None
    with open(raw_pro_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    all_matches = bundle.get("matches", [])
    if not all_matches:
        return None

    region_counts: Dict[str, int] = {k: 0 for k in config.PRO_REGION_META}
    for m in all_matches:
        r = m.get("region", "as")
        if r in region_counts:
            region_counts[r] += 1
        if r == "sea":
            region_counts["oc"] += 1

    eff_regions = set(regions_key)
    if "oc" in eff_regions:
        eff_regions.add("sea")

    filtered: List[Dict[str, Any]] = []
    for m in all_matches:
        r = m.get("region", "as")
        if r in eff_regions:
            m_copy = dict(m)
            m_copy["match_index"] = len(filtered)
            filtered.append(m_copy)

    if not filtered:
        map_meta = config.SUPPORTED_MAPS.get(map_id, config.SUPPORTED_MAPS["erangel"])
        return {
            "map_id": map_id,
            "map_name_ko": map_meta["name_ko"],
            "map_name_en": map_meta["name_en"],
            "data_source": "real_pubg_api",
            "cache_profile": "pro",
            "total_matches": 0,
            "total_all_region_matches": len(all_matches),
            "region_counts": region_counts,
            "selected_regions": list(regions_key),
            "region_empty": True,
            "total_spots": 0,
            "spots": [],
        }

    sub_bundle = dict(bundle)
    sub_bundle["matches"] = filtered
    sub_bundle["num_matches"] = len(filtered)
    spots_data = calculate_spot_probabilities(sub_bundle)
    spots_data["cache_profile"] = "pro"
    spots_data["total_all_region_matches"] = len(all_matches)
    spots_data["region_counts"] = region_counts
    spots_data["selected_regions"] = list(regions_key)
    return spots_data


def _load_spots_data(map_id: str, profile: str = "pro") -> Dict[str, Any]:
    """선택된 프로필(pro/user) 및 서버·국가 필터에 맞는 거점 데이터를 로드합니다."""
    map_meta = config.SUPPORTED_MAPS.get(map_id, config.SUPPORTED_MAPS["erangel"])
    if profile == "pro":
        selected_regs = st.session_state.get("selected_regions", list(config.ALL_PRO_REGION_KEYS))
        if not selected_regs:
            selected_regs = list(config.ALL_PRO_REGION_KEYS)
        reg_tuple = tuple(sorted(set(selected_regs)))
        raw_pro_path = config.DATA_RAW_DIR / f"{map_id}_pro_matches.json"
        pro_path = config.DATA_PROCESSED_DIR / f"{map_id}_pro_spots.json"

        # 전체 권역 선택 시 사전 계산된 pro_spots.json 즉시 반환
        if set(reg_tuple) >= set(config.ALL_PRO_REGION_KEYS) and pro_path.exists():
            with open(pro_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "region_counts" not in data and raw_pro_path.exists():
                try:
                    with open(raw_pro_path, "r", encoding="utf-8") as rf:
                        rb = json.load(rf)
                    rc = {k: 0 for k in config.PRO_REGION_META}
                    for m in rb.get("matches", []):
                        r = m.get("region", "as")
                        if r in rc:
                            rc[r] += 1
                        if r == "sea":
                            rc["oc"] += 1
                    data["region_counts"] = rc
                except Exception:
                    pass
            data["selected_regions"] = list(reg_tuple)
            data["total_all_region_matches"] = data.get("total_matches", 0)
            return data

        # 일부 서버/권역만 선택 시 raw_pro_path에서 동적 필터링
        if raw_pro_path.exists() and pro_path.exists():
            filtered_data = _compute_filtered_pro_spots(
                map_id=map_id,
                regions_key=reg_tuple,
                raw_mtime=raw_pro_path.stat().st_mtime,
            )
            if filtered_data is not None:
                return filtered_data

        if pro_path.exists():
            with open(pro_path, "r", encoding="utf-8") as f:
                return json.load(f)

    processed_path = Path(map_meta["processed_file"])
    if not processed_path.exists():
        run_pipeline()
    with open(processed_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if profile == "pro":
        data["pro_cache_missing"] = True
    return data


def main() -> None:
    _init_session_state()
    inject_theme_css(st.session_state["theme"])
    render_navbar()

    map_id = st.session_state["selected_map"]
    profile = st.session_state.get("data_profile", "pro")
    spots_data = _load_spots_data(map_id, profile=profile)

    render_phase_bar(spots_data)
    render_map_canvas(spots_data)
    render_bottom_controls(spots_data)


if __name__ == "__main__":
    main()
