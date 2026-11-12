"""
PUBG Tactical Hub - 데이터 생성 및 거점 점유 확률 산출 파이프라인 (src/pipeline.py)
기능:
1. (데이터 생성) 에란겔(및 지원 맵) 가상 텔레메트리 매치 데이터 생성
   - 최소 30판 이상(기본 60판) 매치 데이터
   - 각 판마다 페이즈 1~6 자기장 중심 좌표 및 16개 팀(스쿼드)의 고착(Holding >= 30초) 스팟 좌표 포함
2. (확률 산출 로직) 특정 페이즈와 자기장 영역 내에서 DBSCAN(반경 20m)으로 주요 거점 포인트(클러스터) 도출
   - 점유 확률(%) = (해당 포인트에 스쿼드가 고착한 매치 수 / 유사 자기장 전체 매치 수) * 100
   - 결과를 data/processed/erangel_spots.json (및 각 맵별 _spots.json)으로 저장
"""

import json
import math
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
from PIL import Image
from sklearn.cluster import DBSCAN

# 프로젝트 루트 경로 추가
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import config


def _load_land_mask(map_id: str) -> np.ndarray | None:
    """지도 이미지로부터 육지(True) / 바다 및 강(False) 마스크를 생성합니다."""
    img_path = Path(config.SUPPORTED_MAPS[map_id]["map_image_file"])
    if not img_path.exists():
        return None
    try:
        arr = np.array(Image.open(img_path).convert("RGB").resize((512, 512)), dtype=np.int16)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        if map_id == "vikendi":
            # 설원 맵(비켄디)은 눈 덮인 육지의 밝기가 높고 외곽 바다는 어두운 청색
            land_mask = ((r + g + b) > 130) | (r > (b - 4))
        else:
            land_mask = (r > (b - 6)) & ((r + g + b) > 85)
        return land_mask
    except Exception:
        return None


def _is_land(x_norm: float, y_norm: float, land_mask: np.ndarray | None) -> bool:
    """정규화 좌표 (0~1)가 육지인지 검증합니다."""
    if not (0.07 <= x_norm <= 0.93 and 0.07 <= y_norm <= 0.93):
        return False
    if land_mask is None:
        return True
    h, w = land_mask.shape
    px = int(np.clip(x_norm * (w - 1), 0, w - 1))
    py = int(np.clip(y_norm * (h - 1), 0, h - 1))
    y0, y1 = max(0, py - 2), min(h, py + 3)
    x0, x1 = max(0, px - 2), min(w, px + 3)
    patch = land_mask[y0:y1, x0:x1]
    return bool(np.mean(patch) >= 0.80)


def _build_candidate_landmarks(
    map_id: str,
    rng: np.random.Generator,
    land_mask: np.ndarray | None,
) -> List[Dict[str, Any]]:
    """
    맵 전역의 주요 랜드마크 및 전술 정착지(집단, 능선, 창고, 검문소) 후보군을 생성합니다.
    10판 중 8~9판 자리 잡는 1티어 요충지부터 3~6판 자리 잡는 서브 거점까지 현실적인 선호도 분포를 가집니다.
    """
    candidates: List[Dict[str, Any]] = []

    if map_id == "erangel":
        for idx, (xn, yn, name, weight) in enumerate(config.ERANGEL_LANDMARKS):
            # 1티어 랜드마크들의 목표 점유율(0.68 ~ 0.94)이 자연스럽게 분포하도록 세밀 조정
            jitter_w = float(np.clip(weight - rng.uniform(0.02, 0.14), 0.64, 0.94))
            candidates.append({
                "seed_id": idx,
                "x_norm": float(xn),
                "y_norm": float(yn),
                "name": name,
                "base_weight": jitter_w,
            })

        # 주요 랜드마크 주변의 실제 서브 정착 포인트(근교 능선, 외곽 2층집, 창고, 매복 구릉) 확장
        sub_suffixes = [
            "북측 능선 집단",
            "남측 외곽 창고",
            "서측 구릉 가옥",
            "동측 도로변 초소",
            "외곽 2층 차고집",
        ]
        seed_idx = len(candidates)
        for base_idx, (bx, by, bname, bweight) in enumerate(config.ERANGEL_LANDMARKS):
            region_label = bname.split()[0]
            for s_i in range(4):
                for _ in range(20):
                    angle = rng.uniform(0, 2 * math.pi)
                    dist = rng.uniform(0.022, 0.068)  # 175m ~ 540m 거리
                    nx = float(np.clip(bx + math.cos(angle) * dist, 0.08, 0.92))
                    ny = float(np.clip(by + math.sin(angle) * dist, 0.08, 0.92))
                    if _is_land(nx, ny, land_mask):
                        too_close = any(
                            math.hypot(nx - c["x_norm"], ny - c["y_norm"]) < 0.014
                            for c in candidates
                        )
                        if not too_close:
                            sub_name = f"{region_label} {sub_suffixes[(base_idx + s_i) % len(sub_suffixes)]}"
                            # 서브 거점은 28% ~ 76% 사이의 다양한 점유 확률을 갖도록 설정
                            tier_w = float(np.clip(bweight - rng.uniform(0.16, 0.54), 0.28, 0.78))
                            candidates.append({
                                "seed_id": seed_idx,
                                "x_norm": nx,
                                "y_norm": ny,
                                "name": sub_name,
                                "base_weight": tier_w,
                            })
                            seed_idx += 1
                            break
    else:
        map_ko = config.SUPPORTED_MAPS[map_id]["name_ko"]
        spot_types = ["중앙 요충지", "북측 고지대", "남측 창고 단지", "서측 능선 초소", "동측 삼거리 가옥", "외곽 매복 능선"]
        seed_idx = 0
        grid_coords = np.linspace(0.14, 0.86, 11)
        for gx in grid_coords:
            for gy in grid_coords:
                for _ in range(12):
                    nx = float(np.clip(gx + rng.uniform(-0.03, 0.03), 0.09, 0.91))
                    ny = float(np.clip(gy + rng.uniform(-0.03, 0.03), 0.09, 0.91))
                    if _is_land(nx, ny, land_mask):
                        stype = spot_types[seed_idx % len(spot_types)]
                        candidates.append({
                            "seed_id": seed_idx,
                            "x_norm": nx,
                            "y_norm": ny,
                            "name": f"{map_ko} #{seed_idx + 1:02d} {stype}",
                            "base_weight": float(rng.uniform(0.30, 0.92)),
                        })
                        seed_idx += 1
                        break

    return candidates


