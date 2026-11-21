배포 사양을 산정하려면 실제 기술 스택과 의존성, 실행 구조를 봐야 합니다. 관련 파일들을 확인하겠습니다.


발견됨 파일, 읽기 파일 3개, 실행됨 명령 1개
핵심 의존성 하나가 빠져 있고 OS 종속 설정이 있어 추가 확인합니다.

실행됨
Check oracledb in reqs and Python 3.10+ syntax usage
확인 끝났습니다. 모든 DB(PostgreSQL 메인·SR·Oracle·BPM)가 원격 서버라 이 박스는 순수 애플리케이션 서버입니다. 그 기준으로 사양을 산정합니다.

1. 아키텍처 요약
항목	내용
런타임	FastAPI + Uvicorn (단일 프로세스 웹앱)
무거운 라이브러리	pandas/numpy, openpyxl, paramiko, oracledb, SQLAlchemy
DB	전부 원격 (메인 PG …134:5432, SR PG …37, Oracle …121:1521, BPM/EDB …182:5444) → 로컬 DB 미설치
배치	cron으로 scripts/load_*.py 월·일 실행 (pandas+SSH+Oracle 조회)
동시 사용자	내부 운영자/검토자용 소규모 (수~수십 명)
부하 자체는 가볍습니다(조회 데이터 수백 행 수준). 메모리는 pandas/Oracle client가 좌우합니다.

2. 소프트웨어 요구사항
항목	권장
OS	RHEL 8.x 또는 9.x (x86_64)
Python	3.10 이상 필수 — routers/program_change.py가 `str
네이티브 패키지	libaio(Oracle Instant Client용), glibc; psycopg2-binary·bcrypt·cryptography는 wheel이라 컴파일러 불필요(없으면 gcc만)
Oracle Instant Client	필수 설치 (oracledb thick 모드). basic 패키지 압축 해제 후 ORACLE_CLIENT_LIB_DIR 지정
프로세스 관리	systemd + nginx(리버스 프록시/HTTPS) 권장, gunicorn -k uvicorn.workers.UvicornWorker

3. 하드웨어 사양
최소	권장
vCPU	2 core	4 core
RAM	4 GB	8 GB
Disk	20 GB	40–50 GB (SSD)
산정 근거

메모리: Uvicorn 워커당 pandas/numpy/oracledb 로드 시 ~200–300 MB. 워커 2–4개 + 월배치(pandas로 CSV/로그 in-memory 처리, 수백 MB 스파이크) 동시 실행 여유 → 8 GB 권장(4 GB로도 가동은 가능).
CPU: 상시 부하 낮음. 월배치 pandas 변환·엑셀 생성 시 잠깐 사용 → 4 core면 배치+서빙 동시도 여유.
디스크: OS(~5 GB) + Python venv(pandas/numpy 포함 ~0.7 GB) + Oracle Instant Client(~0.5 GB) + 앱(3.6 MB) + 로그/임시파일. 20 GB로 충분하나 로그 누적·여유로 40–50 GB 권장.

4. 방화벽(아웃바운드) 개방 필요
5432(PG 메인·SR), 1521(Oracle), 5444(BPM/EDB), 22(A서버 SFTP …183, B서버 NFS 10.100.1.52). 인바운드는 nginx 443(또는 직접 8000).

5. ⚠️ 배포 전 반드시 고칠 사항 (현재 그대로면 동작 불가/위험)
oracledb가 requirements.txt에 누락 → 부서이동자 배치 전부 실패. 추가 필요 (oracledb>=2.0).
ORACLE_CLIENT_LIB_DIR가 Windows 경로 (C:\Program Files\…) → 리눅스 경로로 변경(예: /opt/oracle/instantclient_23_x). thick 모드가 불필요하면 thin 모드로 전환해 Instant Client 자체를 생략하는 것도 가능.
시크릿/DB 비밀번호가 config.py에 하드코딩 (SECRET_KEY, DB·SSH 패스워드) → .env로 분리하고 권한 600. 운영 HTTPS 시 main.py의 https_only=True로.
uvicorn.run(reload=True)는 개발용 → 운영은 gunicorn/uvicorn 다중 워커 + systemd.

6. 신청 사항
(1) 서버신청 SR -> IP신청 SR(서버담당자가 직접함)
(2) 보안신청 (정보보호포털) 
(3) 서버환경변경 신청 (OS 방화벽)
(4) 사용자리스트 추가

