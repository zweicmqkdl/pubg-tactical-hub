"""
PUBG Tactical Hub - 메인 Streamlit 애플리케이션 엔트리포인트 (app.py)
핵심 기능:
- 특정 자기장 페이즈(P1~P6)와 중심 좌표가 주어졌을 때,
  자기장 내부의 주요 포인트들마다 스쿼드가 자리 잡고 있을 점유 확률(%)을 계산해서 시각화
- 마우스 드래그를 통한 자기장 원 실시간 이동 및 2048x2048 고화질 맵 줌인/줌아웃 지원
"""

import json
from pathlib import Path
from typing import Dict, Any

import streamlit as st

import config
from src.pipeline import run_pipeline
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


def _load_spots_data(map_id: str, profile: str = "pro") -> Dict[str, Any]:
    """선택된 프로필(pro/user)에 맞는 processed JSON 파일을 로드합니다."""
    map_meta = config.SUPPORTED_MAPS.get(map_id, config.SUPPORTED_MAPS["erangel"])
    if profile == "pro":
        pro_path = config.DATA_PROCESSED_DIR / f"{map_id}_pro_spots.json"
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