def generate_virtual_telemetry(
    map_id: str = "erangel",
    num_matches: int = config.NUM_SIMULATED_MATCHES,
) -> Dict[str, Any]:
    """
    1단계 (데이터 생성):
    최소 30판 이상(기본 60판)의 매치 텔레메트리 데이터를 생성합니다.
    각 판마다 페이즈 1~6 자기장 중심 좌표와 16개 스쿼드의 고착 스팟 좌표(체류 시간 >= 30초)를 포함합니다.
    """
    map_meta = config.SUPPORTED_MAPS[map_id]
    size_meter = float(map_meta["size_meter"])

    seed_offset = sum(ord(ch) for ch in map_id)
    rng = np.random.default_rng(config.RANDOM_SEED + seed_offset)

    land_mask = _load_land_mask(map_id)
    candidates = _build_candidate_landmarks(map_id, rng, land_mask)

    zone_hubs_norm: List[Tuple[float, float]] = [
        (0.48, 0.48),  # 포친키 / 학교 중앙 자기장
        (0.51, 0.42),  # 학교 / 로족 자기장
        (0.44, 0.51),  # 포친키 본시가지 자기장
        (0.31, 0.48),  # 가트카 / 루인스 서부 자기장
        (0.22, 0.35),  # 게오르고폴 / 병원 자기장
        (0.65, 0.30),  # 야스나야 북동 자기장
        (0.46, 0.18),  # 세베르니 / 사격장 북부 자기장
        (0.68, 0.55),  # 농장 / 밀타 동부 자기장
        (0.76, 0.46),  # 프리즌 / 맨션 자기장
        (0.54, 0.77),  # 밀리터리 베이스 남부 섬 자기장
        (0.28, 0.63),  # 쿼리 / 페리 피어 남서 자기장
        (0.72, 0.20),  # 스탈베르 북동 자기장
    ]

    matches: List[Dict[str, Any]] = []

    for match_idx in range(num_matches):
        match_id = f"{map_id}_match_{match_idx + 1:03d}"
        if match_idx < 15:
            hub_x, hub_y = zone_hubs_norm[match_idx % 3]
        else:
            hub_x, hub_y = zone_hubs_norm[match_idx % len(zone_hubs_norm)]

        jitter_norm = (config.ZONE_SIMILARITY_RADIUS * 0.60) / size_meter
        cx_norm = float(np.clip(hub_x + rng.normal(0.0, jitter_norm * 0.42), 0.18, 0.82))
        cy_norm = float(np.clip(hub_y + rng.normal(0.0, jitter_norm * 0.42), 0.18, 0.82))

        phases_data: Dict[str, Any] = {}

        for phase in config.PHASES:
            radius_norm = config.PHASE_RADIUS_NORM[phase]
            radius_meter = radius_norm * size_meter

            if phase > 1:
                shift_scale = jitter_norm * 0.20
                cx_norm = float(np.clip(cx_norm + rng.normal(0.0, shift_scale), 0.14, 0.86))
                cy_norm = float(np.clip(cy_norm + rng.normal(0.0, shift_scale), 0.14, 0.86))

            cx_meter = round(cx_norm * size_meter, 1)
            cy_meter = round(cy_norm * size_meter, 1)

            in_zone_candidates = []
            for cand in candidates:
                dist_norm = math.hypot(cand["x_norm"] - cx_norm, cand["y_norm"] - cy_norm)
                if dist_norm <= radius_norm * 1.02:
                    in_zone_candidates.append((cand, dist_norm))

            if len(in_zone_candidates) < 16:
                sorted_by_dist = sorted(
                    [(c, math.hypot(c["x_norm"] - cx_norm, c["y_norm"] - cy_norm)) for c in candidates],
                    key=lambda item: item[1],
                )
                in_zone_candidates = sorted_by_dist[:max(20, len(in_zone_candidates))]

            squad_holdings: List[Dict[str, Any]] = []

            # 각 후보 거점이 해당 매치/페이즈에서 스쿼드에 의해 점유될지 독립 베르누이 시행
            # 이를 통해 거점별로 30%~95% 사이의 정확한 고착 확률(base_weight 반영)이 재현됨
            selected_cands = []
            for cand, dist_norm in in_zone_candidates:
                center_factor = max(0.86, 1.04 - (dist_norm / max(radius_norm, 0.01)) * 0.16)
                prob = float(np.clip(cand["base_weight"] * center_factor, 0.20, 0.94))
                if rng.random() < prob:
                    selected_cands.append(cand)

            # 매치당 16개 팀의 고착 좌표를 기록하되, 선택된 거점들을 우선 배정하고
            # 부족 시 가중치 비례 비복원 추출로 16개 스쿼드 고착 데이터를 구성
            if len(selected_cands) < config.NUM_SQUADS_PER_MATCH:
                remaining = [c for c, _ in in_zone_candidates if c not in selected_cands]
                if remaining:
                    weights = np.array([c["base_weight"] ** 2 for c in remaining], dtype=np.float64)
                    weights /= weights.sum()
                    need = min(config.NUM_SQUADS_PER_MATCH - len(selected_cands), len(remaining))
                    extra_idx = rng.choice(len(remaining), size=need, replace=False, p=weights)
                    for idx_e in extra_idx:
                        selected_cands.append(remaining[int(idx_e)])

            match_ranks = rng.permutation(np.arange(1, config.NUM_SQUADS_PER_MATCH + 1))

            for sq_i, cand in enumerate(selected_cands, start=1):
                offset_r = rng.uniform(1.0, config.CLUSTER_RADIUS_METER * 0.42)
                offset_theta = rng.uniform(0.0, 2.0 * math.pi)
                spot_x_meter = float(np.clip(
                    cand["x_norm"] * size_meter + math.cos(offset_theta) * offset_r,
                    0.0,
                    size_meter,
                ))
                spot_y_meter = float(np.clip(
                    cand["y_norm"] * size_meter + math.sin(offset_theta) * offset_r,
                    0.0,
                    size_meter,
                ))
                holding_sec = int(rng.integers(config.HOLDING_TIME_SEC, config.HOLDING_TIME_SEC + 150))
                squad_id = ((sq_i - 1) % config.NUM_SQUADS_PER_MATCH) + 1
                base_rank = int(match_ranks[squad_id - 1])
                # High base_weight spots slightly bias toward either Top 4 or hot early fights
                if cand["base_weight"] >= 1.15 and sq_i % 2 == 0:
                    sim_rank = int(rng.integers(1, 5))
                elif cand["base_weight"] >= 1.15 and sq_i % 3 == 0:
                    sim_rank = int(rng.integers(8, config.NUM_SQUADS_PER_MATCH + 1))
                else:
                    sim_rank = base_rank

                squad_holdings.append({
                    "squad_id": squad_id,
                    "team_rank": sim_rank,
                    "x_meter": round(spot_x_meter, 2),
                    "y_meter": round(spot_y_meter, 2),
                    "x_norm": round(spot_x_meter / size_meter, 5),
                    "y_norm": round(spot_y_meter / size_meter, 5),
                    "holding_time_sec": holding_sec,
                    "landmark_hint": cand["name"],
                    "seed_id": cand["seed_id"],
                })

            phases_data[str(phase)] = {
                "phase": phase,
                "zone_center_x_meter": cx_meter,
                "zone_center_y_meter": cy_meter,
                "zone_center_x_norm": round(cx_norm, 5),
                "zone_center_y_norm": round(cy_norm, 5),
                "zone_radius_meter": round(radius_meter, 1),
                "zone_radius_norm": round(radius_norm, 5),
                "squad_holdings": squad_holdings,
            }

        matches.append({
            "match_id": match_id,
            "match_index": match_idx,
            "map_id": map_id,
            "phases": phases_data,
        })

    return {
        "map_id": map_id,
        "map_name_ko": map_meta["name_ko"],
        "map_name_en": map_meta["name_en"],
        "size_meter": size_meter,
        "num_matches": len(matches),
        "num_squads_per_match": config.NUM_SQUADS_PER_MATCH,
        "holding_time_threshold_sec": config.HOLDING_TIME_SEC,
        "matches": matches,
    }


