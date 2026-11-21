# 변경 이력

---

## 2026-08-06 (배치/프로그램변경 개선)

### [배치 B-1] 보류 (배치 적재 시각 항상 기록)
- 배치 실행 이력 테이블(`pcl_batch_run`) 방식은 사용자 요청으로 철회. 관련 코드/마이그레이션 원복.
- 현재 적재시각은 기존과 동일하게 마지막 적재행 `created_at` 기준(0건 회차는 미표시). 별도 협의 예정.

### [배치 B-2] 없는 회차 자동 생성
- `services/collect_orchestrator.py` `collect()`: 회차 없으면 `ValueError` 대신 `MonitoringPeriod` 자동 생성(status='open'). 마감 검사는 유지
- 월간 부서이동자는 `dept_transfer_service.run_monthly_collect` 이 이미 `_get_or_create_period` 사용 → 변경 없음

### [배치 B-3] HR 레거시 SSH 옵션 오류 해결
- `services/sftp_log_collector.py` `_run_remote_legacy`: `-oPubkeyAcceptedAlgorithms`(OpenSSH 8.5+) → `-oPubkeyAcceptedKeyTypes`(구·신 호환 별칭) 로 변경. rc=255 & 'Bad configuration option' 시 반대 옵션명으로 1회 폴백 재시도

### [프로그램변경 P-1] 파일명 충돌 시 SR 내장 날짜로 자동매핑
- `services/sr_mapper.py`: `_sr_date()`, `_resolve_by_date()` 추가. `map_basename` 후보 2개+ 일 때 이관일 이전(<=) 후보 중 가장 가까운 과거 SR 선택 → `MapType.date_resolved`. 과거 후보 없으면 기존대로 `check`
- `models/program_change.py` `MapType`: `date_resolved` 추가

### [프로그램변경 P-2-1] (조사) FTP/NFS 조회 범위
- 코드 변경 없음. FTP 로그(build_command `{ym}` 치환 + `_in_year_month` 필터), NFS 폴더(path_globs `{year}*`,`*{m}월*`) 모두 **대상(전월) 회차만** 조회함을 확인

### [프로그램변경 P-3] 배치 실행 버튼
- `routers/program_change.py`: `POST /program-change/api/run` 추가(권한 `can_run_monthly_batch`). 4개 시스템 `run_and_record` 동기 실행
- `templates/program_change.html`: 상단 '🔄 배치 실행' 버튼(operator/reviewer) + 실행결과 박스 + `runPcl()`

### [프로그램변경 P-4] 상단 KPI
- `templates/program_change.html`: 전체/적용완료/사유미입력/미적용/진행률 KPI 카드(공용 `.card-grid`) + `updatePclKpi()` (loadList/saveSr/saveReason 후 갱신, 목록 기반 클라이언트 계산)

### [프로그램변경 P-5] '이관전 승인' 버그 (SR 변경에도 안 바뀜)
- 원인: 배치가 `approval_pre_deploy` 에 확정값을 저장 → `_pick` 이 저장값 우선 → SR 재입력에도 재계산 안 됨
- `services/collect_orchestrator.py`: 배치에서 `approval_pre_deploy=None`(고정 저장 안 함) → 항상 라이브 계산 폴백(self-healing)
- `services/pcl_view.py` `default_pre_deploy`: 양변을 `date`로 정규화(`_as_date`), 작업승인일==이관일이면 O(당일=승인당일 24:00 상정), 타입오류로 조용히 X 되던 문제 제거
- DML: `spec/mirgrations/20260806_pcl_reset_pre_deploy.sql` (기존 행 approval_pre_deploy NULL 리셋)

### [프로그램변경 P-6] 작업승인일·SR종료일 시간 표시
- `models/program_change.py`: `sr_approved_at`/`sr_closed_at` `Date → TIMESTAMP`
- `services/sr_db_client.py` `SrMeta`: `date → datetime`
- `schemas/program_change.py`: 두 필드 `date → datetime`
- `routers/program_change.py` `update_sr`: `_d` 를 'YYYY-MM-DD HH:MM:SS' 로(판정 비교는 날짜 단위 유지)
- `templates/program_change.html`: `_fmtDt()` 로 두 셀에 날짜+시각 인라인 표시
- `services/excel_exporter.py`: 두 셀에 datetime 값 + `number_format='yyyy-mm-dd'`(표시 날짜, 클릭 시 시각)
- DDL: `spec/mirgrations/20260806_pcl_approved_closed_timestamp.sql`

---

## 2026-07-03

### [UI] 로그인·가입 화면 역할 표시 수정
- `templates/login.html`: "검토수행자" → "검토자" (배지 4개가 한 줄에 표시되도록)
- `templates/register.html`: role-chip "검토수행자" → "검토자"

### [권한] CSV 업로드 파일탐색기 차단 (operator 미만 시 picker 자체 미오픈)
- `templates/dml_manager.html`: 업로드 버튼 onclick에 `ROLE !== 'operator'` 사전 체크 추가; `onUpload` 내 중복 role 체크 제거
- `templates/ddl.html`: 동일 패턴 적용 + `ROLE` 상수 추가; `onUpload` 내 role 체크 제거 및 btn.disabled 순서 버그 수정

### [UX] 엑셀 다운로드 로딩 상태 표시
- `templates/dml_manager.html`: 엑셀 버튼에 `id="btn-excel"` 추가; `downloadExcel()`에 finally로 버튼 disable/복원
- `templates/ddl.html`: 엑셀 버튼에 `id="btn-excel-ddl"` 추가; `downloadDdlExcel()`에 finally로 버튼 disable/복원
- `templates/program_change.html`: `exportExcel()`에 버튼 disable + 3초 setTimeout 복원
- `templates/dept_transfer.html`: 엑셀 `<a>` 태그 → `<button id="btn-excel-monthly">` 변환; `downloadMonthlyExcel()` 함수 추가 (fetch 기반, finally 복원)

### [계정관리] 계정 목록 조회/편집 모드 분리
- `templates/admin_users.html` 전면 개편
  - 이름·이메일 칸: 조회 모드에서 텍스트만 표시 (입력 필드 없음)
  - "✏ 편집" 버튼 클릭 시 이름·이메일 입력 필드로 전환 (`editRow(id)`)
  - "저장" 클릭 → `POST /admin/users/{id}/info` 제출; "취소" 클릭 → 원래값 복원 (`cancelRow(id)`)
  - 관리 칼럼(역할변경·PW초기화·활성화) 조회/편집 모드 관계없이 동일 유지
  - 초기 비밀번호 `Mtmon12#` 생성 폼 하단에 명시
- `routers/admin_users.py`: `POST /{user_id}/info` 엔드포인트 추가 (이름+이메일 통합 저장)

### [권한] DML 담당자 화면 — developer 편집 차단 (클라이언트 사전 체크)
- `templates/dml_manager.html`: `CAN_EDIT_MGR = ['operator','reviewer'].includes(ROLE)` 상수 추가
- `mgrApplySr`, `mgrClearSr` 앞에 `if (!CAN_EDIT_MGR)` 체크 추가

### [버그] 권한 부족 시 "저장 실패" toast 이중 표시 수정
- `templates/ddl.html`: `applyDdlSr`, `clearDdlSr`, `saveDdlField`, `saveDdlReason` — `if (r._forbidden) return;` 추가
- `templates/dml_manager.html`: `mgrApplySr`, `mgrClearSr` — `if (r._forbidden) return;` 추가

### [UX] SR 입력 안내 문구 수정 ("적용 버튼" 문구 제거)
- `templates/dml_developer.html`: "Enter 또는 적용 버튼을 누르면" → "Enter 를 누르면"
- `templates/ddl.html`: "Enter 또는 적용 버튼으로 저장합니다" → "Enter 를 누르면 저장됩니다"

---

### [부서이동자] 일간 유지/회수 vs SR입력 권한 분리 (버그수정)

**문제**
- 일간 유지/회수(`/daily/action`)가 developer까지 허용 → 운영자·검토수행자만 허용해야 함
- 일간 SR입력(`/daily/sr`) 엔드포인트에 권한 체크 누락 → viewer도 저장 가능했음
- 프론트 `CAN_DAILY_ACTION` 상수에 developer 포함 → 유지/회수 버튼 사전 체크 오류

**수정**
- `core/permissions.py`
  - `can_daily_dept_action`: operator·reviewer·developer → **operator·reviewer만** (유지/회수용)
  - `can_edit_daily_sr` 함수 신규 추가: operator·reviewer·developer (SR입력용)
- `routers/dept_transfer.py`
  - `can_edit_daily_sr` import 추가
  - `daily_sr` 엔드포인트: `Request` 파라미터 + `can_edit_daily_sr` 체크 추가
  - 라우터 상단 주석 권한 표기 정확하게 수정
- `templates/dept_transfer_daily.html`
  - `CAN_DAILY_ACTION = ['operator', 'reviewer'].includes(ROLE)` (developer 제거)
  - `CAN_DAILY_SR = ['operator', 'reviewer', 'developer'].includes(ROLE)` 신규 추가
  - `saveSr()` 함수 앞에 `if (!CAN_DAILY_SR)` 사전 체크 추가

---

### [계정] 역할 기반 권한 시스템 구현 (항목 1–15)

**신규 파일**
- `core/permissions.py`: 역할별 허용 기능 중앙 정의 함수들
  - `can_upload_csv`, `can_edit_dml_developer`, `can_edit_dml_manager`
  - `can_edit_ddl`, `can_edit_program_change`
  - `can_run_monthly_batch`, `can_run_daily_batch`
  - `can_daily_dept_action`, `can_monthly_dept_action`
- `templates/error_forbidden.html`: 한국어 403 페이지 (항목 14)

**`core/deps.py`**
- `ForbiddenPage` 예외 클래스 추가 (페이지 접근 거부 → HTML 에러)
- `require_operator`, `require_reviewer`: HTTPException 대신 `ForbiddenPage` 발생

**`main.py`**
- `ForbiddenPage` 예외 핸들러 등록 → `error_forbidden.html` 반환 (status 403)

**`templates/base.html`**
- `PERM_DENIED_MSG` 전역 상수 추가
- `postJSON`: 403 응답 시 자동 toast 표시 후 `{ok:false, _forbidden:true}` 반환
- `patchJSON` 함수 추가 (PATCH 메서드 + 403 처리)

**API 엔드포인트 역할 체크 추가 (항목 2–10, 13)**
- `routers/dml_developer.py`: apply-sr, clear-sr, set-dml, bulk-apply-sr, set-reason → viewer 차단
- `routers/dml_manager.py`: upload → operator 전용
- `routers/ddl.py`: upload → operator 전용; apply-sr, clear-sr, save-reason, save-fields → operator·reviewer만
- `routers/program_change.py`: update_sr, update_fields → operator·reviewer만
- `routers/dept_transfer.py`:
  - daily/action → viewer 차단 (operator·reviewer·developer 허용)
  - daily/run → operator 전용
  - monthly/run → operator·reviewer만
  - monthly/sr → operator·reviewer만

