import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from services.nfs_scanner import NfsHit
from models.program_change import MapType


# ─────────────────────────────────────────────────────────────────────────────
# sr_mapper.py
# [수정이력]
# 2026-06-03  동일 basename / 복수 SR 처리: 시간차 기반 강제선택 (구버전, deprecated)
# 2026-06-XX  방침 변경: "확실한 것만 자동 매핑, 애매하면 확인필요"
#   배경:
#     - 시간차 최소 후보를 '억지로' 고르면 basename 충돌/재배포 케이스에서 오답 생성.
#     - 무리한 추측보다, 확실한 것만 자동 확정하고 나머지는 사람이 보게 분리.
#   변경:
#     - map_basename: 후보 1개일 때만 확정(single). 0개→none, 2개+→check.
#       더 이상 시간차로 억지 선택하지 않음.
#     - map_session: 연속 배포(gap<=N분)를 한 세션으로 묶고, 세션 내
#       '후보 1개로 확정되는 파일(앵커)'의 SR이 단일하면 충돌 파일도
#       앵커 SR로 확정(session_anchor). 앵커 0종/2종+면 충돌 파일은 check.
#   비고:
#     - nfs_mtime  = NFS 폴더 업로드(수정) 시각 (mtime)
#     - deploy_time = FTP(xferlog) 배포 시각
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MapResult:
    sr_no: Optional[str]
    nfs_path: Optional[str]
    nfs_mtime: Optional[datetime]
    map_type: MapType


@dataclass
class DeployItem:
    """배포 로그 한 줄 (세션 매핑 입력)."""
    file_name: str
    deploy_time: datetime


def _to_basename(file_name: str) -> str:
    name = file_name.replace("\\", "/").rstrip("/")
    return name.rsplit("/", 1)[-1]


# SR 번호 내장 날짜: 'A01-20260103-001' → 2026-01-03
_SR_DATE_RE = re.compile(r"[A-Za-z]\d{2}-(\d{8})-\d{3}")


def _sr_date(sr_no: Optional[str]):
    """SR 번호에 내장된 등록일(date). 파싱 실패 시 None."""
    if not sr_no:
        return None
    m = _SR_DATE_RE.search(sr_no)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _resolve_by_date(candidates, deploy_time):
    """파일명 충돌(후보 2개+) 시 SR 번호 내장 날짜로 자동선택.

    규칙: '이관일(deploy_time) 이전(<=)' 후보 중 가장 늦은(가장 가까운 과거) SR 날짜 선택.
      예) FTP 1/10, 후보 …0103 / …0108 → 0108 선택.
    이관일 이전 후보가 하나도 없거나 이관일을 알 수 없으면 None(→ 확인필요).
    """
    if deploy_time is None:
        return None
    dep = deploy_time.date() if hasattr(deploy_time, "date") else deploy_time

    best = None
    best_date = None
    for c in candidates:
        d = _sr_date(c.sr_no)
        if d is None or d > dep:
            continue
        if best_date is None or d > best_date:
            best, best_date = c, d
    return best


def _lookup_candidates(basename, index, encodings=("cp949", "euc-kr", "utf-8")):
    if isinstance(basename, bytes):
        return index.get(basename, [])
    for enc in encodings:
        try:
            key = basename.encode(enc)
        except (UnicodeEncodeError, LookupError):
            continue
        hits = index.get(key)
        if hits:
            return hits
    for key_b, hits in index.items():
        for enc in encodings:
            try:
                if key_b.decode(enc) == basename:
                    return hits
            except (UnicodeDecodeError, LookupError):
                continue
    return []