STABILITY_EDGES: List[float] = [0.0, 0.33, 0.66, 1.0]   # 원 중심에서의 거리 / 원 반지름 구간 경계
STABILITY_MIN_N: int = 20                                # 이 팀 수 미만인 구간은 '표본 부족'으로 표시


def _build_stability_table(matches: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    '자리의 안정성' 표를 만듭니다.
    - 페이즈 p의 자기장 원 안에서 30초 이상 머문 팀이, 원 중심에서 반지름의 몇 % 지점에 있었는가(구간)별로
    - 바로 다음 페이즈(p+1) 원 안에 남아 있던 팀의 비율(stay_pct)을 계산합니다.
    거점 하나하나가 아니라 '원과의 상대 위치'로 여러 판의 데이터를 합쳐 표본을 확보합니다.
    """
    counts: Dict[Tuple[int, int], List[int]] = {}
    for match in matches:
        phases = match["phases"]
        for p in config.PHASES[:-1]:
            cur = phases.get(str(p))
            nxt = phases.get(str(p + 1))
            if not cur or not nxt:
                continue
            seen = set()
            for sq in cur["squad_holdings"]:
                if sq["holding_time_sec"] < config.HOLDING_TIME_SEC or sq["squad_id"] in seen:
                    continue
                seen.add(sq["squad_id"])
                r_cur = max(float(cur["zone_radius_meter"]), 1.0)
                r_next = max(float(nxt["zone_radius_meter"]), 1.0)
                rel = math.hypot(
                    sq["x_meter"] - float(cur["zone_center_x_meter"]),
                    sq["y_meter"] - float(cur["zone_center_y_meter"]),
                ) / r_cur
                if rel >= 1.0:
                    continue  # 이미 현재 원 밖에 있던 팀은 제외 (원 밖은 항상 이동 필요)
                b = max(i for i, e in enumerate(STABILITY_EDGES[:-1]) if rel >= e)
                inside_next = math.hypot(
                    sq["x_meter"] - float(nxt["zone_center_x_meter"]),
                    sq["y_meter"] - float(nxt["zone_center_y_meter"]),
                ) / r_next <= 1.0
                cell = counts.setdefault((p, b), [0, 0])
                cell[0] += 1
                cell[1] += 1 if inside_next else 0

    table: Dict[str, List[Dict[str, Any]]] = {}
    for p in config.PHASES[:-1]:
        rows = []
        for b in range(len(STABILITY_EDGES) - 1):
            n, k = counts.get((p, b), [0, 0])
            rows.append({
                "lo": STABILITY_EDGES[b],
                "hi": STABILITY_EDGES[b + 1],
                "n": int(n),
                "stay_pct": round(k / n * 100.0, 1) if n > 0 else None,
                "reliable": bool(n >= STABILITY_MIN_N),
            })
        table[str(p)] = rows
    return table


def _poisson_binomial_tails(probs: List[float], k: int) -> Tuple[float, float]:
    """
    서로 다른 확률(probs)을 가진 독립 시행들의 성공 횟수 X에 대해
    P(X >= k) 와 P(X <= k) 를 정확히 계산합니다. (동적계획법)
    """
    dist = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dist) + 1)
        for j, v in enumerate(dist):
            nxt[j] += v * (1.0 - p)
            nxt[j + 1] += v * p
        dist = nxt
    k = max(0, min(k, len(dist) - 1))
    p_ge = float(sum(dist[k:]))
    p_le = float(sum(dist[: k + 1]))
    return p_ge, p_le


def _phase_top4_baselines(holding_records: List[Dict[str, Any]]) -> Dict[int, float]:
    """
    페이즈별 '기본 Top4 비율'을 계산합니다.
    후반 페이즈까지 살아있는 팀은 원래 Top4 비율이 높기 때문에(생존자 편향),
    각 거점의 Top4 비율은 '같은 페이즈에 있던 팀들의 평균'과 비교해야 공정합니다.
    """
    cutoff = config.TOP4_RANK_CUTOFF
    pair_rank: Dict[Tuple[int, int], int] = {}
    pair_phases: Dict[Tuple[int, int], set] = {}
    for rec in holding_records:
        tr = rec.get("team_rank", 0)
        if tr > 0:
            key = (rec["match_index"], rec["squad_id"])
            pair_rank[key] = tr
            pair_phases.setdefault(key, set()).add(rec["phase"])

    overall_ranks = list(pair_rank.values())
    overall_rate = (
        sum(1 for r in overall_ranks if r <= cutoff) / len(overall_ranks) if overall_ranks else 0.2
    )

    baselines: Dict[int, float] = {}
    for p in config.PHASES:
        ranks = [pair_rank[k] for k, phs in pair_phases.items() if p in phs]
        if len(ranks) >= 20:
            rate = sum(1 for r in ranks if r <= cutoff) / len(ranks)
        else:
            rate = overall_rate  # 표본이 너무 적은 페이즈는 전체 평균으로 대체
        baselines[p] = min(max(rate, 0.02), 0.98)
    return baselines


def calculate_spot_probabilities(telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    2단계 (확률 산출 로직):
    - HOLDING_TIME_SEC(30초) 이상 머무른 스쿼드 좌표들을 대상으로
      DBSCAN(eps=CLUSTER_RADIUS_METER=20m) 클러스터링을 수행해 주요 거점 포인트(Spot) 도출
    - 특정 페이즈와 자기장 중심 좌표 기준으로 ZONE_SIMILARITY_RADIUS(300m) 내의 유사 자기장 매치들을 묶어
      점유 확률(%) = (해당 포인트에 스쿼드가 고착한 매치 수 / 유사 자기장 전체 매치 수) * 100 계산
    """
    map_id = telemetry_data["map_id"]
    map_meta = config.SUPPORTED_MAPS[map_id]
    size_meter = float(telemetry_data["size_meter"])
    matches = telemetry_data["matches"]

    holding_records: List[Dict[str, Any]] = []
    for match in matches:
        m_idx = match["match_index"]
        for phase_str, p_info in match["phases"].items():
            phase_num = int(phase_str)
            for sq in p_info["squad_holdings"]:
                if sq["holding_time_sec"] >= config.HOLDING_TIME_SEC:
                    holding_records.append({
                        "match_index": m_idx,
                        "phase": phase_num,
                        "squad_id": sq["squad_id"],
                        "team_rank": int(sq.get("team_rank", 0) or 0),
                        "x_meter": sq["x_meter"],
                        "y_meter": sq["y_meter"],
                        "holding_time_sec": sq["holding_time_sec"],
                        "landmark_hint": sq["landmark_hint"],
                    })

    coords_meter = np.array([[r["x_meter"], r["y_meter"]] for r in holding_records], dtype=np.float64)
    phase_top4_baselines = _phase_top4_baselines(holding_records)

    dbscan = DBSCAN(
        eps=float(config.CLUSTER_RADIUS_METER),
        min_samples=int(config.DBSCAN_MIN_SAMPLES),
        metric="euclidean",
    )
    labels = dbscan.fit_predict(coords_meter)

    unique_labels = sorted(set(labels) - {-1})

    match_phase_zones: Dict[Tuple[int, int], Tuple[float, float, float]] = {}
    for match in matches:
        m_idx = match["match_index"]
        for phase_str, p_info in match["phases"].items():
            match_phase_zones[(m_idx, int(phase_str))] = (
                float(p_info["zone_center_x_meter"]),
                float(p_info["zone_center_y_meter"]),
                float(p_info["zone_radius_meter"]),
            )

    default_cx_norm, default_cy_norm = map_meta["default_zone_center"]
    default_cx_meter = default_cx_norm * size_meter
    default_cy_meter = default_cy_norm * size_meter

    spots: List[Dict[str, Any]] = []

    for cluster_id in unique_labels:
        member_indices = np.where(labels == cluster_id)[0]
        member_coords = coords_meter[member_indices]
        center_x_meter = float(np.mean(member_coords[:, 0]))
        center_y_meter = float(np.mean(member_coords[:, 1]))
        center_x_norm = round(center_x_meter / size_meter, 5)
        center_y_norm = round(center_y_meter / size_meter, 5)

        hints = [holding_records[i]["landmark_hint"] for i in member_indices]
        most_common_name = max(set(hints), key=hints.count)
        avg_holding_sec = round(
            float(np.mean([holding_records[i]["holding_time_sec"] for i in member_indices])), 1
        )

        occupied_pairs = set()
        occupied_matches_by_phase: Dict[str, List[int]] = {str(p): [] for p in config.PHASES}
        for i in member_indices:
            rec = holding_records[i]
            pair = (rec["match_index"], rec["phase"])
            if pair not in occupied_pairs:
                occupied_pairs.add(pair)
                occupied_matches_by_phase[str(rec["phase"])].append(rec["match_index"])

        phase_stats: Dict[str, Dict[str, Any]] = {}
        overall_occupied = 0
        overall_similar = 0

        for p in config.PHASES:
            in_zone_matches: List[Tuple[int, float, float]] = []
            for m_idx in range(len(matches)):
                zcx, zcy, zr = match_phase_zones[(m_idx, p)]
                if math.hypot(center_x_meter - zcx, center_y_meter - zcy) <= zr * 1.02:
                    in_zone_matches.append((m_idx, zcx, zcy))

            if in_zone_matches:
                ref_cx = float(np.median([item[1] for item in in_zone_matches]))
                ref_cy = float(np.median([item[2] for item in in_zone_matches]))
                similar_matches = [
                    item[0]
                    for item in in_zone_matches
                    if math.hypot(item[1] - ref_cx, item[2] - ref_cy) <= config.ZONE_SIMILARITY_RADIUS
                ]
                if len(similar_matches) < 5:
                    similar_matches = [item[0] for item in in_zone_matches]
            else:
                similar_matches = []

            similar_set = set(similar_matches)
            occ_in_similar = [
                m_idx for m_idx in occupied_matches_by_phase[str(p)] if m_idx in similar_set
            ]

            denom = len(similar_set)
            numer = len(occ_in_similar)
            if denom > 0:
                prob_pct = round((numer / denom) * 100.0, 1)
            else:
                prob_pct = 0.0

            phase_stats[str(p)] = {
                "occupied_matches": numer,
                "similar_zone_matches": denom,
                "occupancy_prob_pct": prob_pct,
                "eligible_match_indices": sorted(similar_set),
                "occupied_match_indices": sorted(occ_in_similar),
            }

            if p in (1, 2, 3, 4):
                overall_occupied += numer
                overall_similar += denom

        if overall_similar > 0:
            baseline_prob_pct = round((overall_occupied / overall_similar) * 100.0, 1)
        else:
            probs = [st["occupancy_prob_pct"] for st in phase_stats.values() if st["similar_zone_matches"] > 0]
            baseline_prob_pct = round(float(np.mean(probs)) if probs else 50.0, 1)

        # Top 4 생존율(%) 계산: 해당 포인트에 고착했던 팀(매치-팀 단위 중복 제거) 중 최종 4위 이내 비율
        seen_team_ranks: Dict[Tuple[int, int], int] = {}
        seen_team_last_phase: Dict[Tuple[int, int], int] = {}
        for i in member_indices:
            rec = holding_records[i]
            tr = rec.get("team_rank", 0)
            if tr > 0:
                key = (rec["match_index"], rec["squad_id"])
                seen_team_ranks[key] = tr
                # 이 거점에서 해당 팀이 확인된 가장 늦은 페이즈 (그 페이즈까지는 살아있었다는 뜻)
                seen_team_last_phase[key] = max(seen_team_last_phase.get(key, 0), rec["phase"])

        rank_sample_count = len(seen_team_ranks)
        top4_count = sum(1 for r in seen_team_ranks.values() if r <= config.TOP4_RANK_CUTOFF)
        top4_survival_pct = round((top4_count / rank_sample_count) * 100.0, 1) if rank_sample_count > 0 else None

        # 같은 페이즈에 있던 팀들의 평균 Top4 비율로 '기대값'을 구해 비교 (생존자 편향 보정)
        expected_probs = [
            phase_top4_baselines.get(seen_team_last_phase[k], 0.2) for k in seen_team_ranks
        ]
        top4_expected_pct = (
            round(float(np.mean(expected_probs)) * 100.0, 1) if expected_probs else None
        )

        top4_pvalue_better = None   # 기대보다 좋을 때, 우연히 이만큼 나올 확률
        top4_pvalue_worse = None    # 기대보다 나쁠 때, 우연히 이만큼 나올 확률
        spot_tier = "neutral"       # 📍 일반 거점 (표본 부족이거나 평균과 구분되지 않음)
        if rank_sample_count >= config.TIER_MIN_SAMPLES:
            p_ge, p_le = _poisson_binomial_tails(expected_probs, top4_count)
            top4_pvalue_better = round(p_ge, 4)
            top4_pvalue_worse = round(p_le, 4)
            if p_ge <= config.TIER_ALPHA:
                spot_tier = "safe_spot"   # 🛡️ 생존 명당 (같은 페이즈 평균보다 순위가 유의하게 높음)
            elif p_le <= config.TIER_ALPHA:
                spot_tier = "hot_zone"    # ⚔️ 킬각 교전지 (같은 페이즈 평균보다 순위가 유의하게 낮음)

        spots.append({
            "spot_id": f"{map_id}_spot_{cluster_id + 1:03d}",
            "cluster_id": int(cluster_id),
            "spot_name": most_common_name,
            "x_meter": round(center_x_meter, 1),
            "y_meter": round(center_y_meter, 1),
            "x_norm": center_x_norm,
            "y_norm": center_y_norm,
            "x_telemetry": round(center_x_meter * config.PUBG_UNIT_PER_METER, 1),
            "y_telemetry": round(center_y_meter * config.PUBG_UNIT_PER_METER, 1),
            "sample_count": int(len(member_indices)),
            "avg_holding_time_sec": avg_holding_sec,
            "occupied_matches": int(overall_occupied),
            "similar_zone_matches": int(overall_similar),
            "occupancy_prob_pct": baseline_prob_pct,
            "rank_sample_count": int(rank_sample_count),
            "top4_count": int(top4_count),
            "top4_survival_pct": top4_survival_pct,
            "top4_expected_pct": top4_expected_pct,
            "top4_pvalue_better": top4_pvalue_better,
            "top4_pvalue_worse": top4_pvalue_worse,
            "spot_tier": spot_tier,
            "phase_stats": phase_stats,
        })

    spots.sort(key=lambda s: (s["occupancy_prob_pct"], s["sample_count"]), reverse=True)
    for rank_idx, spot in enumerate(spots, start=1):
        spot["rank"] = rank_idx

    match_zones_summary: List[Dict[str, Any]] = []
    for match in matches:
        m_phases = {}
        for p_str, p_info in match["phases"].items():
            m_phases[p_str] = {
                "cx_meter": p_info["zone_center_x_meter"],
                "cy_meter": p_info["zone_center_y_meter"],
                "cx_norm": p_info["zone_center_x_norm"],
                "cy_norm": p_info["zone_center_y_norm"],
                "radius_meter": p_info["zone_radius_meter"],
            }
        match_zones_summary.append({
            "match_index": match["match_index"],
            "match_id": match["match_id"],
            "phases": m_phases,
        })

    return {
        "map_id": map_id,
        "map_name_ko": map_meta["name_ko"],
        "map_name_en": map_meta["name_en"],
        "data_source": telemetry_data.get("data_source", "simulation"),
        "size_km": map_meta["size_km"],
        "size_meter": size_meter,
        "algorithm_params": {
            "HOLDING_TIME_SEC": config.HOLDING_TIME_SEC,
            "CLUSTER_RADIUS_METER": config.CLUSTER_RADIUS_METER,
            "ZONE_SIMILARITY_RADIUS": config.ZONE_SIMILARITY_RADIUS,
            "formula": "점유 확률(%) = (해당 포인트에 스쿼드가 고착한 매치 수 / 유사 자기장 전체 매치 수) * 100",
        },
        "default_zone": {
            "phase": 3,
            "center_x_norm": default_cx_norm,
            "center_y_norm": default_cy_norm,
            "center_x_meter": round(default_cx_meter, 1),
            "center_y_meter": round(default_cy_meter, 1),
        },
        "total_matches": len(matches),
        "total_spots": len(spots),
        "spots": spots,
        "match_zones": match_zones_summary,
        "stability_table": _build_stability_table(matches),
    }


def extract_team_ranks_from_match_json(m_json: Dict[str, Any]) -> Dict[int, int]:
    """공식 PUBG /matches/{id} 응답의 roster stats에서 {teamId: rank} 매핑을 추출합니다."""
    ranks: Dict[int, int] = {}
    for inc in m_json.get("included", []):
        if inc.get("type") == "roster":
            st = (inc.get("attributes") or {}).get("stats") or {}
            tid = int(st.get("teamId", 0) or 0)
            rk = int(st.get("rank", 0) or 0)
            if tid > 0 and rk > 0:
                ranks[tid] = rk
    return ranks


def _parse_single_telemetry_json(
    events: List[Dict[str, Any]],
    match_id: str,
    match_index: int,
    map_id: str,
    size_meter: float,
    team_ranks: Dict[int, int] | None = None,
) -> Dict[str, Any] | None:
    """
    공식 PUBG Telemetry 이벤트 리스트(LogGameStatePeriodic, LogPlayerPosition, LogMatchEnd)를 파싱하여
    페이즈 1~6 자기장 중심 좌표 및 30초 이상 고착한 스쿼드 좌표 + 최종 순위를 추출합니다.
    """
    phase_zones: Dict[int, List[Tuple[float, float, float]]] = {p: [] for p in config.PHASES}
    # (phase, team_id) -> list of (elapsed_sec, x_meter, y_meter)
    team_positions: Dict[Tuple[int, int], List[Tuple[float, float, float]]] = {}
    resolved_ranks: Dict[int, int] = dict(team_ranks or {})

    current_phase = 0
    for ev in events:
        t_type = ev.get("_T")
        common = ev.get("common") or {}
        is_game = float(common.get("isGame", 0.0) or 0.0)
        if is_game >= 1.0:
            p_cand = int(math.floor(is_game))
            if 1 <= p_cand <= 6:
                current_phase = p_cand

        if t_type == "LogGameStatePeriodic":
            gs = ev.get("gameState") or {}
            sz_pos = gs.get("safetyZonePosition") or {}
            sz_rad = float(gs.get("safetyZoneRadius", 0.0) or 0.0) / config.PUBG_UNIT_PER_METER
            sx = float(sz_pos.get("x", 0.0) or 0.0) / config.PUBG_UNIT_PER_METER
            sy = float(sz_pos.get("y", 0.0) or 0.0) / config.PUBG_UNIT_PER_METER
            if 1 <= current_phase <= 6 and sz_rad > 10.0 and sx > 0 and sy > 0:
                phase_zones[current_phase].append((sx, sy, sz_rad))

        elif t_type == "LogPlayerPosition" and 1 <= current_phase <= 6:
            char = ev.get("character") or {}
            if float(char.get("health", 100.0) or 0.0) <= 0:
                continue
            team_id = int(char.get("teamId", 0) or 0)
            loc = char.get("location") or {}
            px = float(loc.get("x", 0.0) or 0.0) / config.PUBG_UNIT_PER_METER
            py = float(loc.get("y", 0.0) or 0.0) / config.PUBG_UNIT_PER_METER
            elapsed = float(ev.get("elapsedTime", 0.0) or 0.0)
            if team_id > 0 and 0 < px <= size_meter and 0 < py <= size_meter:
                team_positions.setdefault((current_phase, team_id), []).append((elapsed, px, py))

        elif t_type == "LogMatchEnd" and not resolved_ranks:
            for ch_wrap in ev.get("characters") or []:
                ch = ch_wrap.get("character") or ch_wrap
                tid = int(ch.get("teamId", 0) or 0)
                rk = int(ch.get("ranking", 0) or 0)
                if tid > 0 and rk > 0:
                    resolved_ranks[tid] = rk

    if not any(phase_zones.values()):
        return None

    phases_data: Dict[str, Any] = {}
    last_cx, last_cy = size_meter * 0.5, size_meter * 0.5

    for p in config.PHASES:
        if phase_zones[p]:
            cx_m = float(np.median([z[0] for z in phase_zones[p]]))
            cy_m = float(np.median([z[1] for z in phase_zones[p]]))
            r_m = float(np.median([z[2] for z in phase_zones[p]]))
            last_cx, last_cy = cx_m, cy_m
        else:
            cx_m, cy_m = last_cx, last_cy
            r_m = config.PHASE_RADIUS_NORM[p] * size_meter

        squad_holdings: List[Dict[str, Any]] = []
        for (ph, team_id), pos_list in team_positions.items():
            if ph != p or len(pos_list) < 2:
                continue
            pos_list.sort(key=lambda item: item[0])
            # 연속 체류 구간 중 반경 CLUSTER_RADIUS_METER(20m) 이내에서 HOLDING_TIME_SEC(30초) 이상 머문 지점 탐색
            anchor_t, anchor_x, anchor_y = pos_list[0]
            max_hold_sec = 0.0
            best_x, best_y = anchor_x, anchor_y
            xs, ys = [anchor_x], [anchor_y]

            for t_now, x_now, y_now in pos_list[1:]:
                if math.hypot(x_now - anchor_x, y_now - anchor_y) <= config.CLUSTER_RADIUS_METER:
                    xs.append(x_now)
                    ys.append(y_now)
                    dur = t_now - anchor_t
                    if dur > max_hold_sec:
                        max_hold_sec = dur
                        best_x = float(np.mean(xs))
                        best_y = float(np.mean(ys))
                else:
                    anchor_t, anchor_x, anchor_y = t_now, x_now, y_now
                    xs, ys = [anchor_x], [anchor_y]

            if max_hold_sec >= config.HOLDING_TIME_SEC:
                squad_holdings.append({
                    "squad_id": team_id,
                    "team_rank": resolved_ranks.get(team_id, 0),
                    "x_meter": round(best_x, 2),
                    "y_meter": round(best_y, 2),
                    "x_norm": round(best_x / size_meter, 5),
                    "y_norm": round(best_y / size_meter, 5),
                    "holding_time_sec": int(round(max_hold_sec)),
                    "landmark_hint": f"Spot ({int(best_x)}m, {int(best_y)}m)",
                    "seed_id": 0,
                })

        phases_data[str(p)] = {
            "phase": p,
            "zone_center_x_meter": round(cx_m, 1),
            "zone_center_y_meter": round(cy_m, 1),
            "zone_center_x_norm": round(cx_m / size_meter, 5),
            "zone_center_y_norm": round(cy_m / size_meter, 5),
            "zone_radius_meter": round(r_m, 1),
            "zone_radius_norm": round(r_m / size_meter, 5),
            "squad_holdings": squad_holdings,
        }

    return {
        "match_id": match_id,
        "match_index": match_index,
        "map_id": map_id,
        "phases": phases_data,
    }


def fetch_real_pubg_telemetry(
    api_key: str,
    shard: str = "steam",
    player_names: List[str] | None = None,
    target_map_id: str = "erangel",
    max_matches: int = 35,
    competitive_only: bool = False,
    reset_cache: bool = False,
    cache_profile: str = "user",
) -> Dict[str, Any]:
    """
    공식 PUBG Developer API(https://api.pubg.com)를 통해 실제 매치 텔레메트리를 수집·파싱하고
    data/processed/{map_id}_spots.json을 갱신합니다.
    """
    import requests

    api_key = api_key.strip()
    if not api_key:
        raise ValueError("PUBG API Key가 비어 있습니다.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/vnd.api+json",
    }

    map_meta = config.SUPPORTED_MAPS[target_map_id]
    target_telemetry_name = map_meta["telemetry_name"]
    size_meter = float(map_meta["size_meter"])

    match_ids: List[str] = []

    # 1. 플레이어 닉네임 지정 시 해당 유저들의 최근 매치 ID 수집
    if player_names:
        clean_names = ",".join([n.strip() for n in player_names if n.strip()][:10])
        if clean_names:
            url = f"{config.PUBG_API_BASE_URL}/shards/{shard}/players"
            resp = requests.get(url, headers=headers, params={"filter[playerNames]": clean_names}, timeout=15)
            if resp.status_code == 404:
                raise ValueError(
                    f"[{shard.upper()}] 서버에서 닉네임 '{clean_names}'을(를) 찾을 수 없습니다. "
                    f"(PUBG API는 인게임 닉네임의 대소문자를 100% 정확히 구분하며, 최근 14일 이내 플레이 기록이 있어야 조회됩니다.)"
                )
            if resp.status_code == 429:
                raise ValueError("PUBG API 분당 호출 제한(10회)을 초과했습니다. 1분 후 다시 시도해 주세요.")
            resp.raise_for_status()
            data = resp.json().get("data", [])
            for p_obj in data:
                m_list = p_obj.get("relationships", {}).get("matches", {}).get("data", [])
                for m_ref in m_list:
                    mid = m_ref.get("id")
                    if mid and mid not in match_ids:
                        match_ids.append(mid)

    # 2. 플레이어 미지정 시에만 /samples 엔드포인트 활용 (선수/유저 지정 시 일반 샘플 혼입 방지)
    if not player_names:
        url = f"{config.PUBG_API_BASE_URL}/shards/{shard}/samples"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        m_list = (
            resp.json()
            .get("data", {})
            .get("relationships", {})
            .get("matches", {})
            .get("data", [])
        )
        for m_ref in m_list:
            mid = m_ref.get("id")
            if mid and mid not in match_ids:
                match_ids.append(mid)

    # 0. 프로필별(선수용 pro / 일반 유저용 user) 분리 캐시 경로 설정
    if cache_profile == "pro":
        raw_path = config.DATA_RAW_DIR / f"{target_map_id}_pro_matches.json"
        out_path = config.DATA_PROCESSED_DIR / f"{target_map_id}_pro_spots.json"
    else:
        raw_path = Path(map_meta["raw_file"])
        out_path = Path(map_meta["processed_file"])

    existing_matches: List[Dict[str, Any]] = []
    cached_match_ids: set[str] = set()
    if not reset_cache and raw_path.exists():
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                prev_bundle = json.load(f)
            if prev_bundle.get("data_source") == "real_pubg_api":
                existing_matches = prev_bundle.get("matches", [])
                cached_match_ids = {m["match_id"] for m in existing_matches if m.get("match_id")}
        except Exception:
            existing_matches = []
            cached_match_ids = set()

    newly_parsed_matches: List[Dict[str, Any]] = []
    erangel_aliases = {"Baltic_Main", "Erangel_Main"}

    for mid in match_ids:
        if mid in cached_match_ids:
            continue
        if len(newly_parsed_matches) >= max_matches:
            break
        try:
            m_url = f"{config.PUBG_API_BASE_URL}/shards/{shard}/matches/{mid}"
            m_resp = requests.get(m_url, headers={"Accept": "application/vnd.api+json"}, timeout=15)
            if m_resp.status_code != 200:
                continue
            m_json = m_resp.json()
            m_attrs = m_json.get("data", {}).get("attributes", {})
            m_map_name = m_attrs.get("mapName", "")
            m_type = m_attrs.get("matchType", "")

            if competitive_only and m_type != "competitive":
                continue

            if target_map_id == "erangel":
                if m_map_name not in erangel_aliases:
                    continue
            elif m_map_name != target_telemetry_name:
                continue

            # Telemetry CDN URL 추출
            telemetry_url = None
            for inc in m_json.get("included", []):
                if inc.get("type") == "asset":
                    telemetry_url = inc.get("attributes", {}).get("URL")
                    if telemetry_url:
                        break
            if not telemetry_url:
                continue

            t_resp = requests.get(telemetry_url, headers={"Accept-Encoding": "gzip"}, timeout=30)
            if t_resp.status_code != 200:
                continue
            events = t_resp.json()
            team_ranks = extract_team_ranks_from_match_json(m_json)
            parsed = _parse_single_telemetry_json(
                events=events,
                match_id=mid,
                match_index=len(existing_matches) + len(newly_parsed_matches),
                map_id=target_map_id,
                size_meter=size_meter,
                team_ranks=team_ranks,
            )
            if parsed:
                newly_parsed_matches.append(parsed)
                cached_match_ids.add(mid)
        except Exception:
            continue

    combined_matches = existing_matches + newly_parsed_matches
    if not combined_matches:
        raise RuntimeError(
            f"조회에 성공했으나 선택한 전장({map_meta['name_ko']})에 해당하는 최근 매치가 없습니다. "
            f"주로 해당 맵을 플레이한 유저 닉네임을 입력해 다시 시도해 주세요."
        )

    for idx, m_obj in enumerate(combined_matches):
        m_obj["match_index"] = idx

    telemetry_bundle = {
        "map_id": target_map_id,
        "map_name_ko": map_meta["name_ko"],
        "map_name_en": map_meta["name_en"],
        "data_source": "real_pubg_api",
        "size_meter": size_meter,
        "num_matches": len(combined_matches),
        "num_squads_per_match": config.NUM_SQUADS_PER_MATCH,
        "holding_time_threshold_sec": config.HOLDING_TIME_SEC,
        "matches": combined_matches,
    }

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(telemetry_bundle, f, ensure_ascii=False, indent=2)

    spots_data = calculate_spot_probabilities(telemetry_bundle)
    spots_data["new_matches_added"] = len(newly_parsed_matches)
    spots_data["cache_profile"] = cache_profile
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(spots_data, f, ensure_ascii=False, indent=2)

    return spots_data


def run_pipeline() -> None:
    """에란겔 및 지원 전장의 가상 텔레메트리 생성 및 거점별 점유 확률 JSON 저장을 수행합니다."""
    config.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    config.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] 에란겔(Erangel) 가상 텔레메트리 생성 중... (총 {config.NUM_SIMULATED_MATCHES}매치, 매치당 {config.NUM_SQUADS_PER_MATCH}스쿼드)")
    erangel_raw = generate_virtual_telemetry("erangel", num_matches=config.NUM_SIMULATED_MATCHES)
    erangel_raw_path = Path(config.SUPPORTED_MAPS["erangel"]["raw_file"])
    with open(erangel_raw_path, "w", encoding="utf-8") as f:
        json.dump(erangel_raw, f, ensure_ascii=False, indent=2)

    print(
        f"[2/2] DBSCAN(반경 {config.CLUSTER_RADIUS_METER}m) 클러스터링 및 "
        f"유사 자기장(허용 오차 {config.ZONE_SIMILARITY_RADIUS}m) 점유 확률(%) 산출 중..."
    )
    erangel_spots_data = calculate_spot_probabilities(erangel_raw)
    erangel_out_path = Path(config.SUPPORTED_MAPS["erangel"]["processed_file"])
    with open(erangel_out_path, "w", encoding="utf-8") as f:
        json.dump(erangel_spots_data, f, ensure_ascii=False, indent=2)

    print(f"  -> 완료: {erangel_out_path} (도출된 주요 거점 수: {erangel_spots_data['total_spots']}개)")
    for top_spot in erangel_spots_data["spots"][:8]:
        print(
            f"     * [{top_spot['rank']}위] {top_spot['spot_name']} "
            f"({top_spot['x_meter']}m, {top_spot['y_meter']}m) -> 점유 확률: {top_spot['occupancy_prob_pct']}% "
            f"({top_spot['occupied_matches']}/{top_spot['similar_zone_matches']}판)"
        )

    for map_id in config.SUPPORTED_MAPS:
        if map_id == "erangel":
            continue
        raw_data = generate_virtual_telemetry(map_id, num_matches=36)
        spots_data = calculate_spot_probabilities(raw_data)
        out_path = Path(config.SUPPORTED_MAPS[map_id]["processed_file"])
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(spots_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    run_pipeline()
