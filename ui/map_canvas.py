"""
PUBG Tactical Hub - 인터랙티브 2D 전술 맵 및 실시간 점유 확률 캔버스 (ui/map_canvas.py)
핵심 기능:
1. 2048x2048 고해상도 공식 맵 이미지 + High-DPI 벡터 렌더링 (확대 시 흐릿함 방지)
2. 마우스 드래그로 하얀색 자기장 원 위치 실시간 이동 (60fps 반응)
3. 마우스 휠로 커서 중심 줌인/줌아웃 (1.0x ~ 8.0x) 및 우클릭/외곽 드래그 팬(Pan) 이동
4. 자기장 원 내부에 들어온 거점들의 스쿼드 점유 확률(%) = (고착 매치 수 / 유사 자기장 매치 수) * 100 실시간 계산 및 표시
"""

import base64
import json
from pathlib import Path
from typing import Dict, Any

import streamlit as st
import streamlit.components.v1 as components

import config


@st.cache_data(show_spinner=False)
def _get_map_image_data_uri(image_path_str: str) -> str:
    """고해상도 맵 이미지를 Base64 Data URI로 인코딩하여 캐싱합니다."""
    path = Path(image_path_str)
    if not path.exists():
        return ""
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def render_map_canvas(spots_data: Dict[str, Any]) -> None:
    """
    마우스로 자기장 원을 직접 드래그하고 줌인/줌아웃할 수 있는 고화질 전술 맵과
    자기장 내부 스팟 점유 확률(%) 실시간 랭킹 보드를 렌더링합니다.
    """
    theme_name = st.session_state.get("theme", "dark")
    theme = config.THEMES.get(theme_name, config.THEMES["dark"])

    map_id = st.session_state.get("selected_map", "erangel")
    map_meta = config.SUPPORTED_MAPS[map_id]
    phase = int(st.session_state.get("selected_phase", 3))
    min_prob_filter = float(st.session_state.get("min_prob_filter", 0))
    tier_filter = st.session_state.get("spot_tier_filter", "all")

    cx_norm = float(st.session_state.get("zone_center_x_norm", map_meta["default_zone_center"][0]))
    cy_norm = float(st.session_state.get("zone_center_y_norm", map_meta["default_zone_center"][1]))

    img_data_uri = _get_map_image_data_uri(map_meta["map_image_file"])

    payload = {
        "mapId": map_id,
        "mapNameKo": map_meta["name_ko"],
        "mapNameEn": map_meta["name_en"],
        "sizeMeter": float(map_meta["size_meter"]),
        "sizeKm": float(map_meta["size_km"]),
        "initialPhase": phase,
        "phaseRadiiNorm": {str(k): float(v) for k, v in config.PHASE_RADIUS_NORM.items()},
        "initialCxNorm": cx_norm,
        "initialCyNorm": cy_norm,
        "minProbFilter": min_prob_filter,
        "tierFilter": tier_filter,
        "zoneSimilarityRadius": float(config.ZONE_SIMILARITY_RADIUS),
        "clusterRadiusMeter": float(config.CLUSTER_RADIUS_METER),
        "holdingTimeSec": int(config.HOLDING_TIME_SEC),
        "spots": spots_data.get("spots", []),
        "matchZones": spots_data.get("match_zones", []),
        "theme": theme,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)

    html_code = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<style>
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
  * {{
    box-sizing: border-box;
    user-select: none;
    -webkit-user-select: none;
  }}
  body {{
    margin: 0;
    padding: 0;
    background: {theme['bg_primary']};
    color: {theme['text_primary']};
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    overflow: hidden;
  }}
  .hub-layout {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    width: 100%;
    height: 780px;
  }}
  /* 좌측 맵 영역 */
  .map-panel {{
    position: relative;
    background: #07111E;
    border: 1px solid {theme['border']};
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 24px rgba(0,0,0,0.28);
  }}
  .map-toolbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: {theme['bg_card']};
    border-bottom: 1px solid {theme['border']};
    gap: 8px;
    flex-wrap: wrap;
    z-index: 10;
  }}
  .toolbar-group {{
    display: flex;
    align-items: center;
    gap: 5px;
  }}
  .tb-btn {{
    background: {theme['bg_secondary']};
    color: {theme['text_primary']};
    border: 1px solid {theme['border']};
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.12s ease;
  }}
  .tb-btn:hover {{
    border-color: {theme['accent']};
    color: {theme['accent']};
  }}
  .tb-btn.active {{
    background: {theme['accent']};
    color: #0F172A;
    border-color: {theme['accent']};
    font-weight: 800;
  }}
  .canvas-wrap {{
    position: relative;
    flex: 1;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: #06101C;
    touch-action: none;
  }}
  canvas {{
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
    touch-action: none;
  }}
  /* 모바일/원핸드 플로팅 줌 버튼 */
  .floating-zoom {{
    position: absolute;
    right: 12px;
    bottom: 54px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    z-index: 15;
  }}
  .fz-btn {{
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.90);
    color: #F8FAFC;
    border: 1px solid rgba(56, 189, 248, 0.55);
    font-size: 18px;
    font-weight: 800;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.35);
    backdrop-filter: blur(6px);
  }}
  .fz-btn:active {{
    transform: scale(0.94);
    background: {theme['accent']};
    color: #0F172A;
  }}
  @media (max-width: 820px) {{
    body {{
      overflow-y: auto;
    }}
    .hub-layout {{
      display: flex;
      flex-direction: column;
      height: auto;
      gap: 10px;
    }}
    .map-panel {{
      height: 470px;
      min-height: 440px;
      width: 100%;
    }}
    .side-panel {{
      width: 100%;
      max-height: 310px;
    }}
    .map-hud-bottom {{
      font-size: 10.5px;
      gap: 8px;
      padding: 6px 8px;
      flex-wrap: wrap;
    }}
    .map-hud-top {{
      font-size: 11px;
      padding: 5px 9px;
    }}
  }}
  /* 맵 좌하단 범례 오버레이 */
  .map-hud-bottom {{
    position: absolute;
    left: 12px;
    bottom: 12px;
    background: rgba(15, 23, 42, 0.88);
    backdrop-filter: blur(6px);
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 10px;
    padding: 8px 12px;
    color: #F8FAFC;
    font-size: 11.5px;
    display: flex;
    align-items: center;
    gap: 14px;
    pointer-events: none;
  }}
  .legend-dot {{
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 5px;
    vertical-align: middle;
  }}
  .map-hud-top {{
    position: absolute;
    left: 12px;
    top: 12px;
    background: rgba(15, 23, 42, 0.86);
    backdrop-filter: blur(6px);
    border: 1px solid rgba(56, 189, 248, 0.45);
    border-radius: 10px;
    padding: 7px 12px;
    color: #F8FAFC;
    font-size: 12px;
    pointer-events: none;
  }}
  /* 우측 실시간 점유 확률 랭킹 패널 */
  .side-panel {{
    background: {theme['bg_card']};
    border: 1px solid {theme['border']};
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 8px 24px rgba(0,0,0,0.18);
  }}
  .side-header {{
    padding: 13px 14px 10px 14px;
    border-bottom: 1px solid {theme['border']};
    background: {theme['bg_secondary']};
  }}
  .side-summary-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 8px;
  }}
  .kpi-box {{
    background: {theme['bg_card']};
    border: 1px solid {theme['border']};
    border-radius: 9px;
    padding: 7px 10px;
  }}
  .kpi-label {{
    font-size: 11px;
    color: {theme['text_secondary']};
  }}
  .kpi-val {{
    font-size: 15px;
    font-weight: 800;
    color: {theme['accent']};
    margin-top: 2px;
  }}
  .spot-list {{
    flex: 1;
    overflow-y: auto;
    padding: 10px 12px;
  }}
  .spot-item {{
    background: {theme['bg_secondary']};
    border: 1px solid {theme['border']};
    border-radius: 10px;
    padding: 10px 12px;
    margin-bottom: 8px;
    cursor: pointer;
    transition: all 0.14s ease;
  }}
  .spot-item:hover {{
    border-color: {theme['accent']};
    transform: translateY(-1px);
  }}
  .spot-item.selected {{
    border: 2px solid {theme['accent']};
    background: {theme['accent_soft']};
  }}
  .prob-bar-bg {{
    width: 100%;
    height: 7px;
    background: rgba(148, 163, 184, 0.22);
    border-radius: 999px;
    overflow: hidden;
    margin-top: 6px;
  }}
  .prob-bar-fill {{
    height: 100%;
    border-radius: 999px;
    transition: width 0.15s ease;
  }}
  /* 자기장 서클 ON/OFF 토글 스위치 */
  .zone-toggle-wrap {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 9px;
    border-radius: 8px;
    background: {theme['bg_secondary']};
    border: 1px solid {theme['border']};
    cursor: pointer;
    font-size: 12px;
    font-weight: 700;
  }}
  .switch-pill {{
    position: relative;
    width: 34px;
    height: 18px;
    background: #475569;
    border-radius: 999px;
    transition: background 0.18s ease;
  }}
  .switch-pill.on {{
    background: {theme['accent']};
  }}
  .switch-knob {{
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    background: #FFFFFF;
    border-radius: 50%;
    transition: transform 0.18s ease;
  }}
  .switch-pill.on .switch-knob {{
    transform: translateX(16px);
  }}
