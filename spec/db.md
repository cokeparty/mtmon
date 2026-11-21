# 데이터베이스 구조 (실제 구현 기준)

> 이 파일은 **실제 코드·DDL 파일과 일치하는 현재 상태**를 기록한다.
> 초기 설계안(구 버전)은 git 히스토리에만 남긴다.

---

## 스키마 구성

| 스키마 | 역할 | DDL 파일 |
|--------|------|----------|
| `program_change` | 프로그램 변경 리스트 + 공통 인프라 | `spec/program_change/ddl` |
| `dml` | DML 모니터링 | `spec/DML/ddl` |
| `ddl` | DDL 모니터링 | `spec/DDL/ddl` |
| `auth` | 사용자 인증 (미구현) | `spec/auth/ddl` |

---

## 공통 오브젝트 (program_change 스키마)

### ENUM 타입 — 미사용

> ENUM 대신 **VARCHAR** 컬럼으로 관리. Python 코드에서는 `str` 기반 enum 클래스를
> 상수로 사용하되 DB 컬럼 타입은 VARCHAR.

| 컬럼 | VARCHAR 길이 | 허용 값 |
|------|-------------|---------|
| `monitoring_period.status` | VARCHAR(10) | open \| closed |
| `server_config.system_code` | VARCHAR(10) | HR \| EPRO \| SR \| PMS |
| `program_change_log.system_code` | VARCHAR(10) | HR \| EPRO \| SR \| PMS |
| `program_change_log.map_type` | VARCHAR(30) | none \| single \| session_anchor \| check |
| `program_change_log.result` | VARCHAR(20) | 정상 \| SR없음 \| 경고 \| 이상 |
| `program_change_log.normal_yn` | VARCHAR(10) | 정상 \| 이상 |
| `dml_group.status`, `dml_log.status`, `ddl_log.status` | VARCHAR(10) | 미입력 \| 적용됨 |
| `ddl_log.ddl_type` | VARCHAR(10) | CREATE \| ALTER \| DROP \| TRUNCATE \| RENAME |
| `auth.app_user.role` | VARCHAR(20) | operator \| developer \| reviewer |

### 공통 함수

| 함수 | 역할 |
|------|------|
| `program_change.set_updated_at()` | BEFORE UPDATE 트리거 — `updated_at = now()` |
| `program_change.guard_closed_period()` | 마감 회차(`status='closed'`) 변경 차단 |

---

## program_change 스키마

### monitoring_period — 월 회차

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGINT PK | |
| year_month | CHAR(7) UNIQUE NOT NULL | 'YYYY-MM' |
| status | period_status NOT NULL DEFAULT 'open' | open=수정가능, closed=조회전용 |
| closed_at | TIMESTAMP | |
| closed_by | VARCHAR(50) | 마감 처리자 (미구현 — 추후 auth.app_user FK) |
| created_at | TIMESTAMP NOT NULL DEFAULT now() | |

### server_config — 시스템별 수집 설정

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGINT PK | |
| system_code | system_code_t UNIQUE NOT NULL | |
| ssh_host | VARCHAR(100) NOT NULL | A서버 (xferlog) |
| ssh_port | INTEGER NOT NULL DEFAULT 22 | |
| ssh_user | VARCHAR(50) NOT NULL | |
| ssh_key_path | VARCHAR(300) | |
| ssh_password | VARCHAR(200) | |
| log_dir | VARCHAR(300) NOT NULL | |
| log_pattern | VARCHAR(100) NOT NULL | `*{ym}*` 형식 |
| include_path | VARCHAR(300) NOT NULL | grep 필터 경로 |
| include_flag | VARCHAR(50) NOT NULL | grep 필터 플래그 |
| nfs_ssh_host | VARCHAR(100) | B서버 (NFS) |
| nfs_ssh_port | INTEGER DEFAULT 22 | |
| nfs_ssh_user | VARCHAR(50) | |
| nfs_ssh_key_path | VARCHAR(300) | |
| nfs_ssh_password | VARCHAR(200) | |
| nfs_base_dir | VARCHAR(300) | SR 폴더 루트 경로 |
| updated_at | TIMESTAMP NOT NULL DEFAULT now() | |

### program_change_log — 프로그램 변경 로그

상세 컬럼은 `spec/program_change/ddl` 참고.  
요약: deploy_time + file_name 기준 NFS 매핑 → SR 스냅샷 → 판정(result/normal_yn).

---

## dml 스키마

상세 DDL: `spec/DML/ddl`

### db_user_developer_map

DBSAFER 사용자명(db_user) → 개발자 ID 매핑.  
developer_id: 현재 FK 없음 — auth.app_user 확정 후 추가 예정.

### dml_group

CSV 파싱 후 (user_name + account + target_table + 200초 시간윈도우) 기준 그루핑.  
개발자가 SR번호를 group 단위로 입력.

### dml_log

DBSAFER CSV 원본 1행 = 1 레코드.  
group_id로 dml_group 참조, sr_no·status는 그룹 SR과 동기화.

---

## ddl 스키마

상세 DDL: `spec/DDL/ddl`

### ddl_log

DBSAFER CSV 원본 1행 = 1 레코드.  
담당자 = 개발자 단일 역할이므로 그룹 테이블 없이 행 단위로 SR 입력.  
DROP/TRUNCATE → is_abnormal = TRUE 자동 마킹.

---

## 미구현 모듈 (라우터·더미 데이터만 존재)

| 모듈 | 라우터 | 모델/DDL | 비고 |
|------|--------|----------|------|
| 부서이동자 | `routers/dept_transfer.py` | 없음 | 더미 데이터 |
| 보안접근로그 | `routers/security_log.py` | 없음 | 더미 데이터 |
| 인증 | 없음 | `spec/auth/ddl` 작성됨 | 미구현 |

---

## DDL 실행 순서

```
1. spec/program_change/ddl   ← ENUM + 공통 함수 + program_change 스키마 테이블
2. spec/DML/ddl              ← dml_status ENUM + dml 스키마 테이블
3. spec/DDL/ddl              ← ddl_type ENUM + ddl 스키마 테이블
4. spec/auth/ddl             ← auth 스키마 + app_user 테이블 (미구현)
```
