"""
리더보드 상위 랭커(스배 지역별 + 카배) 매치 누적 수집 스크립트

동작:
1. 기존 data/raw/{map}_pro_matches.json 매치에 platform/region 태그가 없으면 백필(backfill)
2. 지정된 권역(kakao, as, eu, na, sea)별로 리더보드 상위 N명의 최근 매치 ID를 조회
3. 권역당 최대 --per-region 개씩 새 매치를 수집해 특정 지역에 편중되지 않도록 골고루 누적
4. data/raw/{map}_pro_matches.json 및 data/processed/{map}_pro_spots.json 갱신

사용 예:
    python scripts/collect_leaderboard.py --regions kakao,eu,na,sea --top 15 --per-region 18
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.pipeline import (  # noqa: E402
    _parse_single_telemetry_json,
    calculate_spot_probabilities,
    extract_team_ranks_from_match_json,
)

RATE_LIMIT_SLEEP = 6.3  # 분당 10회 제한 준수
MIN_PRO_MATCHES = 10
TELEMETRY_TO_MAP = {v["telemetry_name"]: k for k, v in config.SUPPORTED_MAPS.items()}
TELEMETRY_TO_MAP["Erangel_Main"] = "erangel"

BACKUP_DIR = Path(
    r"C:\Users\user\.gemini\antigravity\brain\b68572c5-2d0a-417c-9005-ef0f023a04ae\scratch\backup_pro"
)


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {config.PUBG_API_KEY}", "Accept": "application/vnd.api+json"}


def _get_limited(url: str, params: Dict[str, Any] | None = None) -> requests.Response:
    for _ in range(3):
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        time.sleep(RATE_LIMIT_SLEEP)
        if resp.status_code != 429:
            return resp
        print("  [429] 호출 제한 → 60초 대기")
        time.sleep(60)
    return resp


def current_season_id() -> str:
    resp = _get_limited(f"{config.PUBG_API_BASE_URL}/shards/steam/seasons")
    resp.raise_for_status()
    for s in resp.json().get("data", []):
        if s.get("attributes", {}).get("isCurrentSeason"):
            return s["id"]
    raise RuntimeError("현재 시즌을 찾을 수 없습니다.")


def leaderboard_player_ids_for_region(season_id: str, lb_shard: str, modes: List[str], top: int) -> List[str]:
    ids: List[str] = []
    for mode in modes:
        url = f"{config.PUBG_API_BASE_URL}/shards/{lb_shard}/leaderboards/{season_id}/{mode}"
        resp = _get_limited(url)
        if resp.status_code != 200:
            print(f"  리더보드 {lb_shard}/{mode} 건너뜀 ({resp.status_code})")
            continue
        players = [x for x in resp.json().get("included", []) if x.get("type") == "player"]
        players.sort(key=lambda p: (p.get("attributes", {}).get("rank") or 9999))
        picked = [p["id"] for p in players[:top] if p.get("id")]
        print(f"  리더보드 {lb_shard}/{mode}: {len(picked)}명")
        for pid in picked:
            if pid not in ids:
                ids.append(pid)
    return ids


def match_ids_for_region_players(api_shard: str, player_ids: List[str]) -> List[str]:
    match_ids: List[str] = []
    url = f"{config.PUBG_API_BASE_URL}/shards/{api_shard}/players"
    for i in range(0, len(player_ids), 10):
        chunk = player_ids[i:i + 10]
        resp = _get_limited(url, {"filter[playerIds]": ",".join(chunk)})
        if resp.status_code == 200:
            for p_obj in resp.json().get("data", []):
                for m_ref in p_obj.get("relationships", {}).get("matches", {}).get("data", []):
                    mid = m_ref.get("id")
                    if mid and mid not in match_ids:
                        match_ids.append(mid)
        else:
            print(f"  [{api_shard}] players 묶음 실패: {resp.status_code}")
    return match_ids


def load_pro_bundle(map_id: str) -> Dict[str, Any]:
    path = config.DATA_RAW_DIR / f"{map_id}_pro_matches.json"
    meta = config.SUPPORTED_MAPS[map_id]
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("matches") is not None:
                return data
        except Exception:
            pass
    return {
        "map_id": map_id,
        "map_name_ko": meta["name_ko"],
        "map_name_en": meta["name_en"],
        "data_source": "real_pubg_api",
        "size_meter": float(meta["size_meter"]),
        "num_squads_per_match": config.NUM_SQUADS_PER_MATCH,
        "holding_time_threshold_sec": config.HOLDING_TIME_SEC,
        "matches": [],
    }


def compute_region_counts(matches: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {k: 0 for k in config.PRO_REGION_META}
    for m in matches:
        r = m.get("region", "as")
        if r in counts:
            counts[r] += 1
        if r == "sea":
            counts["oc"] += 1
    return counts


def backfill_existing_regions(bundles: Dict[str, Dict[str, Any]]) -> int:
    """기존 수집 매치들에 platform/region 태그를 부여합니다."""
    na_seed_ids: Set[str] = set()
    if BACKUP_DIR.exists():
        for p in BACKUP_DIR.glob("*_pro_matches.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                for m in d.get("matches", []):
                    if m.get("match_id"):
                        na_seed_ids.add(m["match_id"])
            except Exception:
                pass

    updated = 0
    for bundle in bundles.values():
        for m in bundle["matches"]:
            if not m.get("region") or not m.get("platform"):
                if m.get("match_id") in na_seed_ids:
                    m["platform"] = "steam"
                    m["region"] = "na"
                else:
                    m["platform"] = "steam"
                    m["region"] = "as"
                updated += 1
    return updated


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regions", default="kakao,eu,na,sea", help="수집할 권역 키 (쉼표 구분)")
    ap.add_argument("--top", type=int, default=15, help="리더보드 모드별 상위 N명")
    ap.add_argument("--modes", default="squad-fpp,squad", help="리더보드 모드 (쉼표 구분)")
    ap.add_argument("--per-region", type=int, default=18, help="권역당 새로 수집할 최대 매치 수")
    ap.add_argument("--upgrade", action="store_true",
                    help="킬 이벤트/생존 팀 수가 없는 기존 매치를 다시 받아 제자리에서 보강 (14일 이내 매치만 가능)")
    args = ap.parse_args()

    if not config.PUBG_API_KEY:
        raise SystemExit("PUBG_API_KEY가 없습니다.")

    bundles = {m: load_pro_bundle(m) for m in config.SUPPORTED_MAPS}
    backfilled = backfill_existing_regions(bundles)
    if backfilled:
        print(f"[백필] 기존 매치 {backfilled}건에 platform/region 태그 부여 완료")

    cached_ids: Set[str] = {mm.get("match_id") for b in bundles.values() for mm in b["matches"] if mm.get("match_id")}
    touched_maps: Set[str] = set()
    if backfilled:
        touched_maps.update(m for m, b in bundles.items() if b["matches"])

    if args.upgrade:
        todo = [(mid_, mm) for mid_, b in bundles.items() for mm in b["matches"] if "kills" not in mm]
        print(f"[보강] 킬 이벤트가 없는 기존 매치 {len(todo)}건 재수집 시도")
        done = 0
        for map_id_, mm in todo:
            reg_meta_ = config.PRO_REGION_META.get(mm.get("region", ""))
            if not reg_meta_:
                continue
            try:
                m_resp = requests.get(
                    f"{config.PUBG_API_BASE_URL}/shards/{reg_meta_['api_shard']}/matches/{mm['match_id']}",
                    headers={"Accept": "application/vnd.api+json"}, timeout=20)
                if m_resp.status_code != 200:
                    continue
                m_json = m_resp.json()
                tel_url = next((inc.get("attributes", {}).get("URL") for inc in m_json.get("included", [])
                                if inc.get("type") == "asset"), None)
                if not tel_url:
                    continue
                t_resp = requests.get(tel_url, headers={"Accept-Encoding": "gzip"}, timeout=60)
                if t_resp.status_code != 200:
                    continue
                parsed = _parse_single_telemetry_json(
                    events=t_resp.json(), match_id=mm["match_id"], match_index=mm.get("match_index", 0),
                    map_id=map_id_, size_meter=float(bundles[map_id_]["size_meter"]),
                    team_ranks=extract_team_ranks_from_match_json(m_json))
                if parsed and "kills" in parsed:
                    mm["kills"] = parsed["kills"]
                    for p_str, p_info in parsed["phases"].items():
                        if p_str in mm.get("phases", {}):
                            mm["phases"][p_str]["alive_teams_start"] = p_info.get("alive_teams_start")
                            mm["phases"][p_str]["alive_teams_end"] = p_info.get("alive_teams_end")
                    touched_maps.add(map_id_)
                    done += 1
                    if done % 10 == 0:
                        print(f"  보강 {done}/{len(todo)}")
            except Exception as exc:  # noqa: BLE001
                print(f"  보강 오류 {mm.get('match_id', '')[:8]}: {exc}")
        print(f"[보강] {done}건 완료 (기존 위치·순위 데이터는 그대로 유지)")

    target_regions = [r.strip() for r in args.regions.split(",") if r.strip() in config.PRO_REGION_META and r.strip() != "oc"]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    if target_regions and args.per_region > 0:
        season = current_season_id()
        print(f"[시즌] {season}")

        for reg_key in target_regions:
            reg_meta = config.PRO_REGION_META[reg_key]
            lb_shard = reg_meta["lb_shard"]
            api_shard = reg_meta["api_shard"]
            platform = reg_meta["platform"]

            # 카배는 TPP(squad) 위주이므로 squad를 먼저 조회
            reg_modes = ["squad", "squad-fpp"] if reg_key == "kakao" else modes
            print(f"\n=== [{reg_key.upper()} / {reg_meta['label']}] 리더보드 조회 ===")
            pids = leaderboard_player_ids_for_region(season, lb_shard, reg_modes, args.top)
            if not pids:
                continue

            mids = match_ids_for_region_players(api_shard, pids)
            new_mids = [m for m in mids if m not in cached_ids]
            print(f"  [{reg_key}] 후보 매치 {len(mids)}개 (신규 {len(new_mids)}개)")

            reg_added = 0
            for mid in new_mids:
                if reg_added >= args.per_region:
                    break
                try:
                    m_resp = requests.get(
                        f"{config.PUBG_API_BASE_URL}/shards/{api_shard}/matches/{mid}",
                        headers={"Accept": "application/vnd.api+json"},
                        timeout=20,
                    )
                    if m_resp.status_code != 200:
                        continue
                    m_json = m_resp.json()
                    attrs = m_json.get("data", {}).get("attributes", {})
                    map_id = TELEMETRY_TO_MAP.get(attrs.get("mapName", ""))
                    game_mode = attrs.get("gameMode", "")
                    if not map_id or "squad" not in game_mode:
                        continue
                    tel_url = next(
                        (inc.get("attributes", {}).get("URL") for inc in m_json.get("included", [])
                         if inc.get("type") == "asset"),
                        None,
                    )
                    if not tel_url:
                        continue
                    t_resp = requests.get(tel_url, headers={"Accept-Encoding": "gzip"}, timeout=60)
                    if t_resp.status_code != 200:
                        continue
                    bundle = bundles[map_id]
                    parsed = _parse_single_telemetry_json(
                        events=t_resp.json(),
                        match_id=mid,
                        match_index=len(bundle["matches"]),
                        map_id=map_id,
                        size_meter=float(bundle["size_meter"]),
                        team_ranks=extract_team_ranks_from_match_json(m_json),
                    )
                    if parsed:
                        parsed["platform"] = platform
                        parsed["region"] = reg_key
                        bundle["matches"].append(parsed)
                        cached_ids.add(mid)
                        touched_maps.add(map_id)
                        reg_added += 1
                        print(f"  +[{reg_key}] {map_id} ({reg_added}/{args.per_region})")
                except Exception as exc:  # noqa: BLE001
                    print(f"  매치 {mid[:8]} 오류: {exc}")

    print("\n[저장] 맵별 JSON 및 권역 통계 갱신 중...")
    for map_id in touched_maps:
        bundle = bundles[map_id]
        if not bundle["matches"]:
            continue
        for i, mm in enumerate(bundle["matches"]):
            mm["match_index"] = i
        bundle["num_matches"] = len(bundle["matches"])
        bundle["region_counts"] = compute_region_counts(bundle["matches"])
        raw_path = config.DATA_RAW_DIR / f"{map_id}_pro_matches.json"
        raw_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        out_path = config.DATA_PROCESSED_DIR / f"{map_id}_pro_spots.json"
        if not out_path.exists() and len(bundle["matches"]) < MIN_PRO_MATCHES:
            print(f"  {map_id}: {len(bundle['matches'])}매치 < {MIN_PRO_MATCHES} → 원본만 저장")
            continue
        spots = calculate_spot_probabilities(bundle)
        spots["cache_profile"] = "pro"
        spots["region_counts"] = bundle["region_counts"]
        out_path.write_text(json.dumps(spots, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 최종 맵별 권역 누적 현황 ===")
    for map_id, bundle in bundles.items():
        if bundle["matches"]:
            rc = compute_region_counts(bundle["matches"])
            print(f"  {map_id} (총 {len(bundle['matches'])}판): {rc}")


if __name__ == "__main__":
    main()
