"""
============================================================
 schemas/program_change.py
------------------------------------------------------------
 [수정 내역]
 2026-xx-xx  화면 역할 변경: '실시간 수집' → '조회 전용'
   1) CollectRequest 삭제  (웹 수집 트리거 폐지)
   2) CollectResult  삭제  (수집 응답 스키마 폐지)
      → 수집 통계는 배치 스크립트가 로그로만 출력
   3) LoadInfo 추가  (푸터 표시용 배치 적재 메타)
   4) 미사용 import 정리 (datetime → LoadInfo에서만 사용)
   5) approval_* 3필드 Optional 처리 (DB NULL → 검증 500 해결)
============================================================
"""
from datetime import datetime, date, time
from typing import Optional, List, Literal
from pydantic import BaseModel, computed_field

from services import pcl_view

SystemLiteral = Literal["HR", "EPRO", "SR", "PMS"]
ResultLiteral = Literal["전체", "정상", "SR없음", "경고", "이상"]


class ProgramChangeRow(BaseModel):
    """프로그램변경 리스트 1행. 편집 6칼럼은 저장값이 없으면 디폴트가 적용된다."""
    id: int
    system_code: Optional[str] = None
    deploy_time: Optional[datetime] = None  # 이관시각 (yyyy-mm-dd HH:MM:SS)
    deployer: Optional[str] = None          # 접속계정
    file_name: str
    full_path: Optional[str] = None         # 파일경로 (file_name 과 합쳐 display_name 으로 표출)
    sr_no: Optional[str] = None
    sr_title: Optional[str] = None
    sr_work_type: Optional[str] = None
    sr_approved_at: Optional[datetime] = None  # 작업승인일 (날짜+시각)
    sr_closed_at: Optional[datetime] = None    # SR종료일 (날짜+시각)
    approval_change_request: Optional[str] = None
    approval_user_test: Optional[str] = None
    approval_pre_deploy: Optional[str] = None
    transferer: Optional[str] = None        # 이관자
    sr_developer: Optional[str] = None
    sr_reviewer: Optional[str] = None
    result: str
    normal_yn: str
    reason: Optional[str] = None
    map_type: str
    sr_in_db: Optional[bool] = None  # router에서 SR DB 조회 후 설정

    # ── 파생 표시값 (웹/엑셀 공용 pcl_view 로 계산) ──
    @computed_field
    @property
    def ui_status(self) -> str:
        """검증결과: 정상/비정상/미적용."""
        return pcl_view.compute_ui_status(self.sr_no, self.result, self.sr_in_db)

    @computed_field
    @property
    def display_name(self) -> str:
        """파일경로+파일명 단일 표기 (HR 타임스탬프 복원)."""
        return pcl_view.display_file_name(
            self.system_code, self.file_name, self.full_path, self.deploy_time)

    @computed_field
    @property
    def monitoring_result(self) -> str:
        """모니터링결과 텍스트."""
        return pcl_view.monitoring_result(self.ui_status, self.reason)

    @computed_field
    @property
    def user_reason(self) -> str:
        """사용자가 직접 작성한 비정상 사유(자동 판정사유 제외)."""
        return self.reason if pcl_view.is_user_reason(self.reason) else ""

    @computed_field
    @property
    def eff_approval_change_request(self) -> str:
        return pcl_view._pick(self.approval_change_request, pcl_view.APPROVAL_DEFAULT)

    @computed_field
    @property
    def eff_approval_user_test(self) -> str:
        return pcl_view._pick(self.approval_user_test, pcl_view.APPROVAL_DEFAULT)

    @computed_field
    @property
    def eff_approval_pre_deploy(self) -> str:
        return pcl_view._pick(
            self.approval_pre_deploy,
            pcl_view.default_pre_deploy(self.deploy_time, self.sr_approved_at))

    @computed_field
    @property
    def eff_transferer(self) -> str:
        return pcl_view._pick(self.transferer, pcl_view.TRANSFERER_DEFAULT)

    @computed_field
    @property
    def eff_sr_reviewer(self) -> str:
        return pcl_view._pick(self.sr_reviewer, pcl_view.REVIEWER_DEFAULT)

    @computed_field
    @property
    def eff_sr_developer(self) -> str:
        return (self.sr_developer or "").strip()   # 디폴트 빈값

    class Config:
        from_attributes = True


class ProgramChangeListResponse(BaseModel):
    year_month: str
    system_code: str
    total: int
    rows: List[ProgramChangeRow]


class SrUpdate(BaseModel):
    sr_no: str


class FieldUpdate(BaseModel):
    """편집가능 칼럼 부분 수정. 보낸 필드만 반영(exclude_unset)."""
    approval_change_request: Optional[str] = None
    approval_user_test: Optional[str] = None
    approval_pre_deploy: Optional[str] = None
    transferer: Optional[str] = None
    sr_developer: Optional[str] = None
    sr_reviewer: Optional[str] = None
    reason: Optional[str] = None


class LoadInfo(BaseModel):
    """배치 적재 메타 (GET /api/load-info 응답). 푸터 표시용."""
    period: str
    loaded_at: Optional[datetime] = None
    row_count: int
    sources: str = "NFS / SR DB / 업로드서버 로그"
