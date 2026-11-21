# 대시보드 — 파일 구조

```
routers/
└── dashboard.py            ← GET /dashboard (회차 ?period= 파라미터)

services/
├── dashboard_service.py    ← 4개 모듈 KPI/상태 통합 집계 (신규)
├── dml_service.py          ← (재사용) get_manager_view
├── ddl_service.py          ← (재사용) get_view
├── dept_transfer_service.py← (재사용) get_monthly_summary
└── excel_exporter.py       ← (재사용) _ui_status — 프로그램변경 상태 판정

models/
├── period.py               ← (재사용) MonitoringPeriod (year_month)
└── program_change.py       ← (재사용) ProgramChangeLog

templates/
└── dashboard.html          ← Hero KPI 카드 + 도넛/진행률/누적막대 (CSS·SVG, 외부 의존성 없음)

spec/dashboard/
├── file_structure.md       ← 이 파일
└── dashboard_spec.md       ← 구현 내용
```

> 신규 파일: `services/dashboard_service.py`.
> 나머지는 기존 모듈 서비스를 그대로 재사용하며, 대시보드는 조회 전용(엑셀 출력 없음).
