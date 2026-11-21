# DML 모니터링 모듈 변경 이력

## 2026-06-06 — 웹 이식 1차 완료

### 수정: `services/dml_parser.py`

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| SR 정규식 | `SR\w+` / `SR\d{6,}` | `[A-Za-z]\d{2}-\d{8}-\d{3}` (원본 sr_ext.py 동일) |
| 명령어 전처리 | 없음 | `clean_cmd()` 추가 — `♪`, `\r\n\t`, `\x00` 제거 |
| Two-Pointer 방향 | 단방향(nearest-donor 탐색) | Forward + Backward pass (원본 동일, 체인 전파 포함) |
| 그룹 시간윈도우 | `build_groups()`에서 미적용 | `_assign_time_groups()`로 200초 갭 기준 분리 후 집계 |
| 통계 반환 | `_propagated` 임시 컬럼 | `propagate_within_groups()` 튜플 반환 `(df, count)` |

### 신규: `models/dml.py`

- `DmlStatus` — `미입력` / `적용됨` Enum
- `DbUserDeveloperMap` — db_user → app_user 매핑
- `DmlGroup` — 그루핑 결과 (200초 + 동일 키 단위)
- `DmlLog` — DBSAFER CSV 원본 적재
- `models/__init__.py` 임포트 추가

### 신규: `schemas/dml.py`

- `ApplySrRequest` — `{ group_id: int, sr_no: str }`
- `ClearSrRequest`  — `{ group_id: int }`

### 신규: `services/dml_service.py`

| 함수 | 설명 |
|------|------|
| `import_csv()` | CSV 파싱 → DB 적재, 재업로드 시 기존 데이터 삭제 후 재적재 |
| `get_manager_view()` | 담당자 뷰 — 그룹 목록 + 개발자별 진행률 집계 |
| `get_developer_view()` | 개발자 뷰 — 본인 그룹만 조회 |
| `apply_sr()` | 그룹 + 소속 dml_log 행 전체에 SR번호 적용 |
| `clear_sr()` | 그룹 + 소속 dml_log 행 전체에서 SR번호 제거 |
| `run_enrich()` | SR DB 조회 + 검증 통계 반환 (DB 저장 안 함) |

### 수정: `routers/dml_manager.py`

- 더미 데이터 제거, `dml_service` 실제 호출로 교체
- `POST /upload` — `UploadFile` 수신 → `import_csv()` 호출
- `POST /enrich` — `run_enrich()` 호출
- `GET /` — `get_manager_view()` 호출, `year_month` / `system_code` 쿼리 파라미터 추가

### 수정: `routers/dml_developer.py`

- 더미 데이터 제거, `dml_service` 실제 호출로 교체
- `POST /apply-sr` — `payload: dict` → `ApplySrRequest` Pydantic 모델
- `POST /clear-sr` — `payload: dict` → `ClearSrRequest` Pydantic 모델
- `GET /` — `get_developer_view()` 호출, `developer_id` 쿼리 파라미터 추가

### 신규: `spec/DML/ddl`

`db_user_developer_map`, `dml_group`, `dml_log` 테이블 DDL.
마감 회차 보호 트리거(`trg_guard_*`) 포함. 수동 실행 대상.

### 신규: `spec/DML/improvements.md`

추후 개선 후보 6건 기록.

---

## 2026-06-06 — 화면 단 구현

### 페이지 구성 (2개)

| URL | 템플릿 | 역할 |
|-----|--------|------|
| `GET /dml/manager` | `templates/dml_manager.html` | 담당자 — CSV 업로드·진행률 모니터링·자동매핑 |
| `GET /dml/developer` | `templates/dml_developer.html` | 개발자 — 본인 그룹 SR 번호 입력 |

### `templates/dml_manager.html`

| 구성 요소 | 설명 |
|----------|------|
| 시스템 탭 (HR/EPRO/SR/PMS) | 클릭 시 `?system_code=XX` URL 이동 |
| 회차 선택 `<input type=month>` | 변경 시 `?year_month=YYYY-MM` URL 이동 |
| CSV 업로드 버튼 | `POST /dml/manager/upload?year_month=&system_code=` multipart, 업로드 완료 후 통계 toast + 자동 리로드 |
| 자동매핑 버튼 | `POST /dml/manager/enrich`, 결과 패널 인라인 표시 (정상/비정상/판정불가) |
| KPI 카드 4개 | 전체 그룹 / 적용 완료 / 미적용 / 진행률(바 포함) |
| 개발자별 진행 현황 | 진행률 색상 — 100% 초록, ≥50% 파랑, <50% 빨강 |
| 전체 그룹 목록 | 키워드 검색 + 상태 필터(전체/적용됨/미입력) 통합 적용, 표시 건수 실시간 갱신 |

### `templates/dml_developer.html`

| 구성 요소 | 설명 |
|----------|------|
| 회차 선택 | 변경 시 `?year_month=&developer_id=` URL 이동 (developer_id 보존) |
| KPI 카드 4개 | 내 그룹 / 적용 완료 / 미적용 / 진행률 |
| 상태 필터 | 전체 / 미적용만 / 적용완료만 드롭다운 |
| SR 입력 필드 | `Enter` 키 또는 [적용] 버튼 → `POST /dml/developer/apply-sr` |
| 즉시 상태 반영 | 페이지 리로드 없이 행 배경색·배지·취소버튼 인라인 갱신 |
| [취소] 버튼 | 적용됨 상태일 때만 표시 → `POST /dml/developer/clear-sr` |

### 공통 UX 처리

- 상태값 `'미입력'` / `'적용됨'` (한글) 기준으로 필터·배지 통일
- 미적용 행 배경 `#fffbea` (연노랑) 강조
- 모든 서버 요청 결과 toast 알림 (ok/warn/bad)
- 빈 데이터 상태 안내 문구 처리

---

## 미구현 항목 (다음 단계)

- `GET /dml/manager/excel` — excel_exporter 연결 필요
- 개발자 인증 세션 연동 (`developer_id` 쿼리파라미터 → 로그인 세션)
- 개발자 이름 표시 — `app_user` 조회 후 `developer_id` → 이름 매핑
- enrich 결과 DB 캐싱 (improvements.md #2 참고)

## 최종화면 칼럼
명령어	요청 시각	접속계정	사용자명	SR번호	SR제목	작업구분	작업승인일	SR종료일	검증결과
