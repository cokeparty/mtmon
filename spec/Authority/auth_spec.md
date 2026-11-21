# 인증(Auth) 모듈 설계

## 로그인 범위 결정

### 결론: 대시보드 전체에 적용

DML 부분만 로그인하는 방식은 권장하지 않는다. 이유:

1. **일관성**: 프로그램 변경·DDL·보안로그 등 나머지 화면은 누구나 접근 가능한 상태가 됨.
2. **의존성**: `developer_id`(DML), 검토수행자 식별(부서이동자) 모두 로그인한 사람에서 나와야 함.
3. **보안**: 프로그램 변경 리스트, DDL 로그 등 내부 정보 보호.
4. **구현 단순성**: 전체 미들웨어 한 번으로 처리.

---

## 역할(Role) — 3종

| 역할값 | 명칭 | 설명 |
|--------|------|------|
| `operator` | 운영자 | 전체 화면 조회 + 모니터링 관리 + SR 입력 |
| `developer` | 개발자 | DML 개발자 뷰 (본인 그룹 SR 입력) + 나머지 읽기 전용 |
| `reviewer` | 검토수행자 | 부서이동자 권한유지/회수 판단 + SR 입력. 나머지 읽기 전용 |

### 모듈별 권한 매트릭스

| 모듈 | operator | developer | reviewer |
|------|----------|-----------|----------|
| 대시보드 | ✅ 조회 | ✅ 조회 | ✅ 조회 |
| 프로그램 변경 | ✅ 조회 | ✅ 조회 | ✅ 조회 |
| DML 담당자 뷰 | ✅ 전체 | ❌ | ❌ |
| DML 개발자 뷰 | ✅ | ✅ 본인 그룹 | ❌ |
| DDL | ✅ SR 입력 | ❌ | ❌ |
| 부서이동자 일간 | ✅ SR 입력 | ❌ | ✅ 유지/회수 + SR 입력 |
| 부서이동자 월간 | ✅ 실행·엑셀 | ❌ | ✅ 조회·엑셀 |
| 보안접근로그 | ✅ 조회 | ❌ | ❌ |

> **SR 입력**: operator와 reviewer 모두 가능.  
> **권한유지/회수 결정**: reviewer 전용.  
> **DML 개발자 뷰**: developer 본인 그룹만, operator도 전체 조회 가능.

---

## 인증 방식

**세션 쿠키 방식** (Starlette SessionMiddleware 사용)

- JWT는 로그아웃·강제만료 처리가 번거롭고, 단일 서버 운영이라 세션이 더 단순함.
- `itsdangerous` 서명 쿠키로 세션 데이터 보호.
- 비밀번호 해시: `bcrypt` (`passlib` 라이브러리).

---

## 화면 구성

| 화면 | URL | 설명 |
|------|-----|------|
| 로그인 | `GET/POST /login` | 전체 진입점, 미인증 시 모든 URL에서 리다이렉트 |
| 로그아웃 | `POST /logout` | 세션 삭제 후 /login 이동 |

---

## FastAPI 구현 포인트

1. `SessionMiddleware` 설정 (`SECRET_KEY` 환경변수)
2. `get_current_user` Depends — 세션에서 user_id 읽어 DB 조회, 없으면 `/login` 리다이렉트
3. `require_operator` Depends — role = 'operator' 체크
4. `require_reviewer` Depends — role in ('operator', 'reviewer') 체크 (SR 입력 등 공통 기능)
5. 모든 라우터 GET 핸들러에 `current_user = Depends(get_current_user)` 추가
6. DML 개발자 뷰: `developer_id` URL 파라미터 → `current_user.id` 교체
7. 부서이동자 유지/회수 버튼: `current_user.role == 'reviewer'` 조건으로 표시

---

## 추가 패키지

```
passlib[bcrypt]==1.7.4
itsdangerous==2.2.0       # Starlette SessionMiddleware 의존

```

(`starlette`는 FastAPI에 이미 포함)

---

## 미결 사항

- `developer` 역할의 비DML 화면 상세 접근 범위 확정
- `monitoring_period.closed_by` → `auth.app_user.id` FK 전환 시점
- `dml.db_user_developer_map.developer_id` FK 추가 시점
- 비밀번호 초기화 절차