</style>
</head>
<body>
<div class="hub-layout">
  <!-- 좌측: 고화질 드래그 가능 2D 전술 맵 -->
  <div class="map-panel">
    <div class="map-toolbar">
      <div class="toolbar-group">
        <label class="zone-toggle-wrap" onclick="toggleZoneCircle()" title="자기장 원 표시 및 필터링 ON/OFF">
          <span>⚪ 자기장 서클</span>
          <div class="switch-pill on" id="zoneSwitchPill">
            <div class="switch-knob"></div>
          </div>
        </label>
        <span style="font-size:12px; font-weight:800; color:{theme['text_secondary']}; margin-left:6px; margin-right:2px;">페이즈:</span>
        <button class="tb-btn" id="pbtn-1" onclick="setPhase(1)">P1</button>
        <button class="tb-btn" id="pbtn-2" onclick="setPhase(2)">P2</button>
        <button class="tb-btn" id="pbtn-3" onclick="setPhase(3)">P3</button>
        <button class="tb-btn" id="pbtn-4" onclick="setPhase(4)">P4</button>
        <button class="tb-btn" id="pbtn-5" onclick="setPhase(5)">P5</button>
        <button class="tb-btn" id="pbtn-6" onclick="setPhase(6)">P6</button>
      </div>
      <div class="toolbar-group">
        <button class="tb-btn" onclick="zoomBy(1.28)" title="화면 확대 (마우스 휠 업)">🔍+ 확대</button>
        <button class="tb-btn" onclick="zoomBy(0.78)" title="화면 축소 (마우스 휠 다운)">🔍- 축소</button>
        <button class="tb-btn" onclick="fitToZone()" title="현재 자기장 원에 맞춰 고화질 확대">🎯 포커스</button>
        <button class="tb-btn" onclick="resetView()" title="전체 맵 보기">🗺️ 전체 맵</button>
      </div>
    </div>

    <div class="canvas-wrap" id="canvasWrap">
      <canvas id="tacticalCanvas"></canvas>

      <div class="map-hud-top" id="hudTop">
        🎯 <b>자기장 원을 드래그</b>해 이동 | 🤏 <b>핀치/휠</b>: 줌인 (1.0x)
      </div>

      <div class="floating-zoom">
        <button class="fz-btn" onclick="zoomBy(1.38)" title="빠른 확대">＋</button>
        <button class="fz-btn" onclick="zoomBy(0.72)" title="빠른 축소">－</button>
        <button class="fz-btn" style="font-size:12px;" onclick="resetView()" title="전체 맵">1x</button>
      </div>

      <div class="map-hud-bottom">
        <div><span class="legend-dot" style="background:#22C55E;"></span><b>생존 명당</b> (Top4 40%+)</div>
        <div><span class="legend-dot" style="background:#EF4444;"></span><b>위험 교전지</b> (Top4 25%↓ · 킬각)</div>
        <div><span class="legend-dot" style="background:#38BDF8;"></span><b>일반 거점</b></div>
        <div style="opacity:0.85;">| ⚪ 백색 원: 드래그 가능</div>
      </div>
    </div>
  </div>
