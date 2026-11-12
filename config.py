"""
PUBG Tactical Hub - 전역 설정 및 상수 모듈 (config.py)
핵심 기능: 특정 자기장 페이즈(P1~P6)와 중심 좌표 기준, 자기장 내부 주요 거점별 스쿼드 점유 확률(%) 산출 및 시각화
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

# ==============================================================================
# 1. 프로젝트 경로 설정 및 .env 로드
# ==============================================================================
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_RAW_DIR: Path = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR: Path = BASE_DIR / "data" / "processed"
ASSETS_MAPS_DIR: Path = BASE_DIR / "assets" / "maps"
ENV_FILE: Path = BASE_DIR / ".env"


def load_saved_api_key() -> str:
    """환경 변수, Streamlit Secrets, 또는 .env 파일에서 PUBG_API_KEY를 읽어옵니다."""
    env_val = os.environ.get("PUBG_API_KEY", "").strip()
    if env_val:
        return env_val
    try:
        import streamlit as st
        secret_val = st.secrets.get("PUBG_API_KEY", "")
        if isinstance(secret_val, str) and secret_val.strip():
            return secret_val.strip()
    except Exception:
        pass
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PUBG_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def save_api_key(api_key: str) -> None:
    """입력한 PUBG_API_KEY를 .env 파일과 현재 프로세스 환경 변수에 영구 저장합니다."""
    clean_key = api_key.strip()
    os.environ["PUBG_API_KEY"] = clean_key
    lines = []
    if ENV_FILE.exists():
        lines = [
            ln for ln in ENV_FILE.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("PUBG_API_KEY=")
        ]
    lines.append(f"PUBG_API_KEY={clean_key}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ==============================================================================
# 2. 공식 PUBG Developer API 연동 설정
# ==============================================================================
PUBG_API_BASE_URL: str = "https://api.pubg.com"
PUBG_API_KEY: str = load_saved_api_key()
PUBG_SHARD: str = os.environ.get("PUBG_SHARD", "steam").strip()  # steam, kakao, tournament
DEFAULT_PRO_PLAYERS: List[str] = ["TGLTN", "hwinn", "Shrimzy"]

# 서버(스배/카배) 및 권역별 필터 메타데이터
PRO_REGION_META: Dict[str, Dict[str, str]] = {
    "kakao": {"label": "💛 카배(한국)", "short": "카배", "platform": "kakao", "lb_shard": "pc-kakao", "api_shard": "kakao"},
    "as":    {"label": "🌏 아시아(AS)", "short": "아시아", "platform": "steam", "lb_shard": "pc-as",    "api_shard": "steam"},
    "eu":    {"label": "🇪🇺 유럽(EU)",   "short": "유럽",   "platform": "steam", "lb_shard": "pc-eu",    "api_shard": "steam"},
    "na":    {"label": "🇺🇸 북미(NA)",   "short": "북미",   "platform": "steam", "lb_shard": "pc-na",    "api_shard": "steam"},
    "sea":   {"label": "🌴 동남아(SEA)", "short": "동남아", "platform": "steam", "lb_shard": "pc-sea",   "api_shard": "steam"},
    "oc":    {"label": "🦘 오세아니아(OC·SEA통합)", "short": "오세아니아", "platform": "steam", "lb_shard": "pc-sea", "api_shard": "steam"},
}
ALL_PRO_REGION_KEYS: List[str] = list(PRO_REGION_META.keys())
STEAM_PRO_REGION_KEYS: List[str] = [k for k, v in PRO_REGION_META.items() if v["platform"] == "steam"]

# ==============================================================================
# 3. 핵심 전술 알고리즘 파라미터 (절대 하드코딩 금지 상수)
# ==============================================================================
HOLDING_TIME_SEC: int = 30            # 고착(Holding) 판정 최소 체류 시간 (초)
CLUSTER_RADIUS_METER: int = 20        # 동일 거점 포인트로 묶는 DBSCAN 반경 (m)
ZONE_SIMILARITY_RADIUS: int = 300     # 유사한 자기장 상황으로 묶는 중심 좌표 허용 오차 (m)

# DBSCAN 최소 샘플 수 및 좌표 변환 상수
DBSCAN_MIN_SAMPLES: int = 2           # 거점 클러스터 인정을 위한 최소 스쿼드 고착 샘플 수
PUBG_UNIT_PER_METER: float = 100.0    # PUBG 텔레메트리 좌표계: 1m = 100cm

# ==============================================================================
# 3. 시뮬레이션 및 가상 텔레메트리 생성 설정
# ==============================================================================
RANDOM_SEED: int = 42
NUM_SIMULATED_MATCHES: int = 60       # 에란겔 매치 생성 수 (최소 30판 이상)
NUM_SQUADS_PER_MATCH: int = 16        # 매치당 참가 스쿼드 수 (16개 팀, 64명 기준)
PHASES: List[int] = [1, 2, 3, 4, 5, 6]

# 페이즈별 생존 스쿼드 기대 수 (P1 -> P6로 갈수록 생존 팀 감소, 자리 경쟁 밀도 변화)
PHASE_ALIVE_SQUADS: Dict[int, int] = {
    1: 16,
    2: 15,
    3: 14,
    4: 12,
    5: 9,
    6: 6,
}

# 페이즈별 자기장 반경 비율 (맵 한 변의 길이 대비 반경 비율, 0.0 ~ 1.0 정규화 기준)
PHASE_RADIUS_NORM: Dict[int, float] = {
    1: 0.280,
    2: 0.185,
    3: 0.120,
    4: 0.078,
    5: 0.048,
    6: 0.028,
}

# 자기장 쉬프트 중심 분포(주요 교전 권역 시드 비율)
DEFAULT_ZONE_CENTER_NORM: Tuple[float, float] = (0.48, 0.48)

# ==============================================================================
# 4. 지원하는 9개 전장(Map) 메타데이터 정의
# ==============================================================================
SUPPORTED_MAPS: Dict[str, Dict[str, Any]] = {
    "erangel": {
        "id": "erangel",
        "name_ko": "에란겔",
        "name_en": "Erangel",
        "telemetry_name": "Baltic_Main",
        "api_asset_name": "Erangel_Main",
        "category": "대형 (8x8 km)",
        "size_km": 8.0,
        "size_meter": 8000,
        "telemetry_max": 800000.0,
        "default_zone_center": (0.48, 0.48),
        "processed_file": str(DATA_PROCESSED_DIR / "erangel_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "erangel_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "erangel.jpg"),
    },
    "miramar": {
        "id": "miramar",
        "name_ko": "미라마",
        "name_en": "Miramar",
        "telemetry_name": "Desert_Main",
        "api_asset_name": "Miramar_Main",
        "category": "대형 (8x8 km)",
        "size_km": 8.0,
        "size_meter": 8000,
        "telemetry_max": 800000.0,
        "default_zone_center": (0.50, 0.48),
        "processed_file": str(DATA_PROCESSED_DIR / "miramar_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "miramar_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "miramar.jpg"),
    },
    "taego": {
        "id": "taego",
        "name_ko": "태이고",
        "name_en": "Taego",
        "telemetry_name": "Tiger_Main",
        "api_asset_name": "Taego_Main",
        "category": "대형 (8x8 km)",
        "size_km": 8.0,
        "size_meter": 8000,
        "telemetry_max": 800000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "taego_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "taego_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "taego.jpg"),
    },
    "rondo": {
        "id": "rondo",
        "name_ko": "론도",
        "name_en": "Rondo",
        "telemetry_name": "Neon_Main",
        "api_asset_name": "Rondo_Main",
        "category": "대형 (8x8 km)",
        "size_km": 8.0,
        "size_meter": 8000,
        "telemetry_max": 800000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "rondo_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "rondo_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "rondo.jpg"),
    },
    "deston": {
        "id": "deston",
        "name_ko": "데스턴",
        "name_en": "Deston",
        "telemetry_name": "Kiki_Main",
        "api_asset_name": "Deston_Main",
        "category": "대형 (8x8 km)",
        "size_km": 8.0,
        "size_meter": 8000,
        "telemetry_max": 800000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "deston_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "deston_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "deston.jpg"),
    },
    "vikendi": {
        "id": "vikendi",
        "name_ko": "비켄디",
        "name_en": "Vikendi",
        "telemetry_name": "DihorOtok_Main",
        "api_asset_name": "Vikendi_Main",
        "category": "중형 (6x6 / 8x8 km)",
        "size_km": 6.0,
        "size_meter": 6000,
        "telemetry_max": 600000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "vikendi_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "vikendi_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "vikendi.jpg"),
    },
    "sanhok": {
        "id": "sanhok",
        "name_ko": "사녹",
        "name_en": "Sanhok",
        "telemetry_name": "Savage_Main",
        "api_asset_name": "Sanhok_Main",
        "category": "중형 (4x4 km)",
        "size_km": 4.0,
        "size_meter": 4000,
        "telemetry_max": 400000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "sanhok_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "sanhok_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "sanhok.jpg"),
    },
    "paramo": {
        "id": "paramo",
        "name_ko": "파라모",
        "name_en": "Paramo",
        "telemetry_name": "Chimera_Main",
        "api_asset_name": "Paramo_Main",
        "category": "소형 (3x3 km)",
        "size_km": 3.0,
        "size_meter": 3000,
        "telemetry_max": 300000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "paramo_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "paramo_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "paramo.jpg"),
    },
    "haven": {
        "id": "haven",
        "name_ko": "헤이븐",
        "name_en": "Haven",
        "telemetry_name": "Heaven_Main",
        "api_asset_name": "Haven_Main",
        "category": "소형 (1x1 km)",
        "size_km": 1.0,
        "size_meter": 1000,
        "telemetry_max": 100000.0,
        "default_zone_center": (0.50, 0.50),
        "processed_file": str(DATA_PROCESSED_DIR / "haven_spots.json"),
        "raw_file": str(DATA_RAW_DIR / "haven_matches.json"),
        "map_image_file": str(ASSETS_MAPS_DIR / "haven.jpg"),
    },
}

MAP_CATEGORIES: Dict[str, List[str]] = {
    "대형 (8x8 km)": ["erangel", "miramar", "taego", "rondo", "deston"],
    "중형 (4x4 ~ 6x6 km)": ["vikendi", "sanhok"],
    "소형 (1x1 ~ 3x3 km)": ["paramo", "haven"],
}

# ==============================================================================
# 5. 다크 모드 / 라이트 모드 테마 컬러 시스템 (Shadcn UI / Tremor 스타일)
# ==============================================================================
ACCENT_COLOR: str = "#38BDF8"  # 포인트 컬러 (Sky Blue)

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "name": "dark",
        "bg_primary": "#0F172A",
        "bg_secondary": "#1E293B",
        "bg_card": "#1E293B",
        "bg_hover": "#334155",
        "text_primary": "#F8FAFC",
        "text_secondary": "#94A3B8",
        "border": "#334155",
        "accent": ACCENT_COLOR,
        "accent_soft": "rgba(56, 189, 248, 0.16)",
        "border_radius": "12px",
        "prob_high": "#EF4444",    # 70% 이상 (거의 매 판 스쿼드가 상주하는 핵심 자리)
        "prob_mid": "#F59E0B",     # 45% ~ 69% (자주 점유되는 주요 자리)
        "prob_low": "#38BDF8",     # 45% 미만 (상황별 점유 자리)
    },
    "light": {
        "name": "light",
        "bg_primary": "#F8FAFC",
        "bg_secondary": "#F1F5F9",
        "bg_card": "#FFFFFF",
        "bg_hover": "#E2E8F0",
        "text_primary": "#0F172A",
        "text_secondary": "#475569",
        "border": "#E2E8F0",
        "accent": ACCENT_COLOR,
        "accent_soft": "rgba(56, 189, 248, 0.14)",
        "border_radius": "12px",
        "prob_high": "#DC2626",
        "prob_mid": "#D97706",
        "prob_low": "#0284C7",
    },
}

# ==============================================================================
# 6. 에란겔 실제 지형 랜드마크 및 주요 스쿼드 정착 거점 (육지 검증 완료 좌표)
#    (x_norm, y_norm, 거점 명칭, 기본 선호 가중치)
# ==============================================================================
ERANGEL_LANDMARKS: List[Tuple[float, float, str, float]] = [
    # 중앙 권역 (포친키 / 학교 / 로족 / 루인스) - 대회 및 랭크 게임 최다 정착지
    (0.450, 0.505, "Pochinki 북동 성당/집단", 0.96),
    (0.432, 0.525, "Pochinki 남서 외곽 창고", 0.88),
    (0.468, 0.535, "Pochinki 남동 구릉 가옥", 0.84),
    (0.520, 0.415, "School 본관 & 수영장", 0.94),
    (0.542, 0.412, "School 동측 아파트 단지", 0.91),
    (0.495, 0.355, "Rozhok 남측 고지대 가옥", 0.92),
    (0.478, 0.342, "Rozhok 서측 창고 단지", 0.82),
    (0.395, 0.418, "Ruins 북서 사원 능선", 0.78),
    (0.418, 0.448, "Ruins 남동 언덕 초소", 0.85),
    (0.545, 0.475, "Pochinki 동측 삼거리 집단", 0.90),
    (0.498, 0.460, "School 남서 평원 농가", 0.86),

    # 서부 권역 (게오르고폴 / 가트카 / 병원 / 쿼리 / 프리모스크)
    (0.285, 0.478, "Gatka 본마을 중앙 가옥", 0.89),
    (0.328, 0.495, "Gatka 동측 라디오 타워 능선", 0.93),
    (0.255, 0.440, "Gatka 북서 참호 & 벙커", 0.79),
    (0.215, 0.275, "Georgopol 북측 아파트", 0.87),
    (0.205, 0.342, "Georgopol 남측 컨테이너 앞 가옥", 0.85),
    (0.185, 0.388, "Hospital 본관 능선", 0.86),
    (0.215, 0.640, "Quarry 북동 절벽 가옥", 0.81),
    (0.352, 0.615, "Ferry Pier 북측 언덕 집단", 0.88),
    (0.205, 0.735, "Primorsk 북동 창고 단지", 0.77),

    # 북부 권역 (야스나야 / 세베르니 / 사격장 / 스탈베르)
    (0.658, 0.295, "Yasnaya Polyana 중앙 경찰서", 0.94),
    (0.625, 0.285, "Yasnaya 서측 주유소 & 검문소", 0.89),
    (0.688, 0.318, "Yasnaya 남동 아파트", 0.86),
    (0.468, 0.145, "Severny 남측 성당 가옥", 0.83),
    (0.405, 0.208, "Shooting Range 남측 벙커", 0.85),
    (0.695, 0.160, "Stalber 남서 천문대 능선", 0.82),
    (0.815, 0.135, "Kameshki 남서 해안 초소", 0.74),
    (0.145, 0.165, "Zharki 동측 농장 단지", 0.75),

    # 동부 권역 (밀타 / 농장 / 쉘터 / 프리즌 / 맨션 / 리포브카)
    (0.648, 0.565, "Farm 중앙 본가 창고", 0.93),
    (0.612, 0.535, "Farm 북서 구릉 3채", 0.89),
    (0.738, 0.585, "Mylta 북서 차고지 가옥", 0.91),
    (0.880, 0.535, "Mylta Power 본관 통제실", 0.84),
    (0.700, 0.485, "Shelter 상부 능선 가옥", 0.90),
    (0.775, 0.475, "Prison 서측 절벽 감시탑", 0.87),
    (0.765, 0.385, "Mansion 본관 정원", 0.88),
    (0.862, 0.395, "Lipovka 서측 외곽 농가", 0.80),

    # 남부 섬 권역 (소스노브카 밀리터리 베이스 / 노보)
    (0.548, 0.795, "Sosnovka Military Base C동 옥상", 0.95),
    (0.515, 0.748, "Sosnovka 레이더 기지 고지대", 0.92),
    (0.445, 0.785, "Sosnovka 서측 해안 초소", 0.83),
    (0.748, 0.758, "Novorepnoye 북서 검문소 가옥", 0.87),
]