**템플릿 클라이언트 사전 체크 추가 (항목 12–13)**
- `dml_developer.html`: `CAN_EDIT_DEV` 상수 + `applySr`, `clearSr`, `toggleDml`, `openReasonModal`, `showBulkPreview` 앞에 viewer 체크
- `dml_manager.html`: `onUpload` — operator 사전 체크 + raw fetch 403 처리
- `ddl.html`: `onUpload` — operator 사전 체크 + raw fetch 403 처리
- `program_change.html`: `saveField` → `patchJSON` 전환; `saveSr`, `saveReason` → patchJSON/403 처리
- `dept_transfer.html`: `CAN_RUN_MONTHLY`, `CAN_EDIT_MONTHLY` 상수 + `runMonthly`, `saveMonthSr` 앞에 체크 + raw fetch 403 처리
- `dept_transfer_daily.html`: `CAN_DAILY_ACTION`, `CAN_DAILY_BATCH` 상수 + `setAction`, `runDailyBatch` 앞에 체크; 유지/회수 버튼 모든 역할에 표시 (기존 reviewer 전용 → 공통 표시)

**`routers/admin_users.py`** (항목 1)
- `_VALID_ROLES`, `_ROLE_LABELS`에 viewer 추가
- `POST /{user_id}/email` 엔드포인트 추가 (이메일 수정)

**`templates/admin_users.html`** (항목 1)
- 이메일 칸: 텍스트 표시 → 인라인 편집 폼으로 교체
- 역할 생성 드롭다운에 조회자(viewer) 추가
- 역할 배지 `.role-viewer` CSS 추가 (보라색 계열)

### [계정] 회원가입 역할 고정 + 로그인 페이지 4역할 안내 (항목 16)

- `routers/auth.py`
  - `_VALID_ROLES`에 `"viewer"` 추가
  - `register_submit`: `role` Form 파라미터 제거, `role = "viewer"` 하드코딩 고정
  - 가입 성공 메시지에 "조회자로 가입, 다른 역할은 관리자 문의" 안내 추가
- `templates/register.html`
  - 역할 선택 라디오 버튼 UI 제거 → `<input type="hidden" name="role" value="viewer">`
  - 역할 안내 박스 추가: 조회자 고정 + 4가지 역할 칩 표시 + 관리자 문의 안내
  - JS 폼 제출 검증에서 역할 체크 코드 제거
- `templates/login.html`
  - 역할 안내 배지에 `👁 조회자` 추가 (4가지 역할 모두 표시)
  - `.role-badge.viewer` CSS 추가 (보라색 계열)

### [DML] SR 빈값 입력 허용 + 작업 칼럼 제거 + CSV 업로드 시간 표시

- `routers/dml_developer.py`
  - `apply_sr_to_group`: 빈 SR 400 반환 제거 (빈값 허용)
  - `bulk_apply_sr`: 빈 SR 400 반환 제거
- `services/dml_service.py`
  - `get_manager_view()`: `last_uploaded_at` 추가 (DmlGroup.created_at max값)
- `templates/dml_manager.html`
  - `mgrApplySr()`: 빈값 toast 검증 제거
  - 테이블 헤더/행에서 **작업** 칼럼(적용/취소 버튼) 제거
  - colspan 15 → 14, CSS td:nth-child(14) 제거, JS actCell 참조 제거
  - 마지막 CSV 업로드 시각 표시 추가
- `templates/dml_developer.html`
  - `applySr()`: 빈값 toast 검증 제거
  - `showBulkPreview()`: 빈 SR toast 검증 제거
  - 테이블 헤더/행에서 **작업** 칼럼 제거 (`id="dbtns-*"` td 포함)
  - colspan 15 → 14, `_renderBtnsCell` 함수 및 호출 제거

### [DDL] SR 빈값 입력 허용 + 작업 칼럼 제거 + CSV 업로드 시간 표시

- `routers/ddl.py`
  - `apply_sr`: 빈 SR 400 반환 제거
- `services/ddl_service.py`
  - `get_view()`: `last_uploaded_at` 추가 (DdlLog.created_at max값)
- `templates/ddl.html`
  - `applyDdlSr()`: 빈값 toast 검증 제거
  - 테이블 헤더/행에서 **작업** 칼럼(적용/취소 버튼) 제거
  - colspan 20 → 19
  - 마지막 CSV 업로드 시각 표시 추가

### [DML] 엑셀 다운로드 성능 개선 (10k+ 행 5초 이내)

- `services/dml_service.py`
  - `export_excel()`: openpyxl `write_only=True` 모드로 전환
  - `WriteOnlyCell` 사용으로 헤더 굵기 + 검증결과 셀 색상 적용
  - `ws.cell(row=ws.max_row)` 재접근 제거 → 행 스트리밍 방식으로 대용량 성능 개선

### [프로그램변경] 배치 적재 시 기본값 즉시 DB 반영

- `services/collect_orchestrator.py`
  - `collect()`: `ProgramChangeLog` 생성 시 기본값 즉시 적재
    - `approval_change_request = "O"` (프로그램변경요청승인)
    - `approval_user_test = "O"` (사용자테스트)
    - `approval_pre_deploy = default_pre_deploy(deploy_time, sr_approved_at)` (O/X 자동판정)
    - `transferer = "이기헌"` (이관자)
    - `sr_reviewer = sr_meta.sr_reviewer or "노광환"` (검토수행자; SR값 없으면 기본값)
  - `pcl_view` import 추가 (상수 및 `default_pre_deploy` 재사용)

### [부서이동자] SR 빈값 허용 + 배치 실행 시간 표시

- `services/dept_transfer_service.py`
  - `get_daily_view()`: `last_batch_at` 추가 (DailyRecord.updated_at max값)
  - `get_monthly_view()`: `last_batch_at` 추가 (MonthlyRecord.updated_at max값)
- `templates/dept_transfer_daily.html`
  - `saveSr()`: 빈값 toast 검증 제거
  - 마지막 일간 배치 실행 시각 표시 추가
- `templates/dept_transfer.html`
  - `saveMonthSr()`: 빈값 toast 검증 제거
  - 마지막 월간 배치 실행 시각 표시 추가

---

## 2026-07-02 (2차)

### [대시보드] 진행률 기준 변경 + 설명 텍스트 수정

**진행률 공식**: 전체에서 **정상 + 비정상(사유 작성)** 비율로 변경
- 기존: PC=정상만, DML/DDL=정상+비정상 전체
- 변경: 3개 모듈 모두 `(정상 + 비정상(사유작성)) / 전체`
- `services/dashboard_service.py`
  - `_pc_summary()`: 루프 내 `ok_count` 추적, 비정상 행에 `is_user_reason(r.reason)` 확인
  - `_dml_summary()`: `ok_applied` 방식 → `ok_count` 추적, `g.get("reason")` 확인
  - `_ddl_summary()`: 동일하게 `l.get("ddl_reason")` 확인
  - `is_user_reason` import 추가 (`services.pcl_view`)
- `templates/dashboard.html`: "SR 적용 / 정상 처리 비율" → "정상 + 비정상(사유 작성) 비율"

---

### [프로그램변경] 화면 범례 설명 구체화

- `templates/program_change.html`
  - 정상: "SR매핑·승인 정상" → "SR 확인 + 작업승인일 이후 이관"
  - 비정상: "SR 매핑됨·판정 이상" → "SR 확인됨 + 미승인 이관·긴급기한 초과 (사유 입력 필요)"
  - 미적용: "SR 미입력" → "SR 미입력 또는 SR DB 미조회"

---

### [부서이동자] 일간 모니터링 월별 조회

**배경**: 데이터가 영구 누적되어 과거 월 데이터까지 섞임. 월별로 분리 조회.

- `services/dept_transfer_service.py` `get_daily_view(db, year_month=None)`
  - `year_month` 파라미터 추가 (기본값 None = 전체)
  - `sqlalchemy.extract`로 `change_date`의 연/월 필터링
- `routers/dept_transfer.py`
  - `_current_ym()` 추가: 당월 "YYYY-MM" 반환 (일간 기본값용, 월간과 다름)
  - `daily_view`: `year_month: str = Query(default=None)` 추가, 기본값=당월
  - 템플릿 컨텍스트에 `year_month` 전달
- `templates/dept_transfer_daily.html`
  - 상단 actions에 `<input type="month">` 추가 (값 변경 시 해당 월로 이동)
  - `runDailyBatch()`: 배치 완료 후 reload 시 선택한 월 유지

---

## 2026-07-02

### [프로그램변경] SR 저장 시 검증결과 새로고침 불일치 버그 수정

**원인**: `PATCH /api/{row_id}/sr` 가 `row.result` / `row.normal_yn` 을 DB에 저장하지 않아,
새로고침 시 `compute_ui_status`가 배치 원본값(이상)을 그대로 읽어 "비정상"으로 표시되는 현상.

**변경 파일**
- `routers/program_change.py` `update_sr()`
  - `judge_validation()` 호출을 `db.commit()` 앞으로 이동
  - ui_status 결정 직후 `row.result` / `row.normal_yn` 을 같은 commit 에 포함
    - 정상 → `result="정상"`, `normal_yn="정상"`
    - 비정상 → `result="이상"`, `normal_yn="이상"`
    - 미적용(SR 없음 or SR DB 미조회) → `result="SR없음"`, `normal_yn="이상"`

---

### [프로그램변경/공통] 로그 개선

**콘솔 print 제거**
- `services/pcl_judger.py` — `_J` 디버그 래퍼(print) 제거, `Judgement()` 직접 반환으로 단순화
- `services/nfs_scanner.py` — `print(full_glob)`, `print("INDEX SIZE :")` 등 모두 제거, `logging` 으로 대체

**application 로그 상세화**
- `routers/program_change.py` `update_sr()` — SR 조회/저장 흐름 INFO 로그 추가
  (sr_no, sr_found, sr_work_type, sr_approved_at, sr_closed_at, 검증결과)
- `services/collect_orchestrator.py` — 수집 시작/완료(host·system·bytes) INFO 로그 추가,
  명령 전문과 응답 샘플은 DEBUG 레벨로 격하
- `services/nfs_scanner.py` — 인덱스 구축 완료(host·파일 수) INFO, 샘플은 DEBUG 레벨
- `services/sftp_log_collector.py` — SSH 진단 상세는 DEBUG 레벨로 격하

**FTP서버/NFS서버 읽기 권한 오류 로깅 추가**
- `services/sftp_log_collector.py` `_run_remote_paramiko()` — stderr 캡처 후
  "permission denied" / "cannot open" 포함 줄을 WARNING 으로 기록
- `services/nfs_scanner.py` `build_index()` — stderr 의 권한 오류 줄을 WARNING 으로 기록

**서버 레이블 구체화 (A서버→FTP서버, B서버→NFS서버)**
- `services/sftp_log_collector.py` — `[SSH라우팅]`, `[SSH진단/paramiko]`, `[SSH진단/legacy]` →
  `[FTP서버/...]` 형식으로 변경
