# 통합 모니터링 대시보드 스펙

## 개요

프로그램변경 · 부서이동자 · DML · DDL 4개 모듈의 기존 KPI/상태 데이터를 한 화면에
모아 보여 주는 **조회 전용** 대시보드. 그래프 위주로 전반적인 현황을 한눈에 파악한다.

- 경로: `GET /dashboard?period=YYYY-MM` (기본값 = 현재 월)
- 보안 접근 로그는 대시보드에서 다루지 않음 (제외).
- 엑셀 출력 등 액션 없음 → 각 카드 클릭 시 해당 모듈 화면으로 이동.
- 그래프는 외부 CDN 없이 **순수 CSS/SVG**(conic-gradient 도넛, SVG 진행률 링,
  CSS 누적 막대)로 구현 — 내부망 환경에서 의존성 없이 렌더.

---

## 데이터 흐름

`routers/dashboard.py` → `dashboard_service.get_dashboard_data(db, year_month)` →
모듈별 기존 서비스 재사용. 모듈별로 `OperationalError`를 독립 처리하여
일부 DB 장애가 전체 화면을 막지 않음 (해당 모듈만 0으로 표시).

| 모듈 | 재사용 함수 | 집계 |
|------|-------------|------|
| 프로그램변경 | `excel_exporter._ui_status` + `ProgramChangeLog` 직접 조회 | 시스템별 건수 / 정상·비정상·미적용 / 정상률 |
| 부서이동자 | `dept_transfer_service.get_monthly_summary` | 권한(HR·PMS·EPRO) total / 미적용 / SR 적용률 |
| DML | `dml_service.get_manager_view` (시스템별 호출) | 그룹 수 / ui_status 분포 / 적용률 |
| DDL | `ddl_service.get_view` (시스템별 호출) | 로그 수 / ui_status 분포 / 위험(is_abnormal) / 적용률 |

- 시스템 코드: `HR · EPRO · SR · PMS` (4개 모듈 공통).
- 통합 상태 분포(도넛)는 3색 상태(정상/비정상/미적용)를 갖는
  **프로그램변경 + DML + DDL** 합산. (부서이동자는 적용/미적용 2상태라 도넛에서 제외,
  자체 KPI 카드·진행률·시스템별 표에는 포함.)

---

## 화면 구성 (`templates/dashboard.html`)

1. **상단 Hero KPI 카드 4개** — 모듈별 총건수 + 비정상/위험·미적용 태그 + SVG 진행률 링.
   카드 클릭 → 해당 모듈 페이지 이동.
2. **통합 SR 상태 도넛** — conic-gradient. 가운데 정상 비율 표시 + 범례(건수·%).
3. **모듈별 진행률 바** — 4개 모듈 SR 적용/정상 처리 비율 가로 막대.
4. **시스템별 모니터링 건수** — 시스템(HR/EPRO/SR/PMS)별 모듈 누적 막대 + 상세 표
   (이상/위험 건수, 점검필요/정상 배지).
5. **최근 이상 이벤트 Top 10** — 프로그램변경 비정상 · DML 비정상 · DDL 비정상/위험을
   시각 내림차순 통합.
6. 회차(`<input type=month>`) 변경 시 `?period=` 로 재조회.

---

## `dashboard_service.get_dashboard_data` 반환 구조

```python
{
  "period": "YYYY-MM",
  "last_updated": "YYYY-MM-DD HH:MM",
  "kpi": {
    "program_change": {total, abnormal(비정상), pending(미적용), progress},
    "dept_transfer":  {total, pending, applied, progress},
    "dml":            {total, pending, abnormal, progress},
    "ddl":            {total, abnormal(위험), pending, progress},
  },
  "status_dist": {"정상": n, "비정상": n, "미적용": n},   # PC+DML+DDL 합산
  "status_pct":  {"정상": %, "비정상": %, "미적용": %},
  "status_total": n,
  "donut_gradient": "conic-gradient 색상 스톱 문자열",
  "by_system": [ {name, program_change, dept_transfer, dml, ddl, abnormal, has_abnormal} ],
  "by_system_max": n,        # 누적 막대 높이 정규화 기준
  "recent_events": [ {time, category, system, account, message} ],  # 최대 10
}
```

---

## 비고

- 성능보다 표현 우선 — 시스템별로 기존 서비스를 반복 호출(각 SR DB 조회 포함)하므로
  호출 수가 많지만 조회 전용 화면이라 허용. SR DB 장애 시 각 서비스의 기존 동작대로
  미적용/0 처리되어 화면은 정상 렌더.
- 신규 의존성 없음(Chart.js 등 미사용).
