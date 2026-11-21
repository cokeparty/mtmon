"""
============================================================
 services/pcl_view.py
------------------------------------------------------------
 프로그램변경 리스트의 '표시용 파생값' 공용 계산 모듈.
 웹(API 응답)과 엑셀이 항상 동일한 값을 내도록 한 곳에서 계산한다.
   - display_file_name : 파일경로+파일명 단일 표기 (HR 타임스탬프 복원)
   - compute_ui_status : 검증결과 (정상/비정상/미적용)
   - monitoring_result : 모니터링결과 텍스트
   - default_pre_deploy : '이관전 승인' 디폴트(O/X)
   - effective_fields  : 편집가능 6칼럼 표시값(저장값 우선, 없으면 디폴트)
============================================================
"""
from typing import Optional

# ── 편집가능 칼럼 디폴트값 ──
APPROVAL_DEFAULT  = "O"
TRANSFERER_DEFAULT = "이기헌"
REVIEWER_DEFAULT   = "노광환"


def display_file_name(system_code, file_name, full_path, deploy_time) -> str:
    """파일경로+파일명 을 합친 단일 '파일명' 표기.

    - HR: 경로 정보가 없고 file_name 은 타임스탬프가 잘려 있으므로
          deploy_time 으로 `.YYYYMMDD.HHMMSS` 를 복원해 붙인다.
          (예: IS_OS05.fmb → IS_OS05.fmb.20260507.074040)
    - 그 외: full_path 가 이미 '경로+파일명' 을 포함 → 그대로 사용.
    """
    fn = (file_name or "").strip()
    fp = (full_path or "").strip()
    if (system_code or "").strip().upper() == "HR":
        if deploy_time is not None:
            try:
                return f"{fn}.{deploy_time.strftime('%Y%m%d.%H%M%S')}"
            except Exception:
                return fn
        return fn
    return fp or fn


def compute_ui_status(sr_no, result_val, sr_in_db: Optional[bool]) -> str:
    """검증결과: 정상 / 비정상 / 미적용.

    - SR번호 없음            → 미적용
    - SR DB에 존재하지 않음   → 미적용
    - 판정 result 가 '정상'   → 정상
    - 그 외                  → 비정상
    """
    if not sr_no:
        return "미적용"
    if sr_in_db is False:
        return "미적용"
    if result_val == "정상":
        return "정상"
    return "비정상"


# ── 판정기(pcl_judger)가 자동 생성하는 사유 ──
# DB의 reason 컬럼에는 적재 배치가 판정 진단문(아래)을 채워 넣지만,
# 화면/엑셀의 '모니터링결과'는 사용자가 직접 작성한 비정상 사유만 보여야 하므로
# 이 진단문들은 '미작성'으로 취급한다.
_AUTO_REASONS = {
    "NFS 매핑 실패 - SR번호 없음",
    "동일 파일명 다수 - 전송시각 이전 후보 없음(검토필요)",
    "배포(이관)시각 없음",
    "긴급변경 SR종료일 없음",
    "작업승인일 없음",
    "사전배포(승인일 이전 이관)",
}
_AUTO_REASON_PREFIXES = ("긴급변경 사후승인 기한초과",)


def is_user_reason(reason) -> bool:
    """사용자가 직접 작성한 비정상 사유인지 여부(자동 판정사유 제외)."""
    r = (reason or "").strip()
    if not r or r in _AUTO_REASONS:
        return False
    return not any(r.startswith(p) for p in _AUTO_REASON_PREFIXES)


def monitoring_result(ui_status: str, reason) -> str:
    """모니터링결과 텍스트.
    - 정상   → '특이사항 없음'
    - 미적용 → 'SR번호 없음'
    - 비정상 → 사용자가 작성한 사유(있으면) / 없으면 '사유 작성이 필요함'
              (판정기 자동 진단문은 사유로 보지 않음)
    """
    if ui_status == "정상":
        return "특이사항 없음"
    if ui_status == "미적용":
        return "SR번호 없음"
    r = (reason or "").strip()
    return r if is_user_reason(r) else "사유 작성이 필요함"


def _as_date(v):
    """datetime / date / pd.Timestamp / 'YYYY-MM-DD...' 문자열 → date. 실패 시 None."""
    if v is None:
        return None
    # datetime·pd.Timestamp 는 .date() 보유. date 는 .date() 없음(그대로 사용).
    if hasattr(v, "date") and not isinstance(v, str):
        try:
            return v.date()
        except Exception:
            return None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            from datetime import datetime as _dt
            return _dt.strptime(s[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return v  # 이미 date


def default_pre_deploy(deploy_time, sr_approved_at) -> str:
    """'이관전 승인' 디폴트: 작업승인일 <= 이관일(날짜 기준) → O, 아니면 X.

    작업승인일은 '그 날의 24:00'로 상정한다. 즉 승인일과 이관일이 같은 날이면
    시각(시:분)에 관계없이 O(승인일 당일 이관은 이관전 승인으로 본다).
    양변을 date 로 정규화하므로 P-6(시간 추가) 이후에도 당일 O 규칙이 유지된다.
    """
    dt   = _as_date(deploy_time)
    appr = _as_date(sr_approved_at)
    if dt is None or appr is None:
        return "X"
    return "O" if appr <= dt else "X"


def _pick(stored, default) -> str:
    """저장값이 있으면 그대로, 없으면(빈문자/None) 디폴트."""
    s = (stored or "").strip() if stored is not None else ""
    return s if s else default


def effective_fields(r) -> dict:
    """편집가능 6칼럼의 화면/엑셀 표시값.

    저장값(컬럼)이 있으면 그 값을, 없으면 디폴트를 돌려준다.
    r 은 ProgramChangeLog ORM 행 또는 동일 속성을 갖는 객체.
    """
    return {
        "approval_change_request": _pick(r.approval_change_request, APPROVAL_DEFAULT),
        "approval_user_test":      _pick(r.approval_user_test, APPROVAL_DEFAULT),
        "approval_pre_deploy":     _pick(
            r.approval_pre_deploy,
            default_pre_deploy(r.deploy_time, r.sr_approved_at),
        ),
        "sr_developer":            (r.sr_developer or "").strip(),  # 디폴트 빈값
        "transferer":              _pick(getattr(r, "transferer", None), TRANSFERER_DEFAULT),
        "sr_reviewer":             _pick(r.sr_reviewer, REVIEWER_DEFAULT),
    }


def row_ui_status(r) -> str:
    """ORM 행의 검증결과(정상/비정상/미적용) — SR DB 조회 없이 result 기준.
    대시보드 집계처럼 행이 많을 때 사용한다."""
    result_val = r.result.value if hasattr(r.result, "value") else (r.result or "")
    return compute_ui_status(r.sr_no or "", result_val, None)