- `services/collect_orchestrator.py` — `[A서버]` → `[FTP서버]`, `[NFS]` → `[NFS서버]`

**로그 레벨 설정 기능 추가**
- `config.py` — `LOG_LEVEL: str = "INFO"` 추가 (INFO / DEBUG 선택 가능)
  변경 방법: `.env` 파일에 `LOG_LEVEL=DEBUG` 추가 또는 `config.py` 직접 수정
- `core/logging_config.py` — 루트 로거 레벨을 `settings.LOG_LEVEL` 에서 읽도록 변경

---

### [설정] config.py SFTP/NFS 미사용 하드코딩 제거

**원인**: FTP서버·NFS서버 접속 정보는 DB `server_config` 테이블에서 조회하므로 config.py 의
SFTP_SSH_HOST 등 설정은 실제로 사용되지 않음.

**변경 파일**
- `config.py` — `SFTP_SSH_HOST/PORT/USER/KEY_PATH/PASSWORD/LOG_DIR`,
  `NFS_SSH_HOST/PORT/USER/KEY_PATH/PASSWORD/BASE_DIR/ENCODING` 제거

---

## 2026-06-29

### [대시보드] Hero KPI 카드 색상 수정 + 도넛 부서이동자 추가

**Hero KPI 카드**
- `templates/dashboard.html`
  - 프로그램변경 / DML / 프로시저: 정상(초록) · 비정상(주황) · 미적용(빨강) 순으로 태그 표시
    - 기존: 비정상=`tag-bad`(빨강), 미적용=`tag-warn`(주황) → 색상 반전 오류
    - 변경: 정상=`tag-ok`, 비정상=`tag-warn`, 미적용=`tag-bad`
  - 부서이동자: 미적용 `tag-warn`(주황) → `tag-bad`(빨강)으로 변경
- `services/dashboard_service.py`
  - 프로그램변경 / DML / 프로시저 KPI dict에 `normal` 필드 추가
  - DDL `abnormal` 집계 기준을 `sum(abn_system.values())` → `ddl["status"]["비정상"]`으로 통일

**도넛 차트 부서이동자 추가**
- `services/dashboard_service.py`
  - `_dt_summary()` 반환값에 `status` 딕셔너리 추가: `{정상: applied, 비정상: 0, 미적용: pending}`
  - `status_dist` 합산 대상에 `dt` 포함 (PC + DT + DML + DDL)
- `templates/dashboard.html`
  - 도넛 subtitle: "프로그램변경 · DML · DDL 합산" → "프로그램변경 · 부서이동자 · DML · DDL 합산"

---

### [부서이동자] 월간 배치 시 일간 SR 자동 매핑

- `services/dept_transfer_collector.py`
  - `_RTYPE_TO_SYSTEM` 매핑 추가: `HR권한→HR`, `전자조달권한→EPRO`, `PMS권한→PMS`
  - `_sync_sr_from_daily(db, period_id, year_month)` 함수 추가
    - `DailyRecord`에서 `sr_no IS NOT NULL` + 동일 year_month 범위인 행 조회
    - `empno + role_key` 기준으로 `MonthlyRecord` 매칭
    - `MonthlyRecord.sr_no`가 NULL인 경우에만 `sr_no / sr_title / sr_work_type` 복사 (기존 수동 입력 보존)
  - `collect_monthly()` 종료 시 `_sync_sr_from_daily()` 자동 호출 + 결과를 `sr_synced` 필드로 반환

---

### [계정] 계정 관리 페이지 추가

- `config.py`: `INITIAL_PASSWORD: str = "Mtmon12#"` 추가 (`.env`로 재정의 가능)
- `routers/admin_users.py` 신규 (prefix: `/admin/users`)
  - `GET /admin/users` — 계정 목록 (operator 전용)
  - `POST /admin/users/create` — 계정 생성 (초기 비밀번호 자동 부여)
  - `POST /admin/users/{id}/role` — 역할 변경
  - `POST /admin/users/{id}/toggle-active` — 활성화 / 비활성화
  - `POST /admin/users/{id}/reset-password` — 비밀번호 초기화
- `templates/admin_users.html` 신규 — 계정 목록 + 생성 폼 + 인라인 관리 버튼
- `templates/base.html` — operator 역할에만 "계정관리" 내비 링크 노출
- `main.py` — `admin_users` 라우터 등록

---

### [계정] 예상 권한 체계 설계 문서 작성

- `spec/auth/permission.md` — 모듈별 세분화 권한 코드 목록 및 역할별 매핑 작성 (미구현, 설계안)

---

### [DDL] 사유미입력 KPI + 사유입력 + 6개 편집 칼럼 + 엑셀 개선

**KPI 카드 개편**
- `templates/ddl.html`: "위험 DDL" 카드 제거 → "사유미입력(비정상+사유없음)" 카드 추가 (주황)
- `services/ddl_service.py` `get_view()`: KPI 재정의
  - 적용완료 = SR있음 + (정상 OR (비정상+사유있음))
  - 미적용 = SR없음
  - 사유미입력 = 비정상 + 사유없음
  - `summary.abnormal` 제거 → `summary.no_reason` 추가

**사유 입력 기능 추가**
- `models/ddl.py`: `ddl_reason VARCHAR(500)` 컬럼 추가
- `services/ddl_service.py`: `save_reason(log_id, reason, db)` 추가
- `schemas/ddl.py`: `DdlSaveReasonRequest` 추가
- `routers/ddl.py`: `POST /ddl/save-reason` 엔드포인트 추가
- `templates/ddl.html`: 비정상 행에 📝/✎ 플래그 + 사유 입력 모달 추가

**6개 편집 칼럼 추가 (웹 + 엑셀)**
- `models/ddl.py`: 6개 컬럼 추가
  - `proc_change_approval` (기본 O), `user_test` (기본 O), `pre_release_approval`, `developer`, `releaser` (기본 이기헌), `reviewer_name` (기본 노광환)
- `services/ddl_service.py`:
  - `save_fields(log_id, fields, db)` 추가
  - `apply_sr()`: `pre_release_approval` 자동 계산 (작업승인일 <= 요청시각 → O, 아니면 X)
  - `import_csv()`: 신규 행에 기본값 설정
- `schemas/ddl.py`: `DdlSaveFieldsRequest` 추가
- `routers/ddl.py`: `POST /ddl/save-fields` 추가
- `templates/ddl.html`: 6개 편집 입력칸 추가, `_paintEditInp()` + blur 저장 이벤트
- `spec/mirgrations/20260629_ddl_log_add_fields.sql`: 마이그레이션 SQL 작성

**엑셀 개선**
- `services/ddl_service.py` `export_excel()`:
  - 헤더 "모니터링 결과" → "모니터링결과" (띄어쓰기 제거)
  - 색상: 정상=초록, 비정상=노랑, 미적용=빨강 (기존 정상/비정상만 초록/빨강)
  - 모니터링결과 텍스트: 정상→"특이사항 없음", 비정상+사유→사유내용, 비정상+사유없음→"사유 입력이 필요합니다", 미적용→"SR번호 없음"
  - 6개 편집 칼럼 실제 데이터 출력 (기존: 모두 빈칸)

---

### [DDL, DML 공통] 자동매핑 버튼 제거

- `templates/ddl.html`: `runEnrich()` 버튼, enrich 결과 패널, JS 함수 모두 제거
- `templates/dml_manager.html`: 동일하게 제거

---

### [DML] 비DML 버튼 토글 스타일 개선

- `templates/dml_developer.html`:
  - `is_dml=True`: 기존 "비DML로" 버튼 유지
  - `is_dml=False`: 기존 "DML 아님" 배지 + "↩ 되돌리기" 버튼 → 초록색 "DML로" 버튼 단일화
  - `_renderDmlCell()` JS 함수 동일하게 수정

---

### [DML] 담당자화면 SR입력 + DML여부 + 사유입력 추가

- `templates/dml_manager.html`:
  - SR번호 칼럼: 읽기전용 → 편집 가능 입력칸 (`mgrApplySr` / Enter 적용)
  - DML여부 칼럼 신규 추가: 비DML로/DML로 토글 버튼 (`mgrToggleDml`)
  - 작업 칼럼 신규 추가: 적용/취소 버튼
  - 비정상 상태 칼럼: 사유 편집 모달 (기존 읽기전용 → 저장 가능)
  - 비DML 그룹: SR번호~SR종료일 "DML 아님" 표시
  - `data-is-dml` 속성 추가
  - `mgrApplySr`, `mgrClearSr`, `mgrToggleDml`, `mgrOpenReasonModal`, `mgrSaveReason` JS 함수 추가

---

### [DML] 엑셀 사유 버그 수정

- `services/dml_service.py` `export_excel()`:
  - 비정상+사유없음: 빈 문자열 → "사유 입력이 필요합니다"
  - 미적용: 빈 문자열 → "SR번호 없음"
  - 기존: `_safe_str(g.dml_reason)` → None/빈값 모두 빈칸 출력

---

### [계정] 비밀번호 변경 기능 추가

- `routers/auth.py`: `GET/POST /change-password` 추가 (현재 비번 확인 + 새 비번 설정)
- `templates/change_password.html` 신규 생성
- `templates/base.html`: 내비바에 🔑 비밀번호 변경 링크 추가 (로그인 사용자 전용)

---

### [DDL] 엑셀 다운로드 빈 데이터 처리

- `templates/ddl.html`:
  - 엑셀 버튼 `<a href="...">` → `<button onclick="downloadDdlExcel()">` 로 변경
  - `downloadDdlExcel()` 함수 추가: `fetch` 후 Content-Type 확인
    - xlsx 응답 → Blob 다운로드
    - 그 외 → `showToast(data.message || '내보낼 데이터가 없습니다.', 'bad')`
  - 기존: `<a>` 링크로 직접 이동 → 404 JSON 페이지 노출

---

### [DDL] UI 버그 수정 + 개선 3차

**KPI/카운트 카운트 오류 수정**
- `templates/ddl.html`:
  - CSS `.ddl-grid tbody tr:not(.ddl-detail-row)` → `tr[data-status]` (height / hover)
  - JS `_updateKpi()`: `'tbody tr:not(.ddl-detail-row)'` → `'tbody tr[data-status]'`
  - JS `applyFilters()`: 동일 선택자 수정
  - 원인: 상세 서브행 내 nested `<table><tbody><tr>` 까지 카운트되어 total=3 오류 발생

**이관전승인 X 기본값 수정**
- `services/ddl_service.py` `apply_sr()`:
  - `auto_pre` 초기값 `"X"` → SR없거나 appr_date 없으면 항상 X
  - 기존: 조건 미충족 시 이전 값(O) 유지 → 잘못된 SR 입력 시 O 표시 버그
- 프로그램변경: `pcl_view.default_pre_deploy()` 가 `sr_approved_at=None` 시 "X" 반환 → 이미 올바름

**위험 DDL만 체크박스 제거**
- `templates/ddl.html`: `<label>` + `chk-abnormal` 체크박스 제거
- `applyFilters()`: `abnOnly` 변수 + `(!abnOnly || rowAbn)` 조건 제거