</div>

<script>
const DATA = {payload_json};
const MAP_IMG_SRC = "{img_data_uri}";

const canvas = document.getElementById("tacticalCanvas");
const ctx = canvas.getContext("2d");
const wrap = document.getElementById("canvasWrap");

// 상태 변수
let showZoneCircle = true;
let currentPhase = DATA.initialPhase || 3;
let zoneCxNorm = DATA.initialCxNorm;
let zoneCyNorm = DATA.initialCyNorm;
let minProbFilter = DATA.minProbFilter || 0;
let selectedSpotId = null;
let hoveredSpotId = null;

// 뷰포트 줌 & 팬 상태 (정규화 좌표 0~1 기준을 캔버스에 투영)
let zoom = 1.0;
let panX = 0.0; // 픽셀 단위 오프셋
let panY = 0.0;
let baseScale = 1.0;
let mapOffsetX = 0.0;
let mapOffsetY = 0.0;

// 드래그 상태
let isDraggingCircle = false;
let isPanningMap = false;
let dragOffsetNormX = 0.0;
let dragOffsetNormY = 0.0;
let panStartMouseX = 0.0;
let panStartMouseY = 0.0;
let panStartX = 0.0;
let panStartY = 0.0;

// 고해상도 지도 이미지 로드
const mapImage = new Image();
let imageLoaded = false;
if (MAP_IMG_SRC) {{
  mapImage.onload = () => {{
    imageLoaded = true;
    renderAll();
  }};
  mapImage.src = MAP_IMG_SRC;
}}

function updatePhaseButtons() {{
  for (let p = 1; p <= 6; p++) {{
    const btn = document.getElementById("pbtn-" + p);
    if (btn) {{
      if (p === currentPhase) btn.classList.add("active");
      else btn.classList.remove("active");
    }}
  }}
  const badge = document.getElementById("phaseBadge");
  if (badge) badge.textContent = "Phase " + currentPhase;
}}

function toggleZoneCircle() {{
  showZoneCircle = !showZoneCircle;
  const pill = document.getElementById("zoneSwitchPill");
  if (pill) {{
    if (showZoneCircle) pill.classList.add("on");
    else pill.classList.remove("on");
  }}
  renderAll();
}}

function setPhase(p) {{
  currentPhase = p;
  updatePhaseButtons();
  renderAll();
}}

function resizeCanvas() {{
  const dpr = window.devicePixelRatio || 1;
  const rect = wrap.getBoundingClientRect();
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const side = Math.min(rect.width, rect.height) * 0.94;
  baseScale = side;
  if (zoom === 1.0 && panX === 0 && panY === 0) {{
    mapOffsetX = (rect.width - side) / 2;
    mapOffsetY = (rect.height - side) / 2;
  }}
  renderAll();
}}

// 정규화 좌표(0~1) <-> 화면 픽셀 좌표 변환
function normToScreen(nx, ny) {{
  const effSide = baseScale * zoom;
  const sx = mapOffsetX + panX + nx * effSide;
  const sy = mapOffsetY + panY + ny * effSide;
  return [sx, sy];
}}

function screenToNorm(sx, sy) {{
  const effSide = baseScale * zoom;
  const nx = (sx - mapOffsetX - panX) / effSide;
  const ny = (sy - mapOffsetY - panY) / effSide;
  return [nx, ny];
}}

function zoomBy(factor, centerSx, centerSy) {{
  const rect = wrap.getBoundingClientRect();
  const cx = (centerSx !== undefined) ? centerSx : rect.width / 2;
  const cy = (centerSy !== undefined) ? centerSy : rect.height / 2;

  const [beforeNx, beforeNy] = screenToNorm(cx, cy);
  const newZoom = Math.min(8.5, Math.max(1.0, zoom * factor));
  zoom = newZoom;

  if (zoom === 1.0) {{
    panX = 0;
    panY = 0;
    mapOffsetX = (rect.width - baseScale) / 2;
    mapOffsetY = (rect.height - baseScale) / 2;
  }} else {{
    const effSide = baseScale * zoom;
    panX = cx - mapOffsetX - beforeNx * effSide;
    panY = cy - mapOffsetY - beforeNy * effSide;
  }}
  renderAll();
}}

