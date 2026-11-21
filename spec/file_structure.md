app/
├── main.py
├── config.py
├── database.py
├── models/
│   ├── user.py
│   ├── period.py
│   ├── server_config.py
│   ├── program_change.py        # 17컬럼 매핑, 결재 컬럼 없음
│   ├── dept_transfer.py
│   ├── dml.py                   # dml_log + dml_group
│   ├── ddl.py
│   └── security_log.py
├── routers/
│   ├── auth.py
│   ├── dashboard.py
│   ├── program_change.py
│   ├── dept_transfer.py
│   ├── dml_manager.py
│   ├── dml_developer.py
│   ├── ddl.py
│   └── security_log.py
├── services/
│   ├── auth_service.py
│   ├── period_service.py
│   ├── server_config_service.py
│   ├── sftp_log_collector.py    # A서버 SSH + xferlog 파싱(wc 제거)
│   ├── nfs_scanner.py           # B서버 NFS SR폴더 스캔 → basename 인덱스
│   ├── sr_mapper.py             # basename 매핑 + mtime 충돌해소
│   ├── sr_db_client.py          # 외부 SR DB
│   ├── pcl_judger.py            # 일반/긴급변경/SR없음/충돌. 결재 판정 없음
│   ├── dept_transfer_service.py
│   ├── dml_service.py           # 그루핑 + 자동매핑
│   ├── ddl_service.py           # 적재 + 이상표시 (별개 서비스)
│   ├── security_log_loader.py
│   └── excel_exporter.py
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── program_change.html      # 17컬럼, 결재 3칸 빈칸 출력
│   ├── dept_transfer.html
│   ├── dml_manager.html
│   ├── dml_developer.html
│   ├── ddl.html
│   └── security_log.html
└── static/ (css/js)

scripts/
└── load_security_log.py         # 크론 OS 로그 CSV 적재