**상세 서브행 디자인 DML 통일**
- `templates/ddl.html`: 상세 sub-table `<tr>` 에 `border-bottom:1px solid #dce3ed` 추가
- CSS `.ddl-grid tbody tr[data-status]` 선택자가 서브행 높이 강제 제외

**설명 레전드 박스 스타일**
- `templates/ddl.html` CSS: `.dml-legend` + `.dml-legend span` 정의 추가 (배경·테두리 박스)
- `<div class="dml-legend" style="margin-bottom:10px;">` → 인라인 스타일 제거

---

### [DML, DDL 공통] 상세 행 쿼리 클릭 시 전체 쿼리 모달

- `templates/base.html`:
  - `openQueryModal(q)` / `closeQueryModal()` 전역 JS 함수 추가
  - `#query-full-modal` 공통 모달 HTML 추가 (배경 클릭 · ESC로 닫기)
- `templates/dml_developer.html`: 상세 행 쿼리 셀 `onclick="openQueryModal(this.title)"` + 파란색(`#2e5a8e`) 적용
- `templates/dml_manager.html`: `toggleMgrLogs` 내 쿼리 셀 동일 적용
- `templates/ddl.html`: 상세 행 쿼리 셀 동일 적용

---

### [DML] 담당자화면 UI 개선 2차

- `templates/dml_manager.html`:
  - 비DML 그룹 SR번호 칸: `<span>DML 아님</span>` → `<input disabled value="DML이 아님">` (초록 배경, 개발자화면 동일)
  - 비DML 그룹 SR제목~SR종료일: "DML 아님"(초록) → "DML이 아님"(검정 `#333`)
  - JS `mgrToggleDml`: SR칸 토글 시 동일하게 disabled input 사용
  - 상세 행 추가: 열 헤더에 "상세" 컬럼, 각 행에 ▶ 버튼, `mdetail-{id}` 서브행
  - `toggleMgrLogs(groupId)`: `/dml/developer/group/{id}/logs` 호출, 요청시각·쿼리·SR번호 표시
  - `applyFilters`: `.m-detail-row` 제외, 부모 숨김 시 상세 서브행 자동 닫기
  - 행 높이: `.td` padding `9px` → `6px` + `line-height:1.3` (개발자화면과 동일)

---

### [DDL] UI 개선 2차

- `templates/ddl.html`:
  - KPI 카드 순서 변경: SR적용완료 → **사유미입력**(주황 border `#e67e22`) → 미적용 → 진행률
  - 상세 행 구조 변경: 쿼리만 표시 → 요청시각 · 쿼리(클릭 가능) · SR번호 3열 테이블로 변경
  - `applyDdlSr` JS: SR 적용 후 `pre_release_approval` 편집 인풋 값 즉시 갱신 (`_paintEditInp` 호출)
- `services/ddl_service.py` `apply_sr()`:
  - `if not log.pre_release_approval:` 조건 제거 → 이관전승인 항상 최신화(SR 재적용 시에도 덮어쓰기)

---

## 2026-06-28 (DML)

### [DML] 개발자화면 KPI 즉시 갱신 + 엑셀 검증결과 색상 웹 일치

**KPI 즉시 갱신 (Task 4)**
- `templates/dml_developer.html`
  - KPI 카드 숫자 div에 id 부여: `kpi-applied` / `kpi-no-reason` / `kpi-pending` / `kpi-pct` / `kpi-bar`
  - `_updateKpiFromDom()` 추가: `data-status`·`data-reason` 속성 기반으로 적용완료/사유미입력/미적용/진행률 재집계
  - `_applyGroupState()` 끝에 `_updateKpiFromDom()` 호출 → SR입력/적용/취소, 비DML토글, 사유저장 등 모든 액션 후 자동 갱신

**엑셀 색상 웹 일치 (Task 5)**
- `services/dml_service.py` `export_excel()`
  - 기존: 정상=초록, 비정상=빨강, 미적용=무색 → 웹(비정상=노랑/미적용=빨강)과 불일치
  - 변경: 정상=초록(`C6EFCE`) / 비정상=노랑(`FFEB9C`+`9C6500`) / 미적용=빨강(`FFC7CE`) — 웹 배지 색과 동일
  - 웹·엑셀 모두 `_compute_ui_status()` 동일 함수 사용 → 값(정상/비정상/미적용) 항상 일치 확인

---

### [DML] KPI 집계 기준 개편 + 사유미입력 카드 추가

**문제**
- KPI "적용 완료"가 `g.status == 적용됨` 기준이라 SR이 있어도 비정상이면 완료로 잡히고, 개발자별 "완료"도 동일 오류.
- 비정상이지만 소명 사유가 없는 그룹을 구분할 KPI 없음.

**변경**
- `services/dml_service.py`
  - `get_developer_view()` / `get_manager_view()`: `g.status` 기반 집계 → `_compute_ui_status()` 기반으로 전환
  - **미적용**: `g.is_dml and ui_status == '미적용'`
  - **사유미입력**: `g.is_dml and ui_status == '비정상' and not g.dml_reason`
  - **적용완료**: `total - 미적용 - 사유미입력`
  - **진행률**: `적용완료 / total`
  - 개발자별 "완료"도 동일 기준 적용 (`not is_dml` or `정상` or `비정상+사유있음`)
  - 빈 period 반환값에 `no_reason(_groups)` 필드 추가
- `templates/dml_developer.html` — KPI 4카드 → 5카드: 적용완료/**사유미입력(주황)**/미적용/진행률
- `templates/dml_manager.html` — 동일하게 KPI 5카드로 확장

---

### [DML] 개발자화면 범위 일괄 SR 적용 (3가지 위험대책)

**기능**: 순번 범위(시작~종료)와 SR번호를 입력하면 해당 그룹에 한 번에 적용.

**위험대책**
1. **적용 전 프리뷰 모달** — 영향받을 그룹 목록(순번·대상 테이블·현재 SR·처리여부)을 확인 후 적용
2. **기존 SR 보호** (기본값 ON) — 이미 SR이 입력된 그룹은 건너뜀. 해제 시 덮어쓰기
3. **범위 하이라이트** — 순번 범위 입력 시 해당 행을 파란 테두리로 실시간 시각 강조

**비DML 자동 건너뜀**: `is_dml=false` 그룹은 범위 안에 있어도 항상 제외.

**변경 파일**
- `schemas/dml.py` — `BulkApplySrRequest{group_ids, sr_no, skip_existing}` 추가
- `services/dml_service.py` — `bulk_apply_sr()` 추가
- `routers/dml_developer.py` — `POST /dml/developer/bulk-apply-sr` 엔드포인트 추가, `BulkApplySrRequest` import
- `templates/dml_developer.html`
  - 필터바 아래 "일괄 SR 적용" 패널 추가 (순번 범위·SR번호·기존 SR 보호 체크박스·미리보기 버튼)
  - 일괄 프리뷰 모달 추가 (순번/대상 테이블/현재 SR/처리 4열, 최대 340px 스크롤)
  - `highlightRange()` / `clearBulkHighlight()` / `showBulkPreview()` / `closeBulkPreview()` / `confirmBulkApply()` JS 추가

---

## 2026-06-27 (프로그램변경 화면 4건)

### [PC 1] 모니터링결과 한 줄 표시 + 말줄임/툴팁

- `templates/program_change.html` — `.grid td.monitor` 를 `white-space:normal`(여러 줄) →
  `nowrap + overflow:hidden + text-overflow:ellipsis` 로 변경(행 높이 고정).
  렌더 시 `title` 속성 부여, `saveSr()`/`saveReason()` 갱신 시에도 `title` 동기화.

### [PC 2] 입력 시 변경 토스트 + 편집칸 색상 피드백

- `templates/program_change.html`
  - `saveField()`(결재/개발자/이관자/검토수행자)·`saveSr()`·`saveReason()` 저장 성공 시
    `showToast(...)` 로 "변경되었습니다" 안내(부서이동자 화면과 동일 패턴).
  - 편집칸(`.edit-inp`) 색칠 규칙 `_paintEdit()` 추가: 값이 있으면(입력/디폴트)
    행 상태색(정상 녹/비정상 노랑/미적용 빨강), 비어 있으면 흰색 유지.
    렌더·입력·blur·SR 상태변경 시 재적용.

### [PC 3] 파일명 전체 표시(한 줄, 잘리지 않음)

- `templates/program_change.html` — 파일명 칼럼(`td:nth-child(4)`) 의 `max-width/ellipsis` 제거,
  `nowrap` 한 줄로 전체 경로+파일명 표시(SR제목 칼럼은 기존 말줄임 유지).

### [PC 4] 모니터링결과 사유 텍스트 정정 (웹·엑셀 동일)

- 원인: 적재 배치(`collect_orchestrator`)가 판정기(`pcl_judger`) 자동 진단문
  ("NFS 매핑 실패 - SR번호 없음", "사전배포(승인일 이전 이관)" 등)을 `reason` 컬럼에 저장 →
  사용자가 SR 입력 후 비정상이 되면 이 자동문이 모니터링결과로 노출됨.
- `services/pcl_view.py` — `is_user_reason()` 추가(자동 진단문 집합/접두사 제외).
  `monitoring_result()` 가 비정상일 때 **사용자 작성 사유만** 표기, 없으면 "사유 작성이 필요함".
  (정상=특이사항 없음, 미적용=SR번호 없음) → 엑셀(`excel_exporter`)도 동일 함수 사용으로 자동 반영.
- `schemas/program_change.py` — `user_reason` computed_field 추가.
  `templates/program_change.html` — 사유 플래그/모달 프리필이 `user_reason` 기준으로 동작
  (자동 진단문은 사유 미입력 `✎` 로 표시).

---

### [DML 1] 엑셀 검증결과 = 웹 화면 상태와 일치 (DML·DDL)

- 기존: 엑셀은 행단위 `enrich_and_validate`(요청시각 기준) 결과를 사용해
  작업승인일이 없으면 `판정불가`로 출력 → 웹에서 `비정상`인 행이 엑셀에서 누락.
- 변경: 엑셀 검증결과를 웹과 동일한 `_compute_ui_status`(그룹 기준시각/SR DB)로 산출.
  웹의 `정상/비정상/미적용`이 엑셀 검증결과에 1:1로 동일하게 표기됨.
- `services/dml_service.py` — `export_excel()`: `enrich_and_validate` 제거,
  `DmlGroup` 맵 + `_fetch_sr_info_map` + `_compute_ui_status`로 행별 검증결과 산출.
- `services/ddl_service.py` — `export_excel()`: 동일하게 `_compute_ui_status(log, sr_info)` 기반으로 변경.

### [DML 2] 개발자화면 비DML 토글 — 새로고침 제거

- `templates/dml_developer.html` — `toggleDml()`에서 `location.reload()` 제거.
  SR 적용과 동일하게 서버 응답(`r.group`)으로 `_applyGroupState()` 호출하여 인플레이스 갱신.

### [DML 3] SR번호 칼럼 디자인 일관성 + 'DML이 아님' 표기 확장