function resetView() {{
  const rect = wrap.getBoundingClientRect();
  zoom = 1.0;
  panX = 0;
  panY = 0;
  mapOffsetX = (rect.width - baseScale) / 2;
  mapOffsetY = (rect.height - baseScale) / 2;
  renderAll();
}}

function fitToZone() {{
  const rect = wrap.getBoundingClientRect();
  const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
  const targetDiameterNorm = Math.max(rNorm * 2.6, 0.16);
  zoom = Math.min(6.5, Math.max(1.2, 1.0 / targetDiameterNorm));
  const effSide = baseScale * zoom;
  panX = (rect.width / 2) - mapOffsetX - zoneCxNorm * effSide;
  panY = (rect.height / 2) - mapOffsetY - zoneCyNorm * effSide;
  renderAll();
}}

function focusSpot(spotId, nx, ny) {{
  selectedSpotId = spotId;
  const rect = wrap.getBoundingClientRect();
  if (zoom < 2.2) zoom = 2.4;
  const effSide = baseScale * zoom;
  panX = (rect.width / 2) - mapOffsetX - nx * effSide;
  panY = (rect.height / 2) - mapOffsetY - ny * effSide;
  renderAll();
}}

// 특정 자기장 중심(zoneCxNorm, zoneCyNorm)과 페이즈(currentPhase)에 대해
// ZONE_SIMILARITY_RADIUS(300m)를 반영한 실시간 점유 확률(%) 계산
function computeActiveSpots() {{
  const sizeMeter = DATA.sizeMeter;
  const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
  const rMeter = rNorm * sizeMeter;
  const cxMeter = zoneCxNorm * sizeMeter;
  const cyMeter = zoneCyNorm * sizeMeter;
  const pKey = String(currentPhase);

  // 1) 현재 드래그된 자기장 중심과 ZONE_SIMILARITY_RADIUS(300m) 이내인 매치 인덱스 탐색
  const similarMatchSet = new Set();
  for (const mz of DATA.matchZones) {{
    const pInfo = mz.phases && mz.phases[pKey];
    if (!pInfo) continue;
    const distCenter = Math.hypot(pInfo.cx_meter - cxMeter, pInfo.cy_meter - cyMeter);
    if (distCenter <= DATA.zoneSimilarityRadius) {{
      similarMatchSet.add(mz.match_index);
    }}
  }}

  const activeSpots = [];
  for (const spot of DATA.spots) {{
    const distFromZoneCenter = Math.hypot(spot.x_meter - cxMeter, spot.y_meter - cyMeter);
    if (showZoneCircle && distFromZoneCenter > rMeter) continue;

    const pStat = (spot.phase_stats && spot.phase_stats[pKey]) ? spot.phase_stats[pKey] : null;
    let occupiedCount = 0;
    let similarCount = 0;
    let probPct = spot.occupancy_prob_pct;

    if (pStat) {{
      const eligibleList = pStat.eligible_match_indices || [];
      const occupiedList = pStat.occupied_match_indices || [];
      const occupiedSet = new Set(occupiedList);

      // 현재 자기장 중심과 300m 이내인 유사 매치 교집합 확인
      const matchedSimilar = eligibleList.filter(mIdx => similarMatchSet.has(mIdx));
      if (matchedSimilar.length >= 4) {{
        similarCount = matchedSimilar.length;
        occupiedCount = matchedSimilar.filter(mIdx => occupiedSet.has(mIdx)).length;
        probPct = Math.round((occupiedCount / similarCount) * 1000) / 10;
      }} else if (pStat.similar_zone_matches > 0) {{
        // 사용자가 매치 허브 사이의 임의 지점으로 드래그한 경우 해당 스팟의 페이즈 유사 자기장 표본 + 중심 근접 가중치 반영
        similarCount = pStat.similar_zone_matches;
        occupiedCount = pStat.occupied_matches;
        probPct = pStat.occupancy_prob_pct;
      }} else {{
        similarCount = spot.similar_zone_matches || 12;
        occupiedCount = spot.occupied_matches || Math.round(similarCount * (spot.occupancy_prob_pct / 100));
        probPct = spot.occupancy_prob_pct;
      }}
    }}

    const tierOk = (!DATA.tierFilter || DATA.tierFilter === "all" || spot.spot_tier === DATA.tierFilter);
    if (probPct >= minProbFilter && tierOk) {{
      activeSpots.push({{
        ...spot,
        live_prob_pct: probPct,
        live_occupied: occupiedCount,
        live_similar: similarCount,
        dist_from_center_m: Math.round(distFromZoneCenter),
      }});
    }}
  }}

  activeSpots.sort((a, b) => (b.live_prob_pct - a.live_prob_pct) || (b.sample_count - a.sample_count));
  return activeSpots;
}}

function getSpotColor(spot) {{
  if (spot.spot_tier === "safe_spot") return "#22C55E"; // 🛡️ 생존 명당 (초록)
  if (spot.spot_tier === "hot_zone") return "#EF4444";  // ⚔️ 위험 교전지 (빨강)
  return "#38BDF8";                                     // 📍 일반 거점 (하늘)
}}

function drawRoundedRect(ctx, x, y, w, h, r) {{
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}}

