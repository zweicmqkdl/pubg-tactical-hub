"""
PUBG Tactical Hub - 상단 페이즈 바 & 하단 데이터 컨트롤 모듈 (ui/sidebar.py)
모바일 최적화 순서:
- 지도 바로 위: render_phase_bar() -> 자기장 페이즈(P1~P6) 선택만 컴팩트하게 배치
- 지도 바로 아래: render_bottom_controls() -> 점유 확률 필터 + [🏆 프로 선수용 | 👤 일반 유저용 검색] 나란히 배치
"""

import streamlit as st
from typing import Dict, Any
import config


def render_phase_bar(spots_data: Dict[str, Any]) -> None:
    """맵 선택 바로 아래, 지도 바로 위에 배치되는 초컴팩트 P1~P6 페이즈 선택 바."""
    map_id = st.session_state.get("selected_map", "erangel")
    map_meta = config.SUPPORTED_MAPS[map_id]
    size_meter = int(map_meta["size_meter"])
    current_phase = int(st.session_state.get("selected_phase", 3))
    radius_m = int(round(config.PHASE_RADIUS_NORM[current_phase] * size_meter))

    st.caption(f"⏱️ **자기장 페이즈 선택** (`P{current_phase}` · 반경 `{radius_m:,}m`)")
    p_cols = st.columns(6, gap="small")
    for idx, p in enumerate(config.PHASES):
        with p_cols[idx]:
            btn_type = "primary" if p == current_phase else "secondary"
            if st.button(f"P{p}", key=f"phase_btn_{p}", type=btn_type, use_container_width=True):
                st.session_state["selected_phase"] = p
                st.rerun()