- `templates/dml_developer.html`
  - SR번호 칼럼: 비DML일 때 상태 뱃지 대신 **SR 입력창을 유지**(값=`DML이 아님`, 비활성화, 정상색).
    실제 `sr_no`는 `data-sr-no`에 보존 → DML로 되돌리면 복원.
  - SR번호·SR제목·작업구분·작업승인일·SR종료일 5개 칼럼 모두 비DML이면 `DML이 아님` 텍스트 표기.
  - JS `_applyGroupState()`/`_renderDmlCell()`/`_renderStatusCell()`/`_renderBtnsCell()` 추가,
    `_updateSrInfo()`가 `is_dml=false`면 5칸 모두 `DML이 아님`으로 갱신.
- `services/dml_service.py` — `export_excel()`: 비DML 행은 SR번호~SR종료일 5칸 모두 `DML이 아님` 출력
  (기존엔 SR번호 칸만 표기).

### [DML 4] 개발자화면 비정상 사유 입력여부 구분 (담당자화면과 동일)

- `templates/dml_developer.html`
  - 상태 셀: 비정상 행에 사유 플래그 표기 — 입력됨 `📝` / 미입력 `✎`(`.reason-flag` 스타일).
  - 기존 `::after`로 모든 비정상 행에 `📝` 붙던 CSS 제거.
  - `saveReason()`은 응답으로 `_applyGroupState()` 호출 → 저장 즉시 플래그 갱신.

---

## 2026-06-23 (로그·공통)

### [로그] logs/ 날짜별 적재 — 애플리케이션·접속(IP)·에러 로그

**배경**: 애플리케이션 로그·접속 로그(사용자 IP 포함)·에러 로그를 `logs/` 폴더에 날짜별로 적재(추후 다른 디스크로 이전 예정).

**신규/변경 파일**
- `core/logging_config.py` (신규) — `setup_logging()`
  - `TimedRotatingFileHandler`(자정 일 단위 롤오버, `backupCount=0` 보존)로 3종 로그
    - `logs/app/application.log` (INFO+), `logs/access/access.log`, `logs/error/error.log` (ERROR+)
  - 당일은 베이스 파일, 자정 롤오버 시 `application-YYYY-MM-DD.log` 형태(`namer`)
  - access 로거는 `propagate=False`로 app 로그와 중복 방지
- `main.py`
  - 모듈 로드시 `setup_logging()` 호출
  - `access_log_middleware` 추가: 요청별 `IP "METHOD PATH" status 소요ms user=` 기록 (SessionMiddleware 이후 등록 → call_next 후 세션에서 사용자명 조회). 처리 중 예외는 error 로그에 트레이스백 기록 후 재발생
  - `_client_ip()`: `X-Forwarded-For`/`X-Real-IP` 우선, 없으면 `request.client.host`

### [공통] 월간 모니터링 기본 회차 = 전월 (당월 → 전월)

**배경**: 월간 모니터링은 전월 대상이므로, 페이지 진입 시 기본 조회 회차를 전월로 표시해야 함. 대상: 대시보드·부서이동자(월간)·데이터변경(담당자/개발자)·프로시저(DDL). (프로그램변경은 대상 외)

**신규/변경 파일**
- `core/periods.py` (신규) — `prev_month_ym(today=None)`: 전월 "YYYY-MM" 반환(연초 경계 처리)
- `routers/dashboard.py`·`routers/ddl.py`·`routers/dml_manager.py`·`routers/dml_developer.py`·`routers/dept_transfer.py`
  - 각 `_current_ym()`(당월) → `_default_ym()`(전월, `prev_month_ym()` 위임)으로 교체, 호출부 일괄 변경
  - GET 화면 기본값 + 파라미터 미지정 시 배치/엑셀/실행 기본 회차도 전월로 통일 (UI는 항상 선택 회차를 명시 전송)
- 참고: `services/dml_service.py`·`services/ddl_service.py`의 `_current_ym()`는 미사용(dead) 함수라 미변경

---

## 2026-06-23 (부서이동자)

### [부서이동자 1] 월간 조회 실행 성능 개선 (행별 UPSERT → 배치 UPSERT)

**배경**: 월간 조회 실행이 너무 오래 걸림. `collect_monthly`가 수집 행마다 개별 `INSERT…ON CONFLICT`를 실행(행당 1 round-trip)하여 수천 건 적재 시 매우 느렸음.

**변경 파일**
- `services/dept_transfer_collector.py`
  - `_upsert_monthly()`(행별) 제거 → `_monthly_values()` + `_bulk_upsert_monthly()` 도입
  - 한 태스크(공통/HR/PMS/EPRO)의 전체 행을 단일 `pg_insert(...).values(list)` statement로 일괄 처리
  - ON CONFLICT는 한 명령에서 같은 충돌키를 두 번 못 건드리므로 `(period_id, system_code, empno, role_key)` 기준 사전 dedup(마지막 행 우선) — 기존 행별 UPSERT와 동일 효과
  - 사용자 입력값(sr_no/sr_title/remark) 보존·키 컬럼 제외 동작 그대로 유지
- `templates/dept_transfer.html` — 조회 결과/토스트의 `r.inserted`(undefined) → `r.upserted`로 수정 (백엔드 반환 키 일치)

### [부서이동자 2] 월간 배치 스크립트 추가

**변경 파일**
- `scripts/load_monthly_dept_transfer.py` (신규) — 일간 스크립트와 동형. `run_monthly_collect()` 호출.
  - 회차 인자 지원: `python -m scripts.load_monthly_dept_transfer [YYYY-MM]` (미지정 시 이번 달)
  - 종료코드 0/1/2 (전체성공/치명오류/부분성공), 크론 예시 주석 포함

### [부서이동자 3] 월간 행 색상 기준 변경 (권한회수일 → SR 매핑)

**배경**: 권한회수일 없을 때 행을 주황색으로 칠하던 로직 불필요. SR 매핑 기준으로 변경.

**변경 파일**
- `templates/dept_transfer.html`
  - 행 배경 조건: `not r.revoke_date` → `not (r.sr_no and r.sr_title)` (SR 미입력 OR 미매핑 → 주황 `#fffbea`, 매핑됨 → 흰색/기본)
  - `saveMonthSr()`: 저장 응답의 `sr_found` 기준으로 행 배경 즉시 토글(매핑됨=흰색, 미매핑=주황)

### [부서이동자 4] 매핑 시 KPI 즉시 갱신 (새로고침 불필요)

**배경**: SR 매핑/해제 후 새로고침해야만 KPI(미적용 건수·SR 적용률)가 갱신됨.

**변경 파일**
- `services/dept_transfer_service.py` — `update_monthly_sr()`가 commit 후 재계산된 `get_monthly_summary()` KPI를 결과에 포함
- `routers/dept_transfer.py` — `/dept-transfer/monthly/sr` 응답에 `kpi` 포함
- `templates/dept_transfer.html`
  - KPI 카드(HR/PMS/EPRO/적용률)에 id 부여
  - `updateKpi(kpi)` 함수 추가 — 미적용 건수·진행률·`warn`/`ok` 클래스 실시간 갱신
  - `saveMonthSr()`에서 응답 `r.kpi`로 `updateKpi()` 호출

---

## 2026-06-23 (DML)

### [DML 1] 개발자화면 DML여부 컬럼 추가 (비DML = 정상·적용완료)

**배경**: SR이 필요없는 비DML(예: DBSAFER 자체이력)도 SR 미입력이라 미적용으로 잡힘. 개발자가 행을 비DML로 표시하면 정상·적용완료로 처리되도록 함. 각 행 기본값은 DML.

**DB 변경** — `spec/db_change_sql.md`
```sql
ALTER TABLE dml.dml_group ADD COLUMN is_dml BOOLEAN NOT NULL DEFAULT TRUE;
```

**변경 파일**
- `models/dml.py` — `DmlGroup.is_dml` Boolean 컬럼(server_default true) 추가, `Boolean`/`text` import
- `services/dml_service.py`
  - `_compute_ui_status()`: `not g.is_dml` → "정상" (SR 무관)
  - `_group_to_dict()`: `is_dml` 필드 노출
  - 담당자·개발자 뷰 applied 집계: `status == 적용됨 or not g.is_dml` (비DML도 적용완료), 개발자별 done 동일
  - `set_dml(group_id, is_dml, db)` 함수 추가 (SR값은 보존, DML로 되돌리면 SR 기준 재판정)
  - `export_excel()`: 그룹별 is_dml 맵 구성 → 비DML 로그는 SR번호 자리에 "DML이 아님", 검증결과 "정상"으로 출력
- `schemas/dml.py` — `SetDmlRequest{group_id, is_dml}` 추가
- `routers/dml_developer.py` — `POST /dml/developer/set-dml` 추가
- `templates/dml_developer.html`
  - 헤더에 "DML여부" 컬럼 추가, 상세 서브행 colspan 14 → 15
  - 비DML 행: SR번호 셀에 "DML이 아님" 표시(입력칸 숨김), 작업(적용/취소) 버튼 숨김
  - DML여부 셀: DML→[비DML로] 버튼 / 비DML→[DML 아님] 배지 + [↩] 되돌리기
  - `toggleDml(groupId, isDml)` JS 추가 (set-dml 호출 후 리로드)
- 담당자화면(`dml_manager.html`)은 변경 없음 — 비DML 그룹이 정상으로 집계되는지만 보장(서버 `_compute_ui_status`·applied 집계로 처리)

### [DML 2] 비정상 소명 "사유" + 엑셀 모니터링결과 컬럼 (구현 완료)

**배경**: 비정상(SR 있으나 판정 이상) 행에 대해 개발자가 소명 사유를 입력하고, 담당자가 확인할 수 있어야 함. 사유는 **비정상일 때만** 사용(비DML·정상 불필요). 컬럼 추가 대신 비정상 행 클릭 시 모달로 입력/확인.

**DB 변경** — `spec/db_change_sql.md`
```sql
ALTER TABLE dml.dml_group ADD COLUMN dml_reason VARCHAR(500);
```

**변경 파일**
- `models/dml.py` — `DmlGroup.dml_reason VARCHAR(500)` 추가
- `services/dml_service.py`
  - `_group_to_dict()`: `reason` 필드 노출
  - `set_reason(group_id, reason, db)` 함수 추가 (최대 500자 저장)
  - `export_excel()`: "모니터링결과" 컬럼 추가 — 비DML="DML이 아님" / 정상="특이사항 없음" / 비정상=개발자 사유 / 그 외=공란. 그룹별 (is_dml, reason) 맵 구성
- `schemas/dml.py` — `SetReasonRequest{group_id, reason}` 추가
- `routers/dml_developer.py` — `POST /dml/developer/set-reason` 추가
- `templates/dml_developer.html`
  - 행에 `data-reason` 추가, 비정상 행 cursor:pointer + 상태 셀 📝 힌트(CSS, data-status 연동)
  - 비정상 사유 **입력** 모달(textarea, maxlength 500, "n / 500자" 카운터) + 배경 클릭 닫기
  - 비정상 행 클릭(입력 컨트롤 제외) → 모달, 저장 시 `set-reason` 호출 후 행 `data-reason` 즉시 갱신
