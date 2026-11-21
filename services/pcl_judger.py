from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from config import settings


@dataclass
class Judgement:
    result: str      # 정상/SR없음/경고/이상
    normal_yn: str   # 정상/이상
    reason: Optional[str]


# SQL CASE 에서 실제로 나오는 긴급변경 계열 라벨
EMERGENCY_TYPES = {"긴급변경_사후", "데이터긴급변경"}

def _to_date(v) -> Optional[date]:
    """date / datetime / 문자열 / None 을 date 로 통일."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):           # datetime 은 위에서 걸러짐 → 순수 date
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    return v


def judge(map_type: str, sr_no: Optional[str], sr_work_type: Optional[str],
          deploy_time: datetime, sr_approved_at, sr_closed_at) -> Judgement:

    # [SR없음] NFS 매핑 실패
    if map_type == "none" or (sr_no is None and map_type != "conflict"):
        return Judgement("SR없음", "이상", "NFS 매핑 실패 - SR번호 없음")

    # [매핑충돌] 전송시각 이전 파일 없음
    if map_type == "conflict":
        return Judgement("경고", "이상", "동일 파일명 다수 - 전송시각 이전 후보 없음(검토필요)")

    # --- 타입 정규화: 모두 date 또는 None 으로 통일 ---
    deploy_date    = _to_date(deploy_time)
    sr_approved_at = _to_date(sr_approved_at)
    sr_closed_at   = _to_date(sr_closed_at)

    if deploy_date is None:
        return Judgement("이상", "이상", "배포(이관)시각 없음")

    # [공통] 작업승인일 있고 배포일이 승인일 이후 → 정상 (긴급변경 포함)
    if sr_approved_at is not None and deploy_date >= sr_approved_at:
        return Judgement("정상", "정상", None)

    # [긴급변경] 사후 승인 허용  (긴급변경_사후 / 데이터긴급변경)
    if sr_work_type in EMERGENCY_TYPES:
        if sr_closed_at is None:
            return Judgement("이상", "이상", "긴급변경 SR종료일 없음")
        if sr_closed_at <= deploy_date + timedelta(days=settings.EMERGENCY_GRACE_DAYS):
            return Judgement("정상", "정상", None)
        return Judgement("이상", "이상",
                         f"긴급변경 사후승인 기한초과(+{settings.EMERGENCY_GRACE_DAYS}일)")

    # [일반 SR]
    if sr_approved_at is None:
        return Judgement("이상", "이상", "작업승인일 없음")
    return Judgement("이상", "이상", "사전배포(승인일 이전 이관)")