def render_bottom_controls(spots_data: Dict[str, Any]) -> None:
    """지도 아래에 배치되는 점유 확률 필터 및 프로 선수용/일반 유저용 데이터 컨트롤."""
    theme_name = st.session_state.get("theme", "dark")
    theme = config.THEMES.get(theme_name, config.THEMES["dark"])
    map_id = st.session_state.get("selected_map", "erangel")
    map_meta = config.SUPPORTED_MAPS[map_id]
    active_profile = st.session_state.get("data_profile", "pro")
    is_pro_missing = spots_data.get("pro_cache_missing", False)
    api_key = config.load_saved_api_key()

    # 1. 점유 확률(%) 필터 & 생존 성향 필터 (생존 명당 vs 위험 교전지)
    fc1, fc2 = st.columns([5.2, 4.8], gap="small")
    with fc1:
        cur_min_prob = int(st.session_state.get("min_prob_filter", 0))
        st.caption(f"📊 **최소 점유 확률 필터** (`{cur_min_prob}% 이상`)")
        f_cols = st.columns(4, gap="small")
        filter_opts = [("전체", 0), ("20%+", 20), ("50%+", 50), ("70%+", 70)]
        for idx, (lbl, val) in enumerate(filter_opts):
            with f_cols[idx]:
                btn_type = "primary" if cur_min_prob == val else "secondary"
                if st.button(lbl, key=f"prob_filter_{val}", type=btn_type, use_container_width=True):
                    st.session_state["min_prob_filter"] = val
                    st.rerun()

    with fc2:
        cur_tier = st.session_state.get("spot_tier_filter", "all")
        st.caption("🛡️ **거점 성향 필터** (Top 4 생존율 기준)")
        t_cols = st.columns(3, gap="small")
        tier_opts = [("전체", "all"), ("🛡️ 생존명당", "safe_spot"), ("⚔️ 킬각교전", "hot_zone")]
        for idx, (lbl, val) in enumerate(tier_opts):
            with t_cols[idx]:
                btn_type = "primary" if cur_tier == val else "secondary"
                if st.button(lbl, key=f"tier_filter_{val}", type=btn_type, use_container_width=True):
                    st.session_state["spot_tier_filter"] = val
                    st.rerun()

    # 1-B. 서버(스배/카배) 및 국가·권역별 반영 데이터 선택 (단독 또는 다중 조합)
    selected_regs = list(st.session_state.get("selected_regions", config.ALL_PRO_REGION_KEYS))
    if not selected_regs:
        selected_regs = list(config.ALL_PRO_REGION_KEYS)
    reg_counts: Dict[str, int] = spots_data.get("region_counts") or {k: 0 for k in config.PRO_REGION_META}
    cur_m = spots_data.get("total_matches", 0)
    all_m = spots_data.get("total_all_region_matches", cur_m)

    is_all_selected = set(selected_regs) >= set(config.ALL_PRO_REGION_KEYS)
    is_steam_only = set(selected_regs) == set(config.STEAM_PRO_REGION_KEYS)
    is_kakao_only = set(selected_regs) == {"kakao"}

    st.caption(
        f"🌏 **반영 데이터 선택 (스배 / 카배 / 국가별 조합)** — "
        f"현재 반영: **{cur_m}판** / 전체 {all_m}판 *(버튼을 눌러 원하는 국가만 보거나 여러 개를 섞어볼 수 있습니다)*"
    )
    preset_cols = st.columns(3, gap="small")
    with preset_cols[0]:
        if st.button(
            "🌐 전체 통합 (스배+카배)",
            key="reg_preset_all",
            type="primary" if is_all_selected else "secondary",
            use_container_width=True,
        ):
            st.session_state["data_profile"] = "pro"
            st.session_state["selected_regions"] = list(config.ALL_PRO_REGION_KEYS)
            st.rerun()
    with preset_cols[1]:
        if st.button(
            "🎮 스배 전체 (Steam)",
            key="reg_preset_steam",
            type="primary" if is_steam_only else "secondary",
            use_container_width=True,
        ):
            st.session_state["data_profile"] = "pro"
            st.session_state["selected_regions"] = list(config.STEAM_PRO_REGION_KEYS)
            st.rerun()
    with preset_cols[2]:
        if st.button(
            "💛 카배 전용 (Kakao)",
            key="reg_preset_kakao",
            type="primary" if is_kakao_only else "secondary",
            use_container_width=True,
        ):
            st.session_state["data_profile"] = "pro"
            st.session_state["selected_regions"] = ["kakao"]
            st.rerun()

    reg_cols = st.columns(len(config.ALL_PRO_REGION_KEYS), gap="small")
    for idx, r_key in enumerate(config.ALL_PRO_REGION_KEYS):
        r_meta = config.PRO_REGION_META[r_key]
        r_cnt = int(reg_counts.get(r_key, 0))
        is_on = r_key in selected_regs
        with reg_cols[idx]:
            if st.button(
                f"{r_meta['label']} ({r_cnt}판)",
                key=f"reg_toggle_{r_key}",
                type="primary" if is_on else "secondary",
                use_container_width=True,
                help="전체 선택 상태에서 누르면 해당 국가만 단독 표시하고, 일부 선택 상태에서 누르면 조합에 추가/제외합니다.",
            ):
                st.session_state["data_profile"] = "pro"
                # 전체가 다 켜진 상태에서 특정 국가 버튼을 누르면 -> 그 국가만 단독 선택!
                # 일부만 켜진 상태에서 누르면 -> 다중 조합(켜기/끄기 토글)으로 동작!
                if is_all_selected:
                    new_regs = [r_key]
                elif is_on and len(selected_regs) == 1:
                    new_regs = list(config.ALL_PRO_REGION_KEYS)
                elif is_on:
                    new_regs = [k for k in selected_regs if k != r_key]
                else:
                    new_regs = selected_regs + [r_key]
                st.session_state["selected_regions"] = new_regs
                st.rerun()

    if spots_data.get("region_empty"):
        st.warning(
            "선택한 서버/국가 조건에 해당하는 매치가 현재 이 맵에 0판입니다. "
            "다른 국가를 함께 선택하거나 **`🔄 선수 최신 매치 추가`** 로 수집해 보세요."
        )

    # 2. 데이터 모드: [🏆 프로 선수용 (좌)] vs [👤 일반 유저용 닉네임 검색 (우)] 나란히 배치
    col_pro, col_user = st.columns([4.6, 5.4], gap="small")

    with col_pro:
        pro_active_badge = "현재 보고 있음 ✅" if active_profile == "pro" else "클릭 시 전환"
        pro_list_str = ", ".join(config.DEFAULT_PRO_PLAYERS)
        total_m = spots_data.get("total_matches", 0) if active_profile == "pro" else "-"

        st.markdown(
            f"""
            <div class="tactical-card" style="padding: 0.65rem 0.85rem !important; margin-bottom: 0.35rem !important;
                 border: {'2px solid ' + theme['accent'] if active_profile == 'pro' else '1px solid ' + theme['border']} !important;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:800; font-size:0.9rem;">🏆 프로 선수용 (기본)</span>
                    <span class="spot-badge" style="font-size:0.68rem;">{pro_active_badge}</span>
                </div>
                <div class="muted-text" style="margin-top:3px; font-size:0.78rem !important;">
                    선수단: <b>{pro_list_str}</b> · 누적 <b>{total_m}판</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        p_b1, p_b2 = st.columns([1.0, 1.3], gap="small")
        with p_b1:
            if st.button(
                "🏆 선수 데이터 보기",
                key="mode_pro_btn",
                type="primary" if active_profile == "pro" else "secondary",
                use_container_width=True,
            ):
                st.session_state["data_profile"] = "pro"
                st.rerun()
        with p_b2:
            if st.button("🔄 선수 최신 매치 추가", key="fetch_pro_btn", use_container_width=True):
                if not api_key:
                    st.error("PUBG API Key(`.env`)가 없습니다.")
                else:
                    st.session_state["data_profile"] = "pro"
                    with st.spinner(f"{map_meta['name_ko']} 프로 매치 수집 중..."):
                        try:
                            from src.pipeline import fetch_real_pubg_telemetry
                            res = fetch_real_pubg_telemetry(
                                api_key=api_key,
                                shard="steam",
                                player_names=config.DEFAULT_PRO_PLAYERS,
                                target_map_id=map_id,
                                max_matches=25,
                                cache_profile="pro",
                            )
                            st.success(f"신규 {res.get('new_matches_added', 0)}판 추가 (총 {res.get('total_matches', 0)}판)")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"수집 오류: {exc}")

    with col_user:
        user_active_badge = "현재 보고 있음 ✅" if active_profile == "user" else "닉네임 검색"
        st.markdown(
            f"""
            <div class="tactical-card" style="padding: 0.65rem 0.85rem !important; margin-bottom: 0.35rem !important;
                 border: {'2px solid ' + theme['accent'] if active_profile == 'user' else '1px solid ' + theme['border']} !important;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:800; font-size:0.9rem;">👤 일반 유저용 검색</span>
                    <span class="spot-badge" style="font-size:0.68rem;">{user_active_badge}</span>
                </div>
                <div class="muted-text" style="margin-top:3px; font-size:0.78rem !important;">
                    Steam/Kakao 토글 후 닉네임(대소문자 구분) 입력
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        u_c1, u_c2, u_c3 = st.columns([1.15, 1.85, 1.0], gap="small")
        with u_c1:
            is_kakao = st.toggle(
                "Kakao",
                value=st.session_state.get("pubg_is_kakao", config.PUBG_SHARD == "kakao"),
                key="pubg_shard_toggle",
                help="OFF: Steam / ON: Kakao",
            )
            st.session_state["pubg_is_kakao"] = is_kakao
            shard_input = "kakao" if is_kakao else "steam"
        with u_c2:
            players_input = st.text_input(
                "유저 닉네임",
                value=st.session_state.get("pubg_player_names", ""),
                placeholder="닉네임 입력 (비우면 샘플)",
                label_visibility="collapsed",
            )
        with u_c3:
            if st.button(
                "🔍 검색",
                key="fetch_user_btn",
                type="primary" if active_profile == "user" else "secondary",
                use_container_width=True,
            ):
                if not api_key:
                    st.error("PUBG API Key(`.env`)가 없습니다.")
                else:
                    st.session_state["data_profile"] = "user"
                    st.session_state["pubg_player_names"] = players_input.strip()
                    player_list = [p.strip() for p in players_input.split(",") if p.strip()] if players_input.strip() else None
                    with st.spinner(f"{map_meta['name_ko']} 유저 매치 검색 중..."):
                        try:
                            from src.pipeline import fetch_real_pubg_telemetry
                            res = fetch_real_pubg_telemetry(
                                api_key=api_key,
                                shard=shard_input,
                                player_names=player_list,
                                target_map_id=map_id,
                                max_matches=25,
                                cache_profile="user",
                            )
                            st.success(f"유저용 {res.get('new_matches_added', 0)}판 추가 (총 {res.get('total_matches', 0)}판)")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"검색 오류: {exc}")

    if active_profile == "pro" and is_pro_missing:
        st.info(f"아직 **{map_meta['name_ko']}** 프로 선수용 캐시가 없습니다. 위 **`🔄 선수 최신 매치 추가`** 버튼을 누르면 즉시 수집됩니다.")