def map_basename(file_name, deploy_time, index) -> MapResult:
    """
    단일 파일 매핑.
      - 후보 0개  → none
      - 후보 1개  → single (확정)
      - 후보 2개+ → SR 번호 내장 날짜 기준 자동선택(date_resolved).
                    이관일 이전(<=) 후보 중 가장 가까운 과거 SR 선택.
                    이관일 이전 후보가 없으면 check(확인필요).
    NFS 스캔이 이미 대상월 폴더만 인덱싱하므로 후보는 모두 대상월 폴더 소속이며,
    SR 내장 날짜(등록일)는 과거월일 수 있다(그 경우도 정상 매핑 대상).
    """
    basename = _to_basename(file_name)
    candidates = _lookup_candidates(basename, index)

    if len(candidates) == 0:
        return MapResult(None, None, None, MapType.none)

    if len(candidates) == 1:
        c = candidates[0]
        return MapResult(c.sr_no, c.nfs_path, c.nfs_mtime, MapType.single)

    # 후보 2개+ : FTP 이관일 기준 가장 가까운 과거 SR 자동선택
    picked = _resolve_by_date(candidates, deploy_time)
    if picked is not None:
        return MapResult(picked.sr_no, picked.nfs_path, picked.nfs_mtime,
                         MapType.date_resolved)

    return MapResult(None, None, None, MapType.check)


def _split_sessions(items: List[DeployItem], gap_min: int) -> List[List[DeployItem]]:
    """deploy_time 정렬 후, 인접 간격이 gap_min 분 이내면 같은 세션."""
    if not items:
        return []
    ordered = sorted(items, key=lambda x: x.deploy_time)
    gap = timedelta(minutes=gap_min)
    sessions, cur = [], [ordered[0]]
    for prev, item in zip(ordered, ordered[1:]):
        if item.deploy_time - prev.deploy_time <= gap:
            cur.append(item)
        else:
            sessions.append(cur)
            cur = [item]
    sessions.append(cur)
    return sessions


def map_session(items: List[DeployItem], index, gap_min: int = 5) -> Dict[DeployItem, MapResult]:
    """
    세션 단위 매핑.
      1) gap_min 분 이내 연속 배포를 한 세션으로 묶음
      2) 세션 내 '후보 1개로 확정되는 파일(앵커)'들의 SR 집합 수집
      3) 판정:
         - 후보 1개                                  → single
         - 후보 2개+ & 앵커 SR 정확히 1종
                     & 충돌 후보의 SR 집합 ⊆ 앵커 SR  → session_anchor
         - 그 외 (앵커 0종/2종+, 충돌후보가 앵커밖 SR 포함, 후보 0개)
                                                     → check / none

    [2026-06-XX 보강] '오염된 앵커' 방지:
      재배포/복합 세션에서 단독파일 앵커(예: 210-004)에 충돌파일(후보 {210-004,427-001})이
      빨려들어가 오답이 나던 문제. 충돌 후보 SR 중 앵커에 없는 SR이 하나라도 있으면
      세션이 복수 SR에 걸쳐 있다는 신호 → 해당 파일은 자동확정하지 않고 check.
    """
    results: Dict[DeployItem, MapResult] = {}

    for sess in _split_sessions(items, gap_min):
        sess_cands = {
            it: _lookup_candidates(_to_basename(it.file_name), index)
            for it in sess
        }
        anchor_srs = {
            cands[0].sr_no
            for cands in sess_cands.values()
            if len(cands) == 1
        }
        single_anchor = next(iter(anchor_srs)) if len(anchor_srs) == 1 else None

        for it in sess:
            cands = sess_cands[it]

            if len(cands) == 0:
                results[it] = MapResult(None, None, None, MapType.none)
                continue

            if len(cands) == 1:
                c = cands[0]
                results[it] = MapResult(c.sr_no, c.nfs_path, c.nfs_mtime, MapType.single)
                continue

            # 후보 2개+ : 앵커로 풀 수 있는지 검증
            if single_anchor is not None:
                cand_srs = {c.sr_no for c in cands}
                # ★ 가드: 충돌 후보의 SR이 모두 앵커 SR 안에 있을 때만 확정.
                #    앵커 밖 SR(예: 427-001)이 섞여 있으면 복합세션 → check.
                if cand_srs <= anchor_srs:
                    match = [c for c in cands if c.sr_no == single_anchor]
                    if match:
                        c = match[0]
                        results[it] = MapResult(c.sr_no, c.nfs_path, c.nfs_mtime,
                                                MapType.session_anchor)
                        continue

            results[it] = MapResult(None, None, None, MapType.check)

    return results