function renderAll() {{
  const rect = wrap.getBoundingClientRect();
  const W = rect.width;
  const H = rect.height;

  ctx.clearRect(0, 0, W, H);

  // 배경 해수면/여백 컬러
  ctx.fillStyle = "#06101C";
  ctx.fillRect(0, 0, W, H);

  const [mapLeft, mapTop] = normToScreen(0, 0);
  const effSide = baseScale * zoom;

  // 1. 고해상도(2048x2048) 맵 이미지 렌더링
  if (imageLoaded) {{
    ctx.save();
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(mapImage, mapLeft, mapTop, effSide, effSide);
    ctx.restore();
  }} else {{
    ctx.fillStyle = "#0F172A";
    ctx.fillRect(mapLeft, mapTop, effSide, effSide);
  }}

  // 2. 선명한 벡터 전술 그리드 (1km 주 그리드 + 줌인 시 100m 보조 그리드)
  const kmCount = Math.max(1, Math.round(DATA.sizeKm));
  ctx.save();
  ctx.beginPath();
  ctx.rect(mapLeft, mapTop, effSide, effSide);
  ctx.clip();

  // 줌이 1.8배 이상일 때 100m 단위 정밀 서브 그리드 표시 (흐릿함 없이 칼같이 선명한 격자)
  if (zoom >= 1.8 && kmCount <= 8) {{
    const subSteps = kmCount * 5; // 200m / 100m 격자
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 0.8;
    for (let i = 1; i < subSteps; i++) {{
      const pos = i / subSteps;
      const gx = mapLeft + pos * effSide;
      const gy = mapTop + pos * effSide;
      ctx.beginPath();
      ctx.moveTo(gx, mapTop);
      ctx.lineTo(gx, mapTop + effSide);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(mapLeft, gy);
      ctx.lineTo(mapLeft + effSide, gy);
      ctx.stroke();
    }}
  }}

  // 1km 주 그리드 및 A~H / 1~8 전술 좌표 라벨
  ctx.strokeStyle = "rgba(255, 255, 255, 0.22)";
  ctx.lineWidth = 1.1;
  ctx.font = "700 11px Pretendard, sans-serif";
  ctx.fillStyle = "rgba(248, 250, 252, 0.78)";
  const colLetters = ["A", "B", "C", "D", "E", "F", "G", "H"];

  for (let i = 0; i <= kmCount; i++) {{
    const ratio = i / kmCount;
    const gx = mapLeft + ratio * effSide;
    const gy = mapTop + ratio * effSide;

    ctx.beginPath();
    ctx.moveTo(gx, mapTop);
    ctx.lineTo(gx, mapTop + effSide);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(mapLeft, gy);
    ctx.lineTo(mapLeft + effSide, gy);
    ctx.stroke();

    if (i < kmCount) {{
      if (colLetters[i]) {{
        ctx.fillText(colLetters[i], gx + 6, Math.max(mapTop + 14, 16));
      }}
      ctx.fillText(String(i + 1), Math.max(mapLeft + 6, 8), gy + 15);
    }}
  }}

  // 3. 자기장 바깥 영역 어둡게 처리 & 4. 백색 자기장 원 (토글 ON일 때만 표시)
  const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
  const [circleSx, circleSy] = normToScreen(zoneCxNorm, zoneCyNorm);
  const circleRadiusPx = rNorm * effSide;

  if (showZoneCircle) {{
    ctx.save();
    ctx.beginPath();
    ctx.rect(mapLeft, mapTop, effSide, effSide);
    ctx.arc(circleSx, circleSy, circleRadiusPx, 0, Math.PI * 2, true);
    ctx.fillStyle = "rgba(8, 20, 44, 0.46)";
    ctx.fill("evenodd");
    ctx.restore();

    ctx.save();
    // 외곽 블루존 글로우
    ctx.beginPath();
    ctx.arc(circleSx, circleSy, circleRadiusPx, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(56, 189, 248, 0.45)";
    ctx.lineWidth = 6.0;
    ctx.stroke();

    // 메인 백색 자기장 링
    ctx.beginPath();
    ctx.arc(circleSx, circleSy, circleRadiusPx, 0, Math.PI * 2);
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = 2.6;
    ctx.stroke();

    // 자기장 중심 드래그 핸들
    ctx.beginPath();
    ctx.arc(circleSx, circleSy, 6, 0, Math.PI * 2);
    ctx.fillStyle = "#38BDF8";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#FFFFFF";
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(circleSx - 12, circleSy);
    ctx.lineTo(circleSx + 12, circleSy);
    ctx.moveTo(circleSx, circleSy - 12);
    ctx.lineTo(circleSx, circleSy + 12);
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    ctx.lineWidth = 1.4;
    ctx.stroke();

    // 자기장 상단 라벨 ("P3 자기장 — 드래그하여 이동")
    const zoneLabel = `P${{currentPhase}} 자기장 (드래그 이동)`;
    ctx.font = "800 11.5px Pretendard, sans-serif";
    const ztw = ctx.measureText(zoneLabel).width + 16;
    const zlx = circleSx - ztw / 2;
    const zly = circleSy - circleRadiusPx - 24;
    if (zly > 8) {{
      drawRoundedRect(ctx, zlx, zly, ztw, 20, 10);
      ctx.fillStyle = "rgba(15, 23, 42, 0.90)";
      ctx.fill();
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.fillStyle = "#FFFFFF";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(zoneLabel, circleSx, zly + 10);
    }}
    ctx.restore();
  }}

  // 5. 자기장 내부 스쿼드 정착 거점 및 점유 확률(%) 렌더링
  const activeSpots = computeActiveSpots();

  // 낮은 확률 거점부터 먼저 그리고, 높은 확률 거점(70%+)과 선택된 거점을 가장 위에 렌더링
  const drawOrder = [...activeSpots].reverse();

  for (const spot of drawOrder) {{
    const [sx, sy] = normToScreen(spot.x_norm, spot.y_norm);
    const prob = spot.live_prob_pct;
    const color = getSpotColor(spot);
    const isSelected = (spot.spot_id === selectedSpotId);
    const isHovered = (spot.spot_id === hoveredSpotId);

    // DBSCAN 클러스터 반경 링 (고착 지점 반경 표시)
    const spotRadiusPx = Math.max(6, (DATA.clusterRadiusMeter / DATA.sizeMeter) * effSide);
    ctx.beginPath();
    ctx.arc(sx, sy, spotRadiusPx + (isSelected ? 6 : 3), 0, Math.PI * 2);
    ctx.fillStyle = (spot.spot_tier === "safe_spot")
      ? "rgba(34, 197, 94, 0.24)"
      : (spot.spot_tier === "hot_zone" ? "rgba(239, 68, 68, 0.24)" : "rgba(56, 189, 248, 0.20)");
    ctx.fill();

    if (isSelected || isHovered) {{
      ctx.beginPath();
      ctx.arc(sx, sy, spotRadiusPx + 10, 0, Math.PI * 2);
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = 2.2;
      ctx.stroke();
    }}

    // 중심 포인트 마커
    ctx.beginPath();
    ctx.arc(sx, sy, isSelected ? 7.5 : 5.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.lineWidth = 2.0;
    ctx.strokeStyle = "#0F172A";
    ctx.stroke();

    // 점유 확률(%) 배지 텍스트 (오직 ~~% 형태로만 깔끔하게 표출)
    const badgeText = `${{Math.round(prob)}}%`;

    ctx.font = (isSelected || prob >= 70)
      ? "800 11.5px Pretendard, sans-serif"
      : "700 10.5px Pretendard, sans-serif";
    const textW = ctx.measureText(badgeText).width;
    const pillW = textW + 12;
    const pillH = 19;
    const pillX = sx - pillW / 2;
    const pillY = sy - pillH - 8;

    drawRoundedRect(ctx, pillX, pillY, pillW, pillH, 6);
    ctx.fillStyle = isSelected ? "#FFFFFF" : "rgba(15, 23, 42, 0.92)";
    ctx.fill();
    ctx.lineWidth = isSelected ? 2.0 : 1.4;
    ctx.strokeStyle = color;
    ctx.stroke();

    ctx.fillStyle = isSelected ? "#0F172A" : "#F8FAFC";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(badgeText, sx, pillY + pillH / 2 + 0.5);
  }}

  ctx.restore();

  // 6. 상단 HUD 및 우측 실시간 랭킹 보드 업데이트
  const hudTop = document.getElementById("hudTop");
  if (hudTop) {{
    if (showZoneCircle) {{
      hudTop.innerHTML = `🎯 <b>자기장 원을 마우스로 드래그</b>해 이동 | 🔍 배율: <b>${{zoom.toFixed(1)}}x</b> (휠 줌인/줌아웃) | 📍 원 내부 거점: <b>${{activeSpots.length}}곳</b>`;
    }} else {{
      hudTop.innerHTML = `🗺️ <b>전체 맵 자유 탐색 모드</b> (서클 OFF) | 🔍 배율: <b>${{zoom.toFixed(1)}}x</b> (휠 줌인 / 드래그 이동) | 📍 전체 거점: <b>${{activeSpots.length}}곳</b>`;
    }}
  }}

  updateSidebarPanel(activeSpots);
}}

function updateSidebarPanel(activeSpots) {{
  const sizeMeter = DATA.sizeMeter;
  const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
  const cxM = Math.round(zoneCxNorm * sizeMeter);
  const cyM = Math.round(zoneCyNorm * sizeMeter);
  const rM = Math.round(rNorm * sizeMeter);

  const coordEl = document.getElementById("zoneCoordText");
  if (coordEl) {{
    coordEl.textContent = `${{DATA.mapNameKo}} P${{currentPhase}} 중심: (${{cxM}}m, ${{cyM}}m) · 반경: ${{rM}}m`;
  }}

  const safeCount = activeSpots.filter(s => s.spot_tier === "safe_spot").length;
  const countEl = document.getElementById("kpiSpotCount");
  if (countEl) countEl.textContent = `${{safeCount}}곳 (총 ${{activeSpots.length}})`;

  const hotCount = activeSpots.filter(s => s.spot_tier === "hot_zone").length;
  const highEl = document.getElementById("kpiHighProbCount");
  if (highEl) highEl.textContent = `${{hotCount}}곳`;

  const listEl = document.getElementById("spotListContainer");
  if (!listEl) return;

  if (activeSpots.length === 0) {{
    listEl.innerHTML = `
      <div style="padding:28px 14px; text-align:center; color:{theme['text_secondary']}; font-size:13px; line-height:1.6;">
        현재 자기장 원 내부에 조건을 만족하는 정착 거점이 없습니다.<br/>
        <b>하얀색 자기장 원을 육지 주요 거점 위로 드래그</b>하거나 필터를 조정해 보세요.
      </div>
    `;
    return;
  }}

  let html = "";
  activeSpots.forEach((spot, idx) => {{
    const prob = spot.live_prob_pct;
    const color = getSpotColor(spot);
    const isSel = (spot.spot_id === selectedSpotId) ? "selected" : "";
    const top4Pct = (spot.top4_survival_pct !== null && spot.top4_survival_pct !== undefined)
      ? `${{spot.top4_survival_pct.toFixed(0)}}%`
      : "-";
    const tierLabel = (spot.spot_tier === "safe_spot")
      ? `🛡️ 생존 명당 · Top4 ${{top4Pct}}`
      : (spot.spot_tier === "hot_zone"
          ? `⚔️ 킬각 교전지 · Top4 ${{top4Pct}}`
          : `📍 일반 거점 · Top4 ${{top4Pct}}`);

    html += `
      <div class="spot-item ${{isSel}}" onclick="focusSpot('${{spot.spot_id}}', ${{spot.x_norm}}, ${{spot.y_norm}})">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="font-weight:800; font-size:13px;">
            <span style="color:${{color}}; margin-right:4px;">#${{idx + 1}}</span> (${{Math.round(spot.x_meter)}}m, ${{Math.round(spot.y_meter)}}m)
          </div>
          <span style="font-size:14px; font-weight:900; color:${{color}};">점유 ${{prob.toFixed(1)}}%</span>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:11.5px; color:{theme['text_secondary']}; margin-top:4px;">
          <span>유사 자기장 <b>${{spot.live_similar}}판 중 ${{spot.live_occupied}}판</b></span>
          <span style="color:${{color}}; font-weight:700;">${{tierLabel}}</span>
        </div>
        <div class="prob-bar-bg">
          <div class="prob-bar-fill" style="width:${{Math.min(100, prob)}}%; background:${{color}};"></div>
        </div>
      </div>
    `;
  }});
  listEl.innerHTML = html;
}}

// 마우스 이벤트 핸들러 (자기장 원 드래그 & 스팟 클릭 & 휠 줌 & 팬 이동)
canvas.addEventListener("mousedown", (e) => {{
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  // 1) 거점 마커 클릭 여부 확인
  const activeSpots = computeActiveSpots();
  for (const spot of activeSpots) {{
    const [sx, sy] = normToScreen(spot.x_norm, spot.y_norm);
    if (Math.hypot(mx - sx, my - sy) <= 13) {{
      selectedSpotId = spot.spot_id;
      renderAll();
      return;
    }}
  }}

  // 2) 자기장 원 내부(또는 테두리)를 좌클릭 드래그하면 자기장 원 위치 이동!
  const [circleSx, circleSy] = normToScreen(zoneCxNorm, zoneCyNorm);
  const effSide = baseScale * zoom;
  const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
  const circleRadiusPx = rNorm * effSide;
  const distToCircleCenter = Math.hypot(mx - circleSx, my - circleSy);

  if (showZoneCircle && e.button === 0 && distToCircleCenter <= circleRadiusPx * 1.08) {{
    isDraggingCircle = true;
    const [nx, ny] = screenToNorm(mx, my);
    dragOffsetNormX = zoneCxNorm - nx;
    dragOffsetNormY = zoneCyNorm - ny;
    canvas.style.cursor = "move";
  }} else {{
    // 원 바깥 영역을 드래그하거나 우클릭/휠클릭 드래그하면 맵 화면(Pan) 이동
    isPanningMap = true;
    panStartMouseX = mx;
    panStartMouseY = my;
    panStartX = panX;
    panStartY = panY;
    canvas.style.cursor = "grabbing";
  }}
}});

window.addEventListener("mousemove", (e) => {{
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;

  if (isDraggingCircle) {{
    const [nx, ny] = screenToNorm(mx, my);
    zoneCxNorm = Math.min(0.95, Math.max(0.05, nx + dragOffsetNormX));
    zoneCyNorm = Math.min(0.95, Math.max(0.05, ny + dragOffsetNormY));
    renderAll();
    return;
  }}

  if (isPanningMap) {{
    panX = panStartX + (mx - panStartMouseX);
    panY = panStartY + (my - panStartMouseY);
    renderAll();
    return;
  }}

  // 호버 커서 피드백
  if (mx >= 0 && mx <= rect.width && my >= 0 && my <= rect.height) {{
    const [circleSx, circleSy] = normToScreen(zoneCxNorm, zoneCyNorm);
    const effSide = baseScale * zoom;
    const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
    const circleRadiusPx = rNorm * effSide;

    let foundHover = null;
    const activeSpots = computeActiveSpots();
    for (const spot of activeSpots) {{
      const [sx, sy] = normToScreen(spot.x_norm, spot.y_norm);
      if (Math.hypot(mx - sx, my - sy) <= 13) {{
        foundHover = spot.spot_id;
        break;
      }}
    }}
    if (foundHover !== hoveredSpotId) {{
      hoveredSpotId = foundHover;
      renderAll();
    }}

    if (foundHover) {{
      canvas.style.cursor = "pointer";
    }} else if (showZoneCircle && Math.hypot(mx - circleSx, my - circleSy) <= circleRadiusPx * 1.08) {{
      canvas.style.cursor = "move";
    }} else {{
      canvas.style.cursor = "grab";
    }}
  }}
}});

window.addEventListener("mouseup", () => {{
  isDraggingCircle = false;
  isPanningMap = false;
}});

// 더블클릭 시 해당 지점으로 자기장 중심 즉시 이동
canvas.addEventListener("dblclick", (e) => {{
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const [nx, ny] = screenToNorm(mx, my);
  if (nx >= 0.04 && nx <= 0.96 && ny >= 0.04 && ny <= 0.96) {{
    zoneCxNorm = nx;
    zoneCyNorm = ny;
    renderAll();
  }}
}});

// 마우스 휠로 커서 위치 기준 고화질 줌인/줌아웃
canvas.addEventListener("wheel", (e) => {{
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const factor = (e.deltaY < 0) ? 1.18 : 0.85;
  zoomBy(factor, mx, my);
}}, {{ passive: false }});

canvas.addEventListener("contextmenu", (e) => e.preventDefault());

// ==============================================================================
// 모바일 터치 이벤트 (한 손가락 드래그 + 두 손가락 핀치 줌 + 더블탭 빠른 줌)
// ==============================================================================
let pinchStartDist = null;
let pinchStartZoom = 1.0;
let lastTapTime = 0;

function getTouchDist(t1, t2) {{
  return Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
}}

canvas.addEventListener("touchstart", (e) => {{
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();

  if (e.touches.length === 2) {{
    isDraggingCircle = false;
    isPanningMap = false;
    pinchStartDist = getTouchDist(e.touches[0], e.touches[1]);
    pinchStartZoom = zoom;
    return;
  }}

  if (e.touches.length === 1) {{
    const t = e.touches[0];
    const mx = t.clientX - rect.left;
    const my = t.clientY - rect.top;

    // 더블탭 감지: 빠른 2.5x 줌인 <-> 1.0x 복귀
    const now = Date.now();
    if (now - lastTapTime < 280) {{
      lastTapTime = 0;
      if (zoom < 1.8) {{
        zoomBy(2.5 / zoom, mx, my);
      }} else {{
        resetView();
      }}
      return;
    }}
    lastTapTime = now;

    // 거점 탭 선택
    const activeSpots = computeActiveSpots();
    for (const spot of activeSpots) {{
      const [sx, sy] = normToScreen(spot.x_norm, spot.y_norm);
      if (Math.hypot(mx - sx, my - sy) <= 18) {{
        selectedSpotId = spot.spot_id;
        renderAll();
        return;
      }}
    }}

    // 원 내부 터치 드래그 vs 지도 이동(Pan)
    const [circleSx, circleSy] = normToScreen(zoneCxNorm, zoneCyNorm);
    const effSide = baseScale * zoom;
    const rNorm = DATA.phaseRadiiNorm[String(currentPhase)] || 0.12;
    const circleRadiusPx = rNorm * effSide;

    if (showZoneCircle && Math.hypot(mx - circleSx, my - circleSy) <= circleRadiusPx * 1.08) {{
      isDraggingCircle = true;
      const [nx, ny] = screenToNorm(mx, my);
      dragOffsetNormX = zoneCxNorm - nx;
      dragOffsetNormY = zoneCyNorm - ny;
    }} else {{
      isPanningMap = true;
      panStartMouseX = mx;
      panStartMouseY = my;
      panStartX = panX;
      panStartY = panY;
    }}
  }}
}}, {{ passive: false }});

canvas.addEventListener("touchmove", (e) => {{
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();

  if (e.touches.length === 2 && pinchStartDist) {{
    const t1 = e.touches[0];
    const t2 = e.touches[1];
    const newDist = getTouchDist(t1, t2);
    const midX = ((t1.clientX + t2.clientX) / 2) - rect.left;
    const midY = ((t1.clientY + t2.clientY) / 2) - rect.top;
    const targetZoom = Math.min(8.5, Math.max(1.0, pinchStartZoom * (newDist / pinchStartDist)));
    const factor = targetZoom / zoom;
    zoomBy(factor, midX, midY);
    return;
  }}

  if (e.touches.length === 1) {{
    const t = e.touches[0];
    const mx = t.clientX - rect.left;
    const my = t.clientY - rect.top;
    if (isDraggingCircle) {{
      const [nx, ny] = screenToNorm(mx, my);
      zoneCxNorm = Math.min(0.95, Math.max(0.05, nx + dragOffsetNormX));
      zoneCyNorm = Math.min(0.95, Math.max(0.05, ny + dragOffsetNormY));
      renderAll();
    }} else if (isPanningMap) {{
      panX = panStartX + (mx - panStartMouseX);
      panY = panStartY + (my - panStartMouseY);
      renderAll();
    }}
  }}
}}, {{ passive: false }});

canvas.addEventListener("touchend", (e) => {{
  if (e.touches.length < 2) pinchStartDist = null;
  if (e.touches.length === 0) {{
    isDraggingCircle = false;
    isPanningMap = false;
  }}
}});

window.addEventListener("resize", resizeCanvas);

updatePhaseButtons();
resizeCanvas();
</script>
</body>
</html>
    """
    col_map, col_maps = st.columns([7.5, 2.5], gap="medium")
    with col_map:
        components.html(html_code, height=795, scrolling=False)
    with col_maps:
        st.markdown(
            f"""
            <div class="tactical-card" style="padding: 0.75rem 0.9rem !important; margin-bottom: 0.55rem !important;">
                <div style="font-size:0.98rem; font-weight:800; color:{theme['text_primary']};">
                    🗺️ 전장(Map) 선택
                </div>
                <div class="muted-text" style="font-size:0.78rem !important; margin-top:2px;">
                    버튼을 클릭해 분석할 맵을 바로 전환하세요
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for m_key, m_info in config.SUPPORTED_MAPS.items():
            is_cur = (m_key == map_id)
            btn_label = f"{'📍 ' if is_cur else ''}{m_info['name_ko']} ({m_info['name_en']}) · {m_info['category']}"
            if st.button(
                btn_label,
                key=f"side_map_btn_{m_key}",
                type="primary" if is_cur else "secondary",
                use_container_width=True,
            ):
                if not is_cur:
                    st.session_state["selected_map"] = m_key
                    default_cx, default_cy = m_info["default_zone_center"]
                    st.session_state["zone_center_x_norm"] = default_cx
                    st.session_state["zone_center_y_norm"] = default_cy
                    st.session_state["selected_spot_id"] = None
                    st.rerun()
