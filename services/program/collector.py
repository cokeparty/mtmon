"""
프로그램변경 월간 수집 — A서버(이관 로그) 수집 → NFS 파일 매칭 → SR 매핑 → 판정 → 적재.
배치잡 program_monthly(batch/jobs.py) 와 화면의 '수집 실행' 버튼이 이 함수를 쓴다.
"""
from datetime import datetime
import shlex
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models.program import ProgramChangeLog
from services.common import server_config as cfg_svc
from services.program import sr_mapper
from services.program import view as pcl_view
from services.program import sftp as collector
from services.program import nfs_scanner, judger as pcl_judger
from services.program.nfs_scanner import NfsConfig
from services.common import sr
from services.common.period import get_or_create_period, is_closed

def _in_year_month(deploy_time, year_month: str) -> bool:
    """deploy_time 이 'YYYY-MM' 에 속하는지."""
    if deploy_time is None:
        return False
    d = deploy_time.date() if hasattr(deploy_time, "date") else deploy_time
    y, m = map(int, year_month.split("-"))
    return d.year == y and d.month == m


def _build_nfs_cfg(cfg, sys_code: str, year_month: str) -> NfsConfig:
    """ServerConfig(SQLAlchemy 모델) → NfsConfig(dataclass) 변환."""
    year, month = year_month.split("-")
    m = month.lstrip("0")
     # ── DB enum → 실제 NFS 폴더명 매핑 ──────────────────
    folder_map = {
        "HR":     "ERP(HR)",
        "EPRO":   "전자조달",     # ★ EPRO 만 폴더명이 다름
        "SR":     "ITSD",
        "PMS":    "PMS",
        "TEST01": "TEST01",
    }
    
    folder = folder_map.get(sys_code, sys_code)   # 매핑 없으면 그대로 사용


    path_globs = [
        "00.*",            # 00.프로그램이관  (한글 → 셸 glob 전개)
        folder,          # PMS 등 업무명
        f"{year}*",        # 2026*  → 2026년
        f"*{m}월*",       # 03*    → 03월
    ]

    return NfsConfig(
        host=cfg.nfs_ssh_host,
        port=cfg.nfs_ssh_port or 22,
        user=cfg.nfs_ssh_user,
        base_dir=cfg.nfs_base_dir,
        key_path=cfg.nfs_ssh_key_path or None,
        password=getattr(cfg, "nfs_ssh_password", None) or None,
        path_globs=path_globs,           # ★ 추가된 인자
        encoding="cp949",
    )