- `templates/dml_manager.html`
  - 행에 `data-reason` 추가, 비정상 상태 셀에 사유 입력 여부 표시(📝 입력됨 / ✎ 미입력)
  - 비정상 사유 **확인**(읽기 전용) 모달 + 비정상 행 클릭 → 모달 (담당자는 입력 불가)

---

## 2026-06-17 (대시보드)

### [대시보드] 4개 모듈 KPI 통합 대시보드 구현 (더미 → 실데이터)

**배경**: 기존 `dashboard.html`/`routers/dashboard.py`는 하드코딩 더미 데이터. 프로그램변경·부서이동자·DML·DDL의 기존 KPI를 한 화면에 그래프로 표현. 보안접근로그는 제외. 조회 전용(엑셀 출력 없음).

**신규/변경 파일**
- `services/dashboard_service.py` (신규)
  - `get_dashboard_data(db, ym)`: 모듈별 집계 통합. `dml_service.get_manager_view`·`ddl_service.get_view`·`dept_transfer_service.get_monthly_summary`·`excel_exporter._ui_status` 재사용
  - 모듈별 `try/except OperationalError` 독립 처리 (부분 DB 장애 시 해당 모듈만 0)
  - 통합 상태 도넛(PC+DML+DDL 3색)용 `_conic_gradient()` 문자열 생성
- `routers/dashboard.py`
  - 더미 제거 → `?period=` 쿼리 + `get_db` 주입 후 `dashboard_service` 호출
- `templates/dashboard.html` (재작성)
  - Hero KPI 카드 4개(SVG 진행률 링) + conic-gradient 도넛 + 진행률 바 + 시스템별 누적 막대(CSS) + 시스템 표 + 최근 이상 이벤트 Top 10
  - 외부 CDN 미사용(내부망), 보안로그·전체 엑셀 버튼 제거
- `spec/dashboard/file_structure.md`, `spec/dashboard/dashboard_spec.md` 작성

---

## 2026-06-17 (DML·DDL·공통)

### [DML 이슈 1] 개발자화면 — 없는 SR 입력 시 '비정상' 오표시 수정

**원인**: 백엔드 `_compute_ui_status()`는 SR DB에 없는 번호에 대해 `"미적용"`을 정상 반환하지만, 프론트 `_setApplied()`가 `정상`이 아니면 무조건 `비정상` 배지를 렌더링해 미적용이 비정상으로 표시됨. (전체 새로고침 시엔 템플릿이 `g.ui_status`로 올바르게 렌더링됨 → JS 실시간 갱신만 버그)

**변경 파일**
- `templates/dml_developer.html`
  - `_setApplied(groupId, sr, uiStatus, srFound)`: `uiStatus`가 `미적용`이면 빨간 `미적용` 배지 + 행 배경 `#fff5f5` + 취소버튼 숨김 처리하도록 3분기로 변경 (기존 정상/비정상 2분기)

### [DML 이슈 2] 개발자화면 — SR 입력칸 상태별 3색

**변경 파일**
- `templates/dml_developer.html`
  - `_srInputColor(uiStatus)` 헬퍼 추가: 정상=초록(`#f0fdf4`/`#86efac`) / 비정상=노랑(`#fffbea`/`#fcd34d`) / 미적용=빨강(`#fef2f2`/`#fca5a5`)
  - `_setApplied`·`_setPending`: SR 입력칸 배경/테두리를 `_srInputColor`로 통일
  - 초기 렌더(Jinja): 입력칸 색상 조건을 `g.sr_no` 유무 2색 → `g.ui_status` 기반 3색으로 변경

### [DDL 이슈 1] 없는 SR 입력 시 '비정상' 오표시 수정 (DML과 동일 버그)

**변경 파일**
- `templates/ddl.html`
  - `_setApplied(logId, sr, uiStatus)`: `미적용` 분기 추가 (빨간 배지 + 배경 `#fff5f5` + 취소버튼 숨김). 위험 DDL 행은 기존대로 빨간 배경 유지.

### [DDL 이슈 2] SR 입력칸 상태별 3색

**변경 파일**
- `templates/ddl.html`
  - `_srInputColor(uiStatus)` 헬퍼 추가 (DML과 동일 팔레트)
  - `_setApplied`·`_setPending`: 입력칸 색상 적용
  - 초기 렌더(Jinja): 무색이던 `ddl-sr-input`에 `l.ui_status` 기반 3색 적용

### [공통] 엑셀 출력 — 행 전체 색칠 → 정상여부 판단 칼럼만 색칠 + 글씨색 변경

**배경**: 검증/모니터링 결과에 따라 엑셀 행 전체가 색칠되어 가독성 저하. 정상여부 판단 칼럼만 색칠하고 해당 칼럼 글씨색도 대비되게 변경.

**변경 파일**
- `services/dml_service.py` `export_excel()`
  - `검증결과` 칼럼 셀만 색칠 (`HEADERS.index("검증결과")`), 정상=초록채움+짙은초록글씨(`006100`)/비정상=빨강채움+짙은빨강글씨(`9C0006`). 판정불가는 무색.
- `services/ddl_service.py` `export_excel()`
  - 동일하게 `검증결과` 칼럼 셀만 색칠 + 글씨색 적용
- `services/excel_exporter.py`(프로그램변경) `export()`
  - `모니터링결과` 칼럼 셀만 색칠: 정상=초록(`006100`)/비정상=노랑채움+갈색글씨(`9C6500`)/미적용=빨강(`9C0006`)
- 참고: 부서이동자 월간 엑셀(`dept_transfer_service.export_monthly_excel`)은 행 색칠 없음 → 변경 불필요

---

## 2026-06-17 (부서이동자)

### [부서이동자 이슈 1·2] 월간 SR 수정 시 매핑상태 원복 + 미적용 KPI 미반영 수정

**원인**: `update_monthly_sr()`가 SR을 못 찾았을 때(또는 SR DB 조회 실패 시) 이전 매핑값 `sr_title`/`sr_work_type`를 그대로 남겨둠.
- 이미 매핑된 SR을 없는 SR로 수정하면 `sr_no`만 갱신되고 `sr_title`은 stale 상태로 유지됨.
- 저장 응답(`sr_found=False`)으로는 "미매핑"이 잠깐 표시되지만, 새로고침 시 템플릿이 `sr_no and sr_title` 기준으로 판정 → **"매핑됨"으로 원복**.
- KPI `get_monthly_summary()`의 미적용 집계가 `not sr_no`만 세어, 없는 SR을 입력해도(sr_title 잔존) 미적용에 잡히지 않음.

**변경 파일**
- `services/dept_transfer_service.py`
  - `update_monthly_sr()`: `rec.sr_no` 설정 직후 `sr_title`/`sr_work_type`를 `None`으로 초기화 후, SR 조회 성공 시에만 다시 채움 (못 찾으면 매핑값 제거 보장)
  - `get_monthly_summary()`: 미적용 집계 기준을 `not r.sr_no` → `not r.sr_no or not r.sr_title` 로 변경 (명세: SR 미입력 OR SR이 DB에 없음)
  - `_apply_sr_to_daily()`: 동일 stale 버그 예방 — `sr_no` 설정 직후 매핑값 초기화 후 조회 성공 시 재설정 (일간 화면 일관성)

---

## 2026-06-17 (부서이동자) — 일간 필터

### [부서이동자 이슈 3] 퇴직자·부서변경자 탭 상태 필터 제거

**배경**: 상태 필터(전체 상태/미처리/유지/회수)는 유지/회수 처리가 없는 퇴직자·부서변경자 탭에서는 불필요.

**변경 파일**
- `templates/dept_transfer_daily.html`
  - `filterTab()`: 탭이 `퇴직자` 또는 `부서변경자`일 때 `#daily-action-filter` select 를 `display:none` 처리하고 값을 `all`로 리셋 (다른 탭에서는 다시 노출)

---

## 2026-06-16 (부서이동자)

### [부서이동자 이슈 1] 일간 유지/회수 버튼 opacity 고착 수정

**배경**: 유지/회수 버튼의 `opacity:0.4` 스타일이 Jinja2 서버 렌더링 시점에만 적용되어, JS로 처리상태 변경 후 버튼 외관이 갱신되지 않는 문제.

**변경 파일**
- `templates/dept_transfer_daily.html`
  - 유지·회수 버튼에 `data-action-btn="유지|회수"` + `data-rid="{{ r.id }}"` 속성 추가 (section-hr·section-perm 동일 패턴, `replace_all` 적용)
  - `setAction()` JS: `applyFilters()` 이후 `querySelectorAll('[data-action-btn][data-rid]')` 순회하여 현재 action과 일치하는 버튼만 `opacity:0.4`, 나머지 `''` 로 실시간 갱신

---

### [부서이동자 이슈 2] 월간 부서이동자 리스트 부서코드 미출력 (코드 정상 — 데이터 재수집 필요)

**원인**: 코드 스택(collector·service·template) 모두 정상. 기존 `MonthlyRecord` 행이 `dept_code` 컬럼 추가 전에 적재되어 NULL 상태.

**조치**: 월간 화면 [월간 조회 실행] 버튼 클릭 → DELETE + INSERT로 최신 데이터 재수집 시 dept_code가 채워짐. 코드 변경 없음.

---

### [부서이동자 이슈 3] 월간 KPI 개편 + 엑셀 버튼 위치 이동 + 탭 건수 상단 이동

**배경**: 기존 KPI가 전체 건수 1카드뿐이었으며 엑셀 버튼이 KPI 카드 안에 있어 UI 이상. HR·PMS·전자조달 SR 적용 현황이 상단에 없어 모니터링 포인트 파악 불가.

**KPI 5카드 (탭 상단)**
- 부서이동자: 리스트 건수 (공통)
- HR: 전체 건수 + 미적용 건수 (노란색 강조)
- PMS: 전체 건수 + 미적용 건수
- 전자조달: 전체 건수 + 미적용 건수
- SR 적용률: HR+PMS+전자조달 통합 진행률 (%)

**변경 파일**
- `services/dept_transfer_service.py`
  - `get_monthly_summary(db, year_month)` 추가: period 조회 → 시스템별 전체/미적용 집계 → 통합 진행률 계산
- `routers/dept_transfer.py`
  - `monthly_view`: `svc.get_monthly_summary()` 호출 후 `kpi=kpi` 템플릿 컨텍스트 추가
  - DB 오류 시 빈 kpi dict fallback 처리
- `templates/dept_transfer.html`
  - page-head actions: 엑셀 버튼을 일간 화면 버튼 좌편으로 이동 (현재 탭 system_code 기준 자동 URL 생성)
  - KPI 2카드(전체+엑셀) 제거 → 5카드 그리드로 교체, 탭보다 위에 배치
  - 필터바 `m-count` span: 서버 렌더링으로 초기값 `총 N건` 표시
  - foot-note `총 N건` div 제거 (중복 제거)

---

