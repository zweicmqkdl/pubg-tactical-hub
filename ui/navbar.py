"""
PUBG Tactical Hub - 상단 내비게이션 바 및 테마 CSS 모듈 (ui/navbar.py)
- 좌측: PUBG Tactical Hub 로고 및 핵심 기능 배지
- 중앙: config.py의 9개 전장(대형/중형/소형 카테고리) 선택 드롭다운
- 우측: ☀️ 라이트 모드 / 🌙 다크 모드 토글 스위치 및 북마크 버튼
"""

import streamlit as st
from typing import Dict
import config


def inject_theme_css(theme_name: str) -> None:
    """스위치 상태에 따라 config.THEMES 컬러(#0F172A <-> #F8FAFC, 12px 라운딩, #38BDF8 포인트)를 즉시 반영합니다."""
    theme: Dict[str, str] = config.THEMES.get(theme_name, config.THEMES["dark"])

    bg_primary = theme["bg_primary"]
    bg_secondary = theme["bg_secondary"]
    bg_card = theme["bg_card"]
    bg_hover = theme["bg_hover"]
    text_primary = theme["text_primary"]
    text_secondary = theme["text_secondary"]
    border = theme["border"]
    accent = theme["accent"]
    accent_soft = theme["accent_soft"]
    radius = theme["border_radius"]

    css = f"""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {{
        background-color: {bg_primary} !important;
        color: {text_primary} !important;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
    }}

    [data-testid="stHeader"] {{
        background-color: transparent !important;
        height: 0px !important;
    }}

    .block-container {{
        padding-top: 0.75rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }}

    /* 카드 및 컨테이너 공통 스타일 (모서리 12px) */
    .tactical-card {{
        background-color: {bg_card} !important;
        border: 1px solid {border} !important;
        border-radius: {radius} !important;
        padding: 1rem 1.1rem !important;
        margin-bottom: 0.75rem !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14) !important;
    }}

    .navbar-box {{
        background-color: {bg_card} !important;
        border: 1px solid {border} !important;
        border-radius: {radius} !important;
        padding: 0.65rem 1.1rem !important;
        margin-bottom: 0.85rem !important;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}

    /* 버튼 및 인터랙션 요소 */
    div.stButton > button {{
        background-color: {bg_secondary} !important;
        color: {text_primary} !important;
        border: 1px solid {border} !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        transition: all 0.15s ease !important;
    }}
    div.stButton > button:hover {{
        border-color: {accent} !important;
        background-color: {bg_hover} !important;
        color: {accent} !important;
    }}
    div.stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {accent}, #0284C7) !important;
        color: #0F172A !important;
        border: 1px solid {accent} !important;
        font-weight: 800 !important;
    }}

    /* 셀렉트박스, 슬라이더, 토글 라벨 텍스트 컬러 */
    label, .stMarkdown, p, span {{
        color: {text_primary};
    }}
    [data-baseweb="select"] > div {{
        background-color: {bg_secondary} !important;
        border-color: {border} !important;
        border-radius: 10px !important;
        color: {text_primary} !important;
    }}

    .spot-badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 700;
        background: {accent_soft};
        color: {accent};
        border: 1px solid {accent};
    }}

    .muted-text {{
        color: {text_secondary} !important;
        font-size: 0.83rem !important;
    }}

    @media (max-width: 768px) {{
        .block-container {{
            padding-top: 0.45rem !important;
            padding-left: 0.55rem !important;
            padding-right: 0.55rem !important;
        }}
        .tactical-card {{
            padding: 0.65rem 0.75rem !important;
            margin-bottom: 0.45rem !important;
        }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def render_navbar() -> None:
    """상단 내비게이션 바 렌더링 (로고 + 다크/라이트 토글)"""
    theme_name = st.session_state.get("theme", "dark")
    theme = config.THEMES.get(theme_name, config.THEMES["dark"])

    current_map = st.session_state.get("selected_map", "erangel")
    map_meta = config.SUPPORTED_MAPS.get(current_map, config.SUPPORTED_MAPS["erangel"])

    col_logo, col_theme = st.columns([8.2, 1.8], gap="small")

    with col_logo:
        st.markdown(
            f"""
            <div class="tactical-card" style="padding: 0.48rem 0.85rem !important; margin-bottom: 0 !important; display:flex; align-items:center; justify-content:space-between;">
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span style="font-size:1.15rem;">🎯</span>
                    <span style="font-size:1.05rem; font-weight:800; letter-spacing:-0.02em; color:{theme['text_primary']};">
                        PUBG Tactical Hub
                    </span>
                    <span class="spot-badge" style="font-size:0.75rem;">현재 맵: {map_meta['name_ko']} ({map_meta['name_en']})</span>
                    <span class="spot-badge">DBSCAN {config.CLUSTER_RADIUS_METER}m</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_theme:
        is_light = theme_name == "light"
        toggle_label = "☀️ 라이트" if is_light else "🌙 다크"
        toggled = st.toggle(
            toggle_label,
            value=is_light,
            key="theme_toggle_switch",
            help="다크 모드(#0F172A)와 라이트 모드(#F8FAFC) 전환",
        )
        new_theme = "light" if toggled else "dark"
        if new_theme != theme_name:
            st.session_state["theme"] = new_theme
            st.rerun()
