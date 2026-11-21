# 부서이동자 모니터링 모듈 스펙

---

## 개요

부서이동자(퇴직·부서변경)에 대해 시스템별 추가권한을 점검하고 유지/회수 여부를 결정하는 모듈.

| 구분 | 주기 | 데이터 원천 | 목적 |
|------|------|------------|------|
| 일간 모니터링 | 매일 자동 | `html_sql.md` (7일 뷰) | 즉시 처리 필요 항목 확인·조치 |
| 월간 모니터링 | 월초 1회 | `select` (월간 쿼리) | 공식 월간 보고서 생성·엑셀 출력 |

---

## 사용자 역할

| 역할 | 일간 화면 | 월간 화면 |
|------|-----------|-----------|
| `operator` (운영자) | 조회 + SR 입력 | 조회 + 실행 + 엑셀 다운로드 |
| `reviewer` (검토수행자) | 조회 + **권한유지/회수** + SR 입력 | 조회 + 엑셀 다운로드 |
| `developer` (개발자) | 접근 불가 | 접근 불가 |
| 미인증 | 접근 불가 | 접근 불가 |

> 권한유지/회수 결정 = `reviewer` 전용.  
> SR 입력 = `operator`, `reviewer` 모두 가능.

---

## 1. 일간 모니터링

### 1-1. 자동 적재 (스케줄 배치)

매일 지정 시각에 `scripts/load_daily_dept_transfer.py` 자동 실행.  
담당자가 직접 버튼을 누르지 않아도 DB에 최신 데이터가 쌓임.

```
크론 예시: 10 8 * * *  python -m scripts.load_daily_dept_transfer
```

**중복 처리 전략 — UPSERT**

7일 뷰(cbo_sa_dept_chg_7) 특성상 같은 레코드가 최대 7일간 반복 조회됨.  
`INSERT ... ON CONFLICT DO UPDATE`로 중복 방지:

```
최초 조회 → INSERT  (first_seen=today, last_seen=today, action=NULL)
2~7일째   → UPDATE  last_seen=today  (action·sr_no·remark 보존)
처리 완료 → UPDATE  last_seen만 갱신, 처리 상태 덮어쓰지 않음
```

Unique index: `(record_type, empno, change_date, COALESCE(role_code, '-'))`

### 1-2. 조회 대상 (html_sql.md 기반 — 5개 쿼리 UNION ALL)

| 순번 | 구분 | 원천 | 윈도우 |
|------|------|------|--------|
| 1 | 퇴직자 (인사이력) | `is_pe01_history@prod_view` | SYSDATE-7 이후 |
| 2 | 퇴직자 (ISG마스터) | `cbo_sa_isg_empmst@prod_view` | SYSDATE-7 이후 |
| 3 | 부서변경자 | `cbo_sa_dept_chg_7@prod_view` | 7일 고정 뷰 |
| 4 | **HR(ERP) 추가권한** | `wf_user_role_assignments_v` + `is_pe01_history` | SYSDATE-7 이후 |
| 5 | 전자조달(EMRO) 추가권한 | `esaaurp` + `cbo_sa_dept_chg_7` | 7일 고정 뷰 |
| 6 | PMS 추가권한 | `cm_user_rgt_grp` + `cbo_sa_dept_chg_7` | 7일 고정 뷰 |

### 1-3. 화면 구성 (`/dept-transfer/daily`)

- **탭**: 전체 | 퇴직자 | 부서변경자 | 전자조달 | PMS
- **표시 항목**: 부서변경일, 사번, 이름, 이전부서, 현재부서, 권한명, 권한등록일, 처리상태
- **SR 입력** (operator·reviewer 가능):
  - SR번호 입력 시 `sr_db_client.fetch()` 로 SR 정보 자동 매핑 (sr_title, work_type, appr_date 등)
  - 기존 `services/sr_db_client.py` 재사용
- **권한유지/회수 결정** (reviewer 전용):
  - [권한유지] [권한회수] 버튼 → `action`, 처리일시 저장
  - 처리 완료 건: 배지로 상태 표시, 버튼 비활성화
- **미처리 강조**: 권한 보유 건(전자조달·PMS)이 미처리면 노란색 행

### 1-4. SR 자동 매핑 로직

```
1. 사용자가 SR번호 입력 후 [저장] 클릭
2. sr_db_client.fetch(sr_no) 호출
3. 성공 시 sr_title, sr_work_type, sr_approved_at, sr_closed_at 자동 채움
4. DB에 저장 (daily_record.sr_no + sr_title + sr_work_type 등)
5. 실패(SR 없음) 시 경고 토스트, 저장은 진행
```

---

## 2. 월간 모니터링

### 2-1. 조회 대상 (select 파일 기반 — 4개 파트)

월초에 `operator` 또는 `reviewer`가 화면에서 실행.