### [부서이동자 이슈 4] 일간 HR·전자조달·PMS 테이블 행 높이 슬림화

**배경**: `#daily-table-hr`, `#daily-table-perm` 행이 퇴직자/부서변경자 테이블보다 두꺼워 가독성 저하.

**변경 파일**
- `templates/dept_transfer_daily.html`
  - `#daily-table-hr td, #daily-table-perm td { padding: 5px 8px; vertical-align: middle; }` 추가
  - SR 입력 input 슬림화: `height:22px; padding:1px 4px; line-height:20px;`
  - btn-sm 슬림화: `height:22px; padding:1px 6px !important; line-height:20px;`

---

## 2026-06-16 (프로그램변경)

### [프로그램변경 이슈 1] 정상여부 칼럼 제거 + 모니터링결과 3색 배지

**배경**: '정상여부' 칼럼 중복·가시성 저하. SR존재/SR없음 텍스트 제거. 모니터링결과를 3색 배지로 교체.

**3가지 상태 기준**
- **정상** (초록 `badge-ok`): SR 매핑 + 판정 정상
- **비정상** (노란 `badge-warn`): SR 매핑됨·판정 이상 (result ∈ {이상, 경고, SR없음(입력됨)})
- **미매핑** (빨간 `badge-bad`): SR 미입력 (sr_no 없음)

**변경 파일**
- `schemas/program_change.py`
  - `computed_field` import 추가
  - `ProgramChangeRow.ui_status` computed property 추가: sr_no 없으면 "미매핑", result=="정상"이면 "정상", 나머지 "비정상"
- `services/excel_exporter.py`
  - HEADERS에서 "정상여부" 제거 (16→15컬럼)
  - `_ui_status()` 헬퍼 추가: sr_no·result 기반 3상태 계산
  - 행 배경색: GREEN(정상) / YELLOW(비정상) / RED(미매핑) 전환
- `routers/program_change.py`
  - `sr_validation.judge_validation` import 추가
  - `PATCH /api/{row_id}/sr` 응답에 `ui_status` 필드 추가 (SR저장 후 즉시 상태 갱신)
- `templates/program_change.html`
  - "정상여부" 헤더·셀 제거
  - SR존재/SR없음 span 및 입력창 배경색 조건 제거
  - 모니터링결과 셀: `id="sr-result-{id}"` + `_badgeHtml(uiStatus)` 3색 배지
  - 행 배경: 미매핑=#fff5f5, 비정상=#fffbea, 정상=기본
  - `data-status` 속성 → `r.ui_status` 값
  - 범례 박스 추가 (`.pc-legend`)
  - `saveSr()`: sr-st span 대신 sr-result 셀 + tr 배경 갱신

### [프로그램변경 이슈 2] 결과 필터 클라이언트 측 처리

**배경**: 조회버튼 없이 드롭다운 변경만으로 즉시 필터링.

**변경 파일**
- `templates/program_change.html`
  - 필터 옵션: 전체/정상/SR없음/경고/이상 → 전체/정상/비정상/미매핑
  - `fResult` select에 `onchange="_applyFilter()"` 추가
  - `loadList()`: result 파라미터 서버 전송 제거 (클라이언트 필터로 전환)
  - `_applyFilter()` 함수 추가: `data-status` 기반 `tr.hidden` 토글
  - `render()` 끝에 `_applyFilter()` 호출

### [프로그램변경 이슈 3] 엑셀 출력 반영

- `services/excel_exporter.py`: 위 이슈1 변경 내용 포함 (HEADERS·색상·ui_status)

---

## 2026-06-16 (DML)

### [DML 이슈 1] 상태 3색 구분 (미적용/비정상/정상)

**배경**: 기존 SR없음/SR존재 표시가 행 높이를 키우고, SR 번호 입력 시 상태가 무조건 "적용완료"로만 표시되던 문제 수정.

**3가지 상태 기준**
- **미적용** (빨간 `badge-bad`): SR 번호 미입력 또는 없음 → KPI 미적용 건수로 집계
- **비정상** (노란 `badge-warn`): SR 있으나 승인일 전 DML 실행·긴급 기한 초과·SR DB 미조회 → KPI 적용완료로 집계
- **정상** (초록 `badge-ok`): 승인일 이후 DML 실행 (긴급: 실행 후 5일 이내 SR종료) → KPI 적용완료로 집계

**변경 파일**
- `services/dml_service.py`
  - `_compute_ui_status(g, sr_info)` 함수 추가: `dml_validation.judge_validation` 재사용하여 정상/비정상/미적용 판단
  - `_group_to_dict()`: `ui_status` 필드 추가 (API 응답·템플릿 양쪽에 노출)
- `templates/dml_developer.html`
  - SR없음/SR존재 `<span>` 및 input 배경색 조건 제거
  - `data-status` → `g.ui_status`, 행 배경색 #fffbea → #fff5f5(미적용만)
  - 상태 배지: 적용완료 단일 → 정상(초록)/비정상(노란)/미적용(빨간) 3색
  - 취소 버튼 조건: `g.status != '적용됨'` → `g.ui_status == '미적용'`
  - 상태 필터: 미입력/적용됨 → 미적용/비정상/정상
  - 범례 박스 추가 (`.dml-legend`)
  - JS `_setApplied(groupId, sr, uiStatus)`: srFound 파라미터 → uiStatus 파라미터로 교체
  - JS `_setPending()`: badge-warn → badge-bad, 배경색 수정
- `templates/dml_manager.html`
  - `data-status` → `g.ui_status`, 행 배경색 동일 적용
  - 상태 배지 3색 동일 적용
  - 상태 필터: 적용됨/미입력 → 정상/비정상/미적용
  - 범례 박스 추가
  - 엑셀 버튼: `<a href>` → `<button onclick="downloadExcel()">` 로 변경
  - JS `downloadExcel()` 추가: fetch → blob 다운로드, 데이터 없을 때 토스트 에러 표시

---

## 2026-06-16 (DDL)

### [DDL 이슈 1] 상태 3색 구분 + SR validation 모듈 분리

**배경**: DDL이 DML 전용 명칭인 `dml_validation.py`를 공유하던 문제 해소. DML과 동일한 3색 상태 표시 적용.

**validation 분리**
- `services/sr_validation.py` 신규 생성: `judge_validation`, `enrich_and_validate`, 상수 — DML·DDL 공용
- `services/dml_validation.py` → thin shim (`from services.sr_validation import *`)으로 교체 (기존 import 하위 호환 유지)
- `services/dml_service.py`: `dml_validation` → `sr_validation` import로 변경
- `services/ddl_service.py`: `dml_validation` → `sr_validation` import로 변경

**3색 상태 (DML과 동일 기준)**
- `services/ddl_service.py`
  - `_compute_ui_status(l, sr_info)` 추가: `sr_validation.judge_validation` 사용
  - `_log_to_dict()`: `ui_status` 필드 추가
- `templates/ddl.html`
  - SR없음/SR존재 span 및 input 배경색 조건 제거
  - `data-status` → `l.ui_status` (미적용/비정상/정상)
  - 행 배경: `is_abnormal` 또는 `ui_status == 미적용` → #fff5f5
  - 상태 배지: 적용완료 단일 → 정상(초록)/비정상(노란)/미적용(빨간) 3색
  - 취소 버튼: `l.status != 적용됨` → `l.ui_status == 미적용`
  - 상태 필터: 미입력/적용됨 → 미적용/비정상/정상
  - 범례 박스 추가 (`.dml-legend`)
  - `_updateKpi()`: applied 집계 기준 `status === 적용됨` → `status !== 미적용`
  - `_setApplied(logId, sr, uiStatus)`: srFound 파라미터 → uiStatus로 교체
  - `_setPending(logId)`: badge-bad + 배경 #fff5f5
  - `applyDdlSr()`: `r.log.ui_status` 기반으로 상태 갱신

**파일 구조 업데이트**
- `spec/ddl/file_structure.md`: `dml_validation.py` → `sr_validation.py`로 교체
- `spec/dml/file_structure.md`: `sr_validation.py` 추가, `dml_validation.py` shim 주석

---

### [DML 이슈 2] 판정 로직 통일 및 긴급일수 config 연동

- `services/dml_validation.py`
  - `EMERGENCY_CLOSE_DAYS = 5` 하드코딩 제거 → `settings.EMERGENCY_GRACE_DAYS` 사용 (config 변경 시 자동 반영)
  - 판정 순서 변경: 긴급변경이라도 **작업승인일이 있고 실행일이 승인일 이후**이면 바로 정상 반환
  - 작업승인일 없고 비긴급이면 `None`(판정불가) 반환 (기존 첫 줄 `pd.isna(appr_dt) → None` 과 동일 효과)
- `services/pcl_judger.py`
  - 동일 로직으로 통일: 날짜 정규화 직후 **작업승인일 있고 배포일 >= 승인일 → 정상** 조건 추가 (긴급변경보다 먼저 체크)
  - 이후 긴급변경 → 일반 SR 순서로 폴스루

---

## 2026-06-15

### [이슈 2] 일간 모니터링 탭별 건수 표시
- `templates/dept_transfer_daily.html`
  - 기존 서버 렌더링 `총 N건` foot-note → `id="daily-footnote"` 로 변경
  - `applyFilters()` 내에서 현재 탭의 visible count를 foot-note에 반영 (탭 전환마다 갱신)

---

### [이슈 3] 월간 HR 중복 제거 버그 수정
- `services/dept_transfer_collector.py` — `_monthly_hr()` 쿼리
  - `NULL AS role_code` → `CAST(a.responsibility_id AS VARCHAR2(50)) AS role_code` 로 변경
  - 기존에 role_key가 모두 `'-'`로 고정되어 UPSERT 시 사용자당 1건으로 덮어씌워지던 문제 수정
  - 이제 responsibility_id 별로 별도 행이 생성되어 사용자의 복수 역할 모두 표시됨

---

### [이슈 5] 월간 부서이동자 리스트 부서코드 컬럼 추가
- `models/dept_transfer.py` — `MonthlyRecord`에 `dept_code`, `prev_dept_code` 컬럼 추가
  ```sql
  ALTER TABLE dept_transfer.monthly_record ADD COLUMN dept_code     VARCHAR(50);
  ALTER TABLE dept_transfer.monthly_record ADD COLUMN prev_dept_code VARCHAR(50);
  ```
- `services/dept_transfer_collector.py` — `_upsert_monthly()`: `dept_code`, `prev_dept_code` 저장 + ON CONFLICT 갱신 대상에 포함
- `services/dept_transfer_service.py` — `_monthly_to_dict()`: `dept_code`, `prev_dept_code` 노출
- `templates/dept_transfer.html` — 공통 탭 thead/tbody에 부서코드, 이전부서코드 컬럼 추가
- `services/dept_transfer_service.py` — `export_monthly_excel()`: 공통 탭 엑셀 헤더를 `[부서변경일, 사번, 이름, 부서코드, 부서명, 이전부서코드, 이전부서명]`으로 변경

---

