# DDL 모니터링 — 파일 구조

```
models/
├── period.py
├── dml.py
└── ddl.py

schemas/
└── ddl.py

routers/
└── ddl.py

services/
├── ddl_service.py
├── ddl_parser.py
├── sr_validation.py     ← DML·DDL 공용 SR 검증 (judge_validation, enrich_and_validate)
└── sr_db_client.py

templates/
└── ddl.html

spec/ddl/
├── file_structure.md
└── ddl/
```
