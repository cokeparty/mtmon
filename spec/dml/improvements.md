# DML 파서 개선 후보

## 1. SR번호 이중 포맷 지원
현재 패턴: `[A-Za-z]\d{2}-\d{8}-\d{3}` (예: H01-20260401-001)
과거 시스템에서 `SR123456` 형태의 번호가 섞인 CSV가 유입될 가능성이 있다면
`SR_COMMENT_RE`를 `|`로 연결해 두 패턴을 동시에 처리하는 방안 고려.

## 2. `enrich` 결과 캐싱
현재 `/enrich` 호출마다 외부 SR DB에 실시간 조회한다.
`dml_group` 테이블에 `sr_title`, `work_type`, `appr_date`, `close_date`,
`validation_result` 컬럼을 추가하면 enrich 결과를 DB에 저장할 수 있고,
엑셀 출력 시 SR DB 재조회 없이 빠르게 처리 가능.

## 3. Two-Pointer 벡터화
현재 Python 루프로 구현. 행 수 > 50,000 이면 속도 저하 가능.
`pandas.merge_asof`를 이용한 벡터화 방식으로 교체하면 성능 개선 여지 있음.
(정확도 검증 후 교체 필요 — 체인 전파 동작이 달라질 수 있음)

## 4. 개발자 인증 연동
`/dml/developer` 뷰의 `developer_id`가 현재 쿼리 파라미터(`?developer_id=1`).
`app_user` 기반 세션/토큰 인증이 구축되면 `developer_id`를 세션에서 읽도록 교체
필요. 그 전까지 누구나 타인의 그룹에 SR을 입력할 수 있는 보안 공백이 있음.

## 5. 엑셀 출력 (excel_exporter 연결)
`GET /dml/manager/excel`이 현재 미구현. `services/excel_exporter.py`에 DML용
시트를 추가하거나 별도 `dml_excel_exporter.py`를 작성해서 연결.
출력 컬럼: 명령어, 요청시각, 접속계정, 사용자명, SR번호, SR제목, 작업구분,
작업승인일, SR종료일, 검증결과. 색상 서식: 정상=파스텔그린, 비정상=파스텔레드.

## 6. NaT 행 그룹 처리
`_assign_time_groups()`에서 NaT 행은 항상 새 그룹을 시작한다.
같은 (user, account, table)의 NaT 행끼리 하나의 그룹으로 묶고 싶다면
별도 NaT 그룹 로직 추가 필요.