### [이슈 6] 일간 퇴직자 탭 전용 섹션
- `models/dept_transfer.py` — `DailyRecord`에 `prev_dept_code` 컬럼 추가
  ```sql
  ALTER TABLE dept_transfer.daily_record ADD COLUMN prev_dept_code VARCHAR(50);
  ```
- `services/dept_transfer_collector.py` — `_upsert_daily()`: `prev_dept_code` 저장
- `services/dept_transfer_service.py` — `_daily_to_dict()`: `dept_code`, `prev_dept_code`, `last_seen` 노출
- `templates/dept_transfer_daily.html`
  - `section-resign` 신규 섹션 추가 (퇴직자 탭 전용)
  - 컬럼: 데이터변경일(`last_seen`) | 사번 | 이름 | 부서코드 | 부서명 | 퇴직일(`change_date`)
  - SR 입력 UI 없음

---

### [이슈 8] 일간 부서변경자 탭 전용 섹션
- `templates/dept_transfer_daily.html`
  - `section-dept` 신규 섹션 추가 (부서변경자 탭 전용)
  - 컬럼: 부서변경일 | 사번 | 이름 | 부서코드 | 부서명 | 이전부서코드 | 이전부서명
  - SR 입력 UI 없음
- `filterTab()` / `applyFilters()` JS 개편: 퇴직자 → section-resign, 부서변경자 → section-dept, 전체 → section-all(기존 통합뷰)

---

### [이슈 9] 월간 권한회수일 — 입력 제거, 조회 전용
- `services/dept_transfer_collector.py` — `_upsert_monthly()`: `revoke_date` 소스DB 값 저장 및 ON CONFLICT 시 항상 최신값으로 갱신
- `templates/dept_transfer.html` — 권한회수일 `<input type="date">` → 읽기전용 텍스트 표시로 변경
- `services/dept_transfer_service.py` — `update_monthly_revoke()` 함수 삭제
- `routers/dept_transfer.py` — `POST /dept-transfer/monthly/revoke` 라우트 삭제
- `schemas/dept_transfer.py` — `MonthlyRevokeRequest` 스키마 삭제
- `templates/dept_transfer.html` — `saveRevoke()` JS 함수 삭제

---

### [이슈 10] 월간 SR 매핑 상태 색상 표시
- `services/dept_transfer_service.py` — `update_monthly_sr()`: `sr_found` 값 반환
- `routers/dept_transfer.py` — 월간 SR 저장 응답에 `sr_found` 포함
- `templates/dept_transfer.html`
  - SR입력 input: sr_no+sr_title 있으면 초록, sr_no만 있으면 빨간 배경
  - SR 열 내 `msr-status-{id}` span: **매핑됨**(초록) / **미매핑**(빨간) 인라인 표시
  - 기존 분리된 `작업` 컬럼 제거 (SR 열에 통합)
  - `saveMonthSr()` JS: sr_found 기반으로 input 스타일 + 상태 span 실시간 갱신

---

### [이슈 1, 4] 전체 탭 아코디언 + KPI 카드 구현 (보류 → 완료)

- `templates/dept_transfer_daily.html` — `section-all` 전체 재구성
  - **KPI 카드 5개**: 퇴직자·부서변경자·HR권한·전자조달·PMS 각 건수, 권한 타입은 미처리 건수도 표시 (노란색 강조)
  - **타입별 아코디언 5개**: 각 섹션 헤더 클릭으로 접기/펴기, 헤더에 건수 + 미처리 뱃지 표시
    - 퇴직자 소섹션: 데이터변경일·사번·이름·부서코드·부서명·퇴직일 (조회 전용)
    - 부서변경자 소섹션: 부서변경일·사번·이름·부서코드·부서명·이전부서코드·이전부서명 (조회 전용)
    - HR권한·전자조달·PMS 소섹션: 각 개별 탭과 동일 컬럼 + 처리상태 표시 (조회 전용, SR/유지회수 버튼 없음)
  - **이슈 4 자동 해결**: 전체 탭의 PMS 소섹션이 PMS권한 탭과 동일한 데이터·필터를 사용하므로 불일치 해소
  - `applyFilters()` JS: 전체 탭에서 5개 아코디언 테이블 전체에 키워드 검색 적용, HR·전자조달·PMS는 처리상태 필터도 적용
  - `toggleAcc(id)` JS 함수 추가
  - 아코디언 CSS 스타일 추가 (`.acc-kpi`, `.acc-sec`, `.acc-hdr`, `.acc-body`, `.acc-chev` 등)

---

## 2026-06-15 (DML)

### [DML 이슈 1] 개발자화면 접속계정 컬럼 추가 + 대상테이블 말줄임

- `templates/dml_developer.html`
  - 실제 데이터 테이블 thead/tbody에 **접속계정** 컬럼 추가 (시스템 바로 옆, `g.conn_account` 출력)
  - 예제 테이블에도 동일하게 접속계정 컬럼 추가 (예: APPS, EXHR)
  - **대상 테이블** 셀에 `max-width:140px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;` + `title` 속성으로 전체 값 tooltip 표시
  - 컬럼 수 13 → 14로 증가, 상세 서브행 `colspan="14"` 갱신

---

### [DML 이슈 2] 개발자화면 SR 존재 여부 색상 + 상태 표시

- `routers/dml_developer.py` — `apply-sr` 응답에 `sr_found` 필드 추가 (`bool(group["sr_title"])` 기반)
- `templates/dml_developer.html`
  - SR 번호 입력 셀 내 `<span id="sr-status-{id}">` 추가
  - 초기 렌더: SR이 적용됨 + sr_title 존재 → 입력창 **초록** + `SR존재` 텍스트; sr_title 없음 → **빨강** + `SR없음`
  - `applySr()` JS: 서버 응답 `r.sr_found` 기반으로 색상·상태 텍스트 실시간 갱신 + 토스트 메시지 분기
  - `_setApplied(groupId, sr, srFound)`: srFound 파라미터 추가, 색상 + 상태 span 동시 갱신
  - `_setPending()`: 상태 span 초기화

---

### [DML 이슈 3] 담당자화면 자동매핑 "nan" 메시지 개선

- `services/dml_service.py`
  - `_safe_str()` 헬퍼 추가: pandas `float('nan')` 은 truthy라 `nan or ""` 패턴이 통하지 않음 → `pd.isna()` 로 명시 처리
  - `run_enrich()`: `valid_mask`에 `enriched["sr_title"].notna()` 조건 추가 — SR DB에 없는 번호는 `group_sr`에서 제외하여 "nan" 문자열 전파 차단
  - `_fetch_sr_info_map()`, `run_enrich()`, `export_excel()` 내 `str(v or "")` 패턴을 모두 `_safe_str(v)` 로 교체

---

## 2026-06-15 (프로그램변경)

### [이슈 1] 이관시각 컬럼 통합

- `schemas/program_change.py` — `ProgramChangeRow`에 `deploy_time: Optional[datetime]` 추가 (`log_month`, `log_day`, `log_time` 3필드 대체)
- `templates/program_change.html` — thead `월/일/시간` 3열 → `이관시각` 1열, render()에서 `r.deploy_time.replace("T"," ").slice(0,19)` 포맷
- `services/excel_exporter.py` — HEADERS `월/일/시간` → `이관시각`, 값은 `deploy_time.strftime("%Y-%m-%d %H:%M:%S")`

---

### [이슈 2] 파일경로 컬럼 추가

- `schemas/program_change.py` — `ProgramChangeRow`에 `full_path: Optional[str]` 추가
- `templates/program_change.html` — 파일명 우측에 `파일경로` 열 추가, `title` 속성으로 전체 경로 tooltip 표시
- `services/excel_exporter.py` — HEADERS에 `파일경로` 추가, `r.full_path` 출력

---

### [이슈 3] SR번호 입력 + 색상 표시 + 자동매핑

- `schemas/program_change.py` — `SrUpdate` 스키마 추가
- `routers/program_change.py`
  - `PATCH /api/{row_id}/sr` 엔드포인트 추가
  - SR DB(`SrDbClient`) 조회 후 `sr_found` 반환 + `sr_title`, `sr_work_type`, `sr_approved_at`, `sr_closed_at` DB 갱신
- `templates/program_change.html`
  - SR번호 셀: `<input class="sr-inp">` + `<span id="sr-st-{id}">` 추가
  - 초기 렌더: SR존재(초록) / SR없음(빨강) / 미입력(기본) 구분
  - `saveSr()` JS: 값이 변경된 경우에만 API 호출, 응답 기반 색상 갱신 + SR제목/작업구분/작업승인일/SR종료일 자동매핑

---

### [이슈 4] 접속계정 컬럼 추가 (이관자 재정의)

- `templates/program_change.html` — `이관자` 열 삭제, 이관시각 우측에 `접속계정` 열 신규 추가 (`r.deployer` 값 그대로 사용)
- `services/excel_exporter.py` — HEADERS `이관자` → `접속계정`, 위치를 이관시각 바로 옆으로 이동

---

### [이슈 5] 비고 컬럼 제거

- `schemas/program_change.py` — `ProgramChangeRow`에서 `remark` 필드 제거, `RemarkUpdate` 스키마 삭제
- `routers/program_change.py` — `PATCH /api/{row_id}/remark` 엔드포인트 삭제
- `templates/program_change.html` — `비고` 열 및 `<input class="remark">` 제거, `saveRemark()` JS 함수 삭제
- `services/excel_exporter.py` — HEADERS에서 `비고` 제거

---

### [이슈 6] 최종 컬럼 순서 통일 (화면 = 엑셀)

최종 컬럼: `이관시각 | 접속계정 | 파일명 | 파일경로 | SR번호 | SR제목 | 작업구분 | 작업승인일 | SR종료일 | 결재3칸 | 개발자 | 검토수행자 | 모니터링결과 | 정상여부`

---

## 2026-06-15 (DDL)

### [DDL 이슈 1] SR번호 존재 여부 색상 표시

- `services/ddl_service.py` — `apply_sr()` 반환값을 `tuple[dict, bool]`로 변경
  - `sr_info_map = _fetch_sr_info_map([sr_no])` 후 `sr_found = sr_no in sr_info_map` 으로 SR DB 실존 여부 직접 판단
- `routers/ddl.py` — `apply-sr` 엔드포인트에서 튜플 언패킹 후 `sr_found` 응답에 포함
  - `{"ok": True, "log": log, "sr_found": sr_found}`
- `templates/ddl.html`
  - **초기 렌더(Jinja)**: SR입력 셀에 `<span id="sr-status-{log_id}">` 추가
    - `status == 적용됨` + `sr_title` 있음 → 입력창 **초록** + `SR존재`
    - `status == 적용됨` + `sr_title` 없음 → 입력창 **빨강** + `SR없음`
  - **`applyDdlSr()`**: `r.sr_found` 기반으로 `_setApplied` 호출 + 토스트 메시지 분기
  - **`_setApplied(logId, sr, srFound)`**: `srFound` 파라미터 추가, 색상·상태 span 동시 갱신
  - **`_setPending(logId)`**: 상태 span 초기화
