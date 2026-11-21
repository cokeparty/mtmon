# 프로그램변경 모니터링 — 파일 구조

```
models/
├── period.py
├── server_config.py
└── program_change.py

schemas/
└── program_change.py

routers/
└── program_change.py

services/
├── collect_orchestrator.py
├── sftp_log_collector.py
├── nfs_scanner.py
├── sr_mapper.py
├── sr_db_client.py
├── pcl_judger.py
├── server_config_service.py
└── excel_exporter.py

scripts/
└── load_program_change.py

templates/
└── program_change.html

spec/program_change/
├── file_structure.md
├── ddl/
├── dml/
├── select/
├── erd.md
├── ftp_process.md
├── nfs_mapping_rule.md
└── table_define.md
```