| 파트 | 시스템 | 내용 |
|------|--------|------|
| A | 공통 | 부서이동자 리스트 (is_pe01_history 기반) |
| B | PMS | 부서변경자의 PMS 권한 현황 |
| C | HR(ERP) | 부서변경자의 ERP 권한 현황 |
| D | 전자조달(EPRO) | 부서변경자의 EMRO 권한 현황 |

### 2-2. 출력 파일 분리

| 파트 | 조회 | 엑셀 다운로드 |
|------|------|-------------|
| A 부서이동자 리스트 | ✅ | ❌ (조회만) |
| B PMS | ✅ | ✅ |
| C HR | ✅ | ✅ |
| D 전자조달 | ✅ | ✅ |

### 2-3. 엑셀 출력 형태 (final_file.md 기준)

PMS·HR·전자조달 각각 별도 시트. 공통 컬럼 구조:

| 컬럼 | 설명 |
|------|------|
| 업무명 | PMS / HR / 전자조달 |
| 부서변경일 | yyyy.mm.dd |
| 권한명 | 시스템 내 권한 이름 |
| 권한코드 | role_cd |
| 사번 | |
| 이름 | |
| 권한등록일 | |
| 권한회수일 | reviewer 입력값 |
| 부서명 | 현재 부서 |
| 이전부서명 | |
| SR | SR번호 |
| 비고 | |

### 2-4. 화면 구성 (`/dept-transfer`)

- **탭**: 부서이동자 리스트 | PMS | HR | 전자조달
- **월간 조회 실행** 버튼: operator·reviewer 가능
- **SR 입력 + 자동 매핑**: 1-4와 동일 로직
- **엑셀 다운로드**: PMS·HR·전자조달 탭에서 각각

---

## 3. DB 스키마

> DDL: `spec/dept_transfer/ddl`

**`dept_transfer` 스키마**

### daily_record — 일간 조회 결과

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGINT PK | |
| record_type | VARCHAR(20) | 퇴직자·부서변경자·전자조달권한·PMS권한 |
| empno | VARCHAR(20) | 사번 |
| emp_name | VARCHAR(50) | 이름 |
| change_date | DATE | 부서변경일/퇴직일 |
| dept_code | VARCHAR(50) | 현재 부서코드 |
| dept_name | VARCHAR(100) | 현재 부서명 |
| prev_dept_name | VARCHAR(100) | 이전 부서명 |
| role_code | VARCHAR(50) | 권한코드 (NULL=권한 없는 건) |
| role_name | VARCHAR(200) | 권한명 |
| reg_date | DATE | 권한등록일 |
| action | VARCHAR(10) | 유지·회수·NULL(미처리) |
| sr_no | VARCHAR(30) | SR번호 |
| sr_title | VARCHAR(300) | SR 자동 매핑 |
| sr_work_type | VARCHAR(50) | SR 자동 매핑 |
| remark | VARCHAR(500) | 비고 |
| processed_by | BIGINT | 처리자 auth.app_user.id |
| processed_at | TIMESTAMP | 처리일시 |
| first_seen | DATE | 최초 조회일 |
| last_seen | DATE | 최근 조회일 (매일 갱신) |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

Unique index: `(record_type, empno, change_date, COALESCE(role_code, '-'))`

### monthly_record — 월간 조회 결과

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGINT PK | |
| period_id | BIGINT | FK → program_change.monitoring_period |
| system_code | VARCHAR(20) | PMS·HR·EPRO·공통 |
| empno | VARCHAR(20) | |
| emp_name | VARCHAR(50) | |
| change_date | DATE | |
| dept_name | VARCHAR(100) | |
| prev_dept_name | VARCHAR(100) | |
| role_code | VARCHAR(50) | |
| role_name | VARCHAR(200) | |
| reg_date | DATE | |
| revoke_date | DATE | 권한회수일 (reviewer 입력) |
| sr_no | VARCHAR(30) | |
| sr_title | VARCHAR(300) | SR 자동 매핑 |
| sr_work_type | VARCHAR(50) | SR 자동 매핑 |
| remark | VARCHAR(500) | |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

Unique: `(period_id, system_code, empno, COALESCE(role_code, '-'))`

---

## 4. 파일 구조

```
spec/dept_transfer/
├── dept_transfer_spec.md   ← 이 파일
├── html_sql.md             ← 일간 조회 SQL (7일 뷰 기반, 5개 UNION ALL)
├── html_output.md          ← 일간 조회 결과 화면 참고
├── select                  ← 월간 조회 SQL (부서이동자 리스트 + PMS/HR/EPRO)
├── final_file.md           ← 월간 엑셀 출력 컬럼 형태 참고
└── ddl                     ← dept_transfer 스키마 DDL
```

---

## 5. 미결 사항

- 일간 자동 배치의 Oracle DB 연결 설정 (HR/EPRO/PMS 각각 별도 접속 정보)
- 월간 조회 실행 시점: 수동 버튼 클릭만 vs 월초 자동 배치도 병행
