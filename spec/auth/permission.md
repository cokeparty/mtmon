# 권한(Permission) 체계 설계 (예상)

> **상태**: 설계안 (미구현)  
> 현재는 `operator / developer / reviewer` 3개 역할로 모듈 단위 접근 제어.  
> 향후 역할에 세부 권한을 자유롭게 조합하는 RBAC 체계로 전환 예정.

---

## 예상 권한 목록

### 계정 관리 (`user.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `user.view` | 계정 목록 조회 |
| `user.create` | 계정 생성 |
| `user.edit_role` | 계정 역할 변경 |
| `user.toggle_active` | 계정 활성화 / 비활성화 |
| `user.reset_password` | 비밀번호 초기화 |

### 대시보드 (`dashboard.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `dashboard.view` | 통합 대시보드 조회 |

### 프로그램변경 (`program_change.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `program_change.view` | 프로그램변경 모니터링 조회 |
| `program_change.edit_sr` | SR 번호 입력 / 수정 |
| `program_change.edit_approver` | 결재자 · 개발자 · 검토수행자 편집 |
| `program_change.export` | 엑셀 출력 |

### 데이터변경 DML (`dml.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `dml.view_manager` | DML 담당자 화면 조회 |
| `dml.upload_csv` | DBSAFER CSV 업로드 |
| `dml.auto_map` | 자동 매핑(SR DB 조회) 실행 |
| `dml.view_developer` | DML 개발자 화면 조회 (본인 그룹) |
| `dml.input_sr` | SR 번호 입력 / 변경 |
| `dml.set_non_dml` | 비DML 표시 / 해제 |
| `dml.input_reason` | 비정상 소명 사유 입력 |
| `dml.export` | 엑셀 출력 |

### 프로시저 DDL (`ddl.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `ddl.view` | DDL 모니터링 조회 |
| `ddl.input_sr` | SR 번호 입력 / 변경 |
| `ddl.export` | 엑셀 출력 |

### 부서이동자 (`dept_transfer.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `dept_transfer.view_daily` | 일간 부서이동자 조회 |
| `dept_transfer.input_sr` | SR 번호 입력 / 변경 |
| `dept_transfer.set_action` | 유지 / 회수 처리 |
| `dept_transfer.view_monthly` | 월간 부서이동자 조회 |
| `dept_transfer.run_collect` | 월간 수집 배치 실행 |
| `dept_transfer.export` | 엑셀 출력 |

### 보안접근로그 (`security_log.*`)

| 권한 코드 | 설명 |
|-----------|------|
| `security_log.view` | 보안 접근 로그 조회 |

---

## 역할별 권한 매핑 (현재 역할 기준)

| 권한 코드 | operator | developer | reviewer |
|-----------|:--------:|:---------:|:--------:|
| `user.view` | ✅ | ❌ | ❌ |
| `user.create` | ✅ | ❌ | ❌ |
| `user.edit_role` | ✅ | ❌ | ❌ |
| `user.toggle_active` | ✅ | ❌ | ❌ |
| `user.reset_password` | ✅ | ❌ | ❌ |
| `dashboard.view` | ✅ | ✅ | ✅ |
| `program_change.view` | ✅ | ✅ | ✅ |
| `program_change.edit_sr` | ✅ | ❌ | ❌ |
| `program_change.edit_approver` | ✅ | ❌ | ❌ |
| `program_change.export` | ✅ | ❌ | ❌ |
| `dml.view_manager` | ✅ | ❌ | ❌ |
| `dml.upload_csv` | ✅ | ❌ | ❌ |
| `dml.auto_map` | ✅ | ❌ | ❌ |
| `dml.view_developer` | ✅ | ✅ | ❌ |
| `dml.input_sr` | ✅ | ✅ | ❌ |
| `dml.set_non_dml` | ✅ | ✅ | ❌ |
| `dml.input_reason` | ✅ | ✅ | ❌ |
| `dml.export` | ✅ | ❌ | ❌ |
| `ddl.view` | ✅ | ❌ | ❌ |
| `ddl.input_sr` | ✅ | ❌ | ❌ |
| `ddl.export` | ✅ | ❌ | ❌ |
| `dept_transfer.view_daily` | ✅ | ❌ | ✅ |
| `dept_transfer.input_sr` | ✅ | ❌ | ✅ |
| `dept_transfer.set_action` | ✅ | ❌ | ✅ |
| `dept_transfer.view_monthly` | ✅ | ❌ | ✅ |
| `dept_transfer.run_collect` | ✅ | ❌ | ❌ |
| `dept_transfer.export` | ✅ | ❌ | ✅ |
| `security_log.view` | ✅ | ❌ | ❌ |

---

## 구현 예정 방식

```
auth.permission        : id, code, description
auth.role_permission   : role_name, permission_code
```

- 역할 편집 화면에서 권한을 체크박스로 조합
- 코드에서 `require_permission("dml.upload_csv")` 형태로 의존성 체크
- 현재 `require_operator / require_reviewer` Depends를 단계적으로 교체