def collect(db: Session, system_code: str, year_month: str) -> dict:
    # 0) 회차 확인(없으면 생성) + 잠금 검사
    period = get_or_create_period(db, year_month)
    if is_closed(period):
        raise PermissionError("마감된 회차 - 수집 불가")

    cfg = cfg_svc.get_by_system(db, system_code)
    ym = year_month.replace("-", "")  # YYYYMM


    # 1) A서버 수집 (HR 분기 추가)
    if system_code == "HR":
        # HR만 ls -alR 기반: log_pattern/cat 미사용, grep만 적용
        ls_dir = cfg.log_dir
        # ym(YYYYMM)으로 grep 패턴 구성: fmb.202603 형태
        grep_pat = f"fmb\\.{ym}"
        cmd = f"cd {shlex.quote(ls_dir)} && ls -alR | grep {shlex.quote(grep_pat)}"
    else:
        cmd = collector.build_command(cfg.log_dir, cfg.log_pattern, ym,
                                  cfg.include_path, cfg.include_flag)
    import logging
    log = logging.getLogger(__name__)
    log.info("[FTP서버] 로그 수집 시작 | system=%s host=%s year_month=%s",
             system_code, cfg.ssh_host, year_month)
    log.debug("[FTP서버] 실행 명령: %s", cmd)

    raw = collector.run_remote(cfg, cmd, system_code)

    log.info("[FTP서버] 수집 완료 | system=%s host=%s | 응답 %d bytes",
             system_code, cfg.ssh_host, len(raw) if raw else 0)
    log.debug("[FTP서버] 응답 샘플: %r", raw[:300] if raw else raw)

    # 시스템별 파서 분기
    if system_code == "HR":
        # HR: ls -alR 출력 → 전용 파서
        records = collector.parse_lines_hr(raw, default_year=int(year_month[:4]))
    elif system_code == "SR":
        # SR: sftp-server 로그 형식 → 전용 파서
        records = collector.parse_lines_sr(raw, default_year=int(year_month[:4]))
    else:
        # EPRO, PMS: 표준 FTP xferlog 형식
        records = collector.parse_lines(raw, default_year=int(year_month[:4]))
       
    # 2) NFS 인덱스
    #index = nfs_scanner.build_index(_build_nfs_cfg(cfg))

    nfs_cfg = _build_nfs_cfg(cfg, system_code, year_month)
    log.info("[NFS서버] 인덱스 구축 시작 | system=%s host=%s", system_code, nfs_cfg.host)
    index = nfs_scanner.build_index(nfs_cfg)
    log.info("[NFS서버] 인덱스 구축 완료 | system=%s | 파일 수=%d", system_code, len(index))

    # 3) SR DB
    
    sr_client = sr.client()

    stats = dict(parsed_lines=len(records), inserted=0, skipped_dup=0,
                 skipped_out_of_range=0,        # ← 추가
                 count_none=0, count_conflict=0, count_abnormal=0, count_normal=0)
    
   
    for rec in records:
        # ★ 지정한 회차(year_month)에 안 맞는 라인은 버림 (2024-11 등 차단)
        if not _in_year_month(rec.deploy_time, year_month):
            stats["skipped_out_of_range"] += 1
            continue
    
        mr = sr_mapper.map_basename(rec.file_name, rec.deploy_time, index)
      
    

        sr_meta = sr_client.fetch(mr.sr_no) if mr.sr_no else None
        wt = sr_meta.sr_work_type if sr_meta else None

        j = pcl_judger.judge(mr.map_type, mr.sr_no, wt, rec.deploy_time,
                             sr_meta.sr_approved_at if sr_meta else None,
                             sr_meta.sr_closed_at if sr_meta else None)

        sr_approved_at = sr_meta.sr_approved_at if sr_meta else None
        row = ProgramChangeLog(
            period_id=period.id, system_code=system_code,
            log_month=rec.log_month, log_day=rec.log_day, log_time=rec.log_time,
            deploy_time=rec.deploy_time, file_name=rec.file_name,
            full_path=rec.full_path, deployer=rec.deployer,
            nfs_path=mr.nfs_path, nfs_mtime=mr.nfs_mtime, map_type=mr.map_type,
            sr_no=mr.sr_no,
            sr_title=sr_meta.sr_title if sr_meta else None,
            sr_work_type=wt,
            sr_approved_at=sr_approved_at,
            sr_closed_at=sr_meta.sr_closed_at if sr_meta else None,
            sr_developer=sr_meta.sr_developer if sr_meta else None,
            sr_reviewer=sr_meta.sr_reviewer or pcl_view.REVIEWER_DEFAULT if sr_meta else pcl_view.REVIEWER_DEFAULT,
            # 결재 컬럼 기본값 즉시 적재
            approval_change_request=pcl_view.APPROVAL_DEFAULT,
            approval_user_test=pcl_view.APPROVAL_DEFAULT,
            # '이관전 승인'은 컬럼에 고정 저장하지 않는다(NULL).
            # → 화면/엑셀이 항상 최신 작업승인일 vs 이관일로 라이브 계산(_pick 폴백).
            #   SR을 나중에 올바르게 입력하면 O/X 가 자동 재계산된다(self-healing).
            approval_pre_deploy=None,
            transferer=pcl_view.TRANSFERER_DEFAULT,
            result=j.result, normal_yn=j.normal_yn, reason=j.reason,
        )
        db.add(row)
        try:
            db.commit()
            stats["inserted"] += 1
        except IntegrityError as e:
            db.rollback()
            # 같은 회차·시스템·이관시각·파일명이 이미 있으면(uq_pcl_dedup) 중복이라 건너뛴다.
            # 그 밖의 DB 오류(필수값 누락·참조 오류 등)는 숨기지 않고 실패로 올린다.
            constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_pcl_dedup":
                stats["skipped_dup"] += 1
                continue
            log.error("[적재 오류] system=%s file=%s deploy_time=%s | %s",
                      system_code, rec.file_name, rec.deploy_time, e.orig)
            raise RuntimeError(
                f"적재 중 DB 오류 (파일 {rec.file_name}, 이관시각 {rec.deploy_time}): {e.orig}"
            ) from e

        if mr.map_type == "none":
            stats["count_none"] += 1
        elif mr.map_type == "conflict":
            stats["count_conflict"] += 1
        if j.normal_yn == "이상":
            stats["count_abnormal"] += 1
        else:
            stats["count_normal"] += 1

    return dict(stats, collected_at=datetime.now(), executed_command=cmd,
                system_code=system_code, year_month=year_month)
