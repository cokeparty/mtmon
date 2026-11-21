# DML 모니터링 — 파일 구조

```
models/
├── period.py
└── dml.py

schemas/
└── dml.py

routers/
├── dml_manager.py
└── dml_developer.py

services/
├── dml_service.py
├── dml_parser.py
├── dml_validation.py    ← 하위 호환 shim (sr_validation 재export)
├── sr_validation.py     ← DML·DDL 공용 SR 검증 (judge_validation, enrich_and_validate)
└── sr_db_client.py

templates/
├── dml_manager.html
└── dml_developer.html

spec/dml/
├── file_structure.md
├── dml_spec.md
├── improvements.md
├── migration_sum.md
├── ddl/
├── sr_enrich_v1.9.py
└── sr_ext.py
```
