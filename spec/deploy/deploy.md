# 운영 배포 매뉴얼 (2026-11 개편 이후)

> 서버: `/opt/mtmon` (소스) · `/opt/mtmon/.env` (설정) · `/opt/mtmon/venv` (가상환경) · `/data/mtmon/logs` (로그)
> 서비스 이름은 실제 systemd 서비스명으로 바꿔 읽으세요 (아래는 `mtmon`).

---

## A. 평소 배포 (바뀐 파일만 업로드)

**개발 PC**
1. 변경 내용 커밋
2. 패치 묶기 — 지난 배포 이후 바뀐 파일만 zip 으로 만들고 배포 태그를 단다
   ```
   python tools/changed_files.py --tag
   ```
   → `dist/patch-날짜.zip` (업로드할 파일), `dist/patch-날짜.txt` (업로드·삭제 목록 + 주의사항)
3. txt 를 열어 `[주의]` 줄 확인
   - `requirements.txt 변경` → 아래 C. 패키지 갱신 먼저
   - `DB 구조 변경 포함` → 재시작 시 자동 적용됨 (할 일 없음, 4번에서 확인만)

**운영 서버**
1. zip 을 `/opt/mtmon` 에 풀기 (같은 경로에 덮어쓰기)
   ```
   cd /opt/mtmon && unzip -o /tmp/patch-날짜.zip
   ```
2. txt 의 `[서버에서 삭제할 파일]` 이 있으면 지우기
3. 재시작
   ```
   sudo systemctl restart mtmon
   ```
4. 확인
   ```
   sudo systemctl status mtmon
   tail -n 30 /data/mtmon/logs/app/application-$(date +%F).log
   ```
   - 정상: `DB 구조 최신 상태 (버전 0008)` 또는 `DB 구조 변경 적용 완료 (버전 …)`
   - 화면 접속 → 로그인 → `/batch`(배치관리) 에서 스케줄러 "동작 중" 확인

* `.env`, `venv/`, `wheelhouse/`, `logs/` 는 서버에만 있고 패치에 들어가지 않음 (덮어쓸 걱정 없음)

---

## B. DB 구조 변경은 어떻게 반영되나 (Alembic)

* **앱이 시작될 때 자동으로 적용된다.** `python main.py` 로 띄우든 systemd(uvicorn) 로 띄우든 같다.
  (`.env` 의 `AUTO_MIGRATE=true`, 기본값)
* 순서: 앱 시작 → `migrations/versions/` 중 아직 안 된 것만 차례로 실행 → 성공하면 화면 시작
* 워커가 여러 개여도 DB 잠금으로 **한 번만** 실행된다.
* **실패하면 앱이 뜨지 않는다** (반쯤 바뀐 DB 로 서비스하지 않기 위함)
  → `/data/mtmon/logs/error/` 에서 원인 확인 → 고친 뒤 재시작
* 현재 DB 버전 확인 / 수동 적용 (서버에서)
  ```
  cd /opt/mtmon && source venv/bin/activate
  python -m alembic current          # 현재 버전
  python -m alembic upgrade head     # 수동 적용 (AUTO_MIGRATE=false 로 운영할 때)
  ```
* 개발자가 DB 구조를 바꿀 때
  1. `models/` 수정
  2. `python -m alembic revision --autogenerate -m "설명"` → `migrations/versions/` 에 파일 생성
  3. 생성된 파일을 **반드시 열어서 검토** (이름 변경은 삭제+생성으로 잡히는 등 틀릴 수 있음)
  4. 개발 DB 에 앱 재시작으로 적용해 보고 커밋 → 평소 배포(A)로 반영

| 버전 | 내용 |
|---|---|
| 0001 | 기준 구조 (이미 있는 테이블은 건드리지 않음) |
| 0002 | 스키마 이름 변경 program_change→program, dept_transfer→depart, auth→account, 공통 테이블→common |
| 0003 | 배치 테이블 (common.batch_job, batch_history) |
| 0004 | 마감 보호 트리거 DELETE 버그 수정 |
| 0005 | 배포 이력 테이블 deploy.deploy_history (운영엔 이미 있음 → 건너뜀) |
| 0006 | 역할·페이지 권한 테이블(account.role, role_permission), 계정 마지막 접속일, DDL 위험(is_abnormal) 칸 삭제 |
| 0007 | 관리자(administrator) 역할 — 모든 권한, 앱에서 보이지 않음 · 부여/수정 불가 |
| 0008 | 계정 역할 칼럼의 옛 CHECK 제약(4개 역할만 허용) 제거 — 역할 검사는 0006 의 참조 제약이 담당 |

* **관리자 계정 지정 (DB 에서만 가능)** — 앱 화면에서는 줄 수도 바꿀 수도 없다
  ```
  UPDATE account.app_user SET role = 'administrator' WHERE login_id = '아이디';
  UPDATE account.app_user SET role = 'operator'      WHERE login_id = '아이디';   -- 해제
  ```
  바로 적용된다 (재시작·재로그인 불필요).

---

## C. 패키지가 바뀌었을 때 (requirements.txt)

폐쇄망이라 인터넷 PC 에서 wheel 을 받아 옮긴다. (자세한 명령은 아래 "이전 문서"의 1번)
1. 개발 PC: `wheelhouse` 다시 받기 (requirements.txt 기준, 의존 패키지까지 자동)
2. `wheelhouse/` 를 서버 `/opt/mtmon/wheelhouse` 로 복사
3. 서버:
   ```
   cd /opt/mtmon && source venv/bin/activate
   pip install --no-index --find-links=./wheelhouse -r requirements.txt
   sudo systemctl restart mtmon
   ```

---

## D. 이번 개편 첫 배포 — 1회만 하는 일 (순서대로)

이번 배포는 구조가 크게 바뀌므로 패치(zip)가 아니라 **소스 전체 교체**를 권장.

1. **DB 백업** (만일을 대비)
   ```
   pg_dump -h <호스트> -U <계정> -d <DB명> -Fc -f /backup/mtmon-before-2026-11.dump
   ```
2. **crontab 정리** — 배치가 앱 안으로 들어왔으므로 기존 3줄 삭제 (`crontab -e`)
   - 삭제 대상: `scripts.load_program_change`, `load_daily_dept_transfer`, `run_dept_monthly.sh`
   - 안 지우면 없는 파일을 실행하다 매번 실패함
3. **앱 중지** `sudo systemctl stop mtmon`
4. **소스 교체** — `/opt/mtmon` 의 `.env`, `venv/`, `wheelhouse/` 는 남기고 나머지를 새 소스로
5. **패키지 추가 설치** — 새로 필요한 것: `alembic`, `APScheduler`(+`tzlocal`), `JPype1==1.5.2` (서버 Java 8 용, oracledb 는 더 이상 안 씀)
   → C. 순서대로 wheelhouse 갱신 후 설치
6. **.env 작성** — `.env.example` 을 복사해 값 채우기
   ```
   cp .env.example .env && vi .env
   ```
   - 옛 운영 값은 개발 PC 에서 `git show <개편 전 커밋>:config.py` 로 확인
     (DATABASE_URL, SR_DB_URL, SECRET_KEY)
   - 부서이동자는 HR(Tibero) 한 곳만 접속: `TIBERO_DSN=10.100.1.130:8629/DXHR`, `TIBERO_USER`, `TIBERO_PASSWORD`
     (옛 ORACLE_* · BPM_ORACLE_* 항목은 없어짐. 조달구매·PMS 는 Tibero 의 DB 링크 @DXHRT_BPMT1 로 조회)
   - Tibero JDBC 드라이버 `lib/tibero7-jdbc.jar` 를 함께 올리고, 서버에 Java(JRE 8 이상)가 있어야 함 (`java -version`).
     java 가 PATH 에 없으면 `.env` 의 `JAVA_HOME` 에 경로를 적음. Oracle Instant Client 는 더 이상 필요 없음
   - 부서이동자 일간 메일(매일 08:40, 대상이 없어도 빈 목록으로 발송): `SMTP_HOST=203.241.0.125`, `SMTP_PORT=25`,
     `SMTP_HELO=kmdev.poscodx.com`, `MAIL_FROM=pe912821@poscodx.com`, 받는 사람 `DEPART_DAILY_MAIL_TO`(쉼표로 여러 명), `APP_BASE_URL`(메일 속 화면 링크)
   - `SECRET_KEY` 를 옛 값 그대로 쓰면 사용자들이 다시 로그인하지 않아도 됨
   - `SCHEDULER_ENABLED=true`, `LOG_DIR=/data/mtmon/logs`, `APP_ENV=prod`
   - 권한: `chmod 600 .env`
7. **스키마 소유자 확인** — 0002(스키마 이름 변경)는 스키마 소유자만 할 수 있음
   ```
   psql ... -c "\dn"
   ```
   `program_change`, `dept_transfer`, `auth` 의 Owner 가 `.env` 의 DATABASE_URL 계정과 같아야 함.
   다르면: 소유자 계정으로 `python -m alembic upgrade head` 를 한 번 직접 실행
8. **앱 시작** `sudo systemctl start mtmon` → A-4 처럼 로그 확인 (`적용 완료 (버전 0008)`)
9. **화면 확인** — 대시보드 · 프로그램변경 · 부서이동자 · DML · DDL · 배치 · 계정관리
   - 옛 주소(`/program-change`, `/dept-transfer`, `/admin/users`)는 새 주소로 자동 이동
10. **DB 이름 변경(month_mon → mtmon)은 나중에 별도로** — 바꾼 뒤 `.env` 의 DATABASE_URL 만 수정하고 재시작

**되돌리기(문제 시)**: 앱 중지 → 1번 백업으로 복원(`pg_restore`) → 옛 소스로 교체 → crontab 복구 → 시작

---

## E. 배치 · 로그

* **배치** — 앱 안에서 실행 (cron 없음)
  - 잡 목록·일정: `batch/jobs.py` / 실행 이력·에러 원인: 화면 `/batch` (운영자는 여기서 수동 실행)
  - 자동 실행 끄기: `.env` 의 `SCHEDULER_ENABLED=false`
  - 수동 실행은 앱의 '배치관리' 화면에서만 (배치관리 수정 권한 필요). 명령줄 실행 기능은 없음
* **로그** — `LOG_DIR` (운영 `/data/mtmon/logs`), 파일명에 날짜
  | 폴더 | 내용 | 보관 |
  |---|---|---|
  | app/ | 앱 동작 | 31일 |
  | error/ | 에러만 모음 | 183일 |
  | access/ | 모든 요청 | 365일 |
  | audit/ | 사용자 작업 (누가·무엇을·결과) | 365일 |
  | batch/ | 배치 실행 | 183일 |
  - 보관 기간이 지나면 '로그 정리' 배치(매일 00:30)가 삭제

---
# (이전 문서)

필요사항

1. 패키지 다운로드(개발서버)
실행환경 : 개발용 PC 윈도우에서 실행
특이사항 : 프로젝트 루트에 wheelhouse/ 경로생김. 폐쇄망은 pip install을 통해 외부에서 라이브러리 설치를 못하므로 그 라이브러리들을 미리 인터넷망에서 다운로드하여 폐쇄망에 옮기기 위한 폴더라고 보면됨.

## 0) 깨끗하게 시작
Remove-Item -Recurse -Force wheelhouse -ErrorAction SilentlyContinue

## 1) 문제 패키지(환경 마커 복잡) 개별 다운로드
py -m pip download uvloop httptools websockets watchfiles greenlet -d wheelhouse --only-binary=:all: --platform manylinux_2_17_x86_64 --python-version 3.11 --implementation cp --abi cp311 --no-deps

## 2) JPype1 단독 다운로드 (플랫폼 태그 여러 개 지정) — Tibero JDBC 호출용 (oracledb 는 더 이상 안 씀)
py -m pip download "JPype1==1.5.2" -d wheelhouse --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --python-version 3.11 --implementation cp --abi cp311 --no-deps

## 3) 메인 다운로드 (의존성 정상 해결)
py -m pip download -r requirements.txt -d wheelhouse --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --python-version 3.11 --implementation cp --abi cp311

## 개발서버(Window)에서 라이브러리를 wheelhouse에 담기 명령어이다. -> wheelhouse/ 경로가 생기면 그걸 나중에 배포서버에서 venv로 설치해야함.

2. 리눅스 배포(운영서버)
실행환경 : 배포용 리눅스 서버에서 실행

[venv 설치 및 활성화]
python3.11 -m venv venv
source venv/bin/activate
deactivate

[프로젝트 루트에서 패키지 설치]
(venv) $ pip install --no-index --find-links=./wheelhouse -r requirements.txt

[오라클 다운로드 및 업로드]
Instant Client 리눅스버전 zip (Oracle 사이트)
/opt/oracle/instantclient_…  ← Instant Client 압축 푼 것

[개발한 소스코드]
앱 소스 (압축)
* 압축할 때 빼야 할 것: __pycache__/, .git/, venv/, 그리고 비밀번호 든 .env(있으면).
* 반드시 포함: templates/, static/ (이건 앱의 일부라 빠지면 화면 깨짐).

서버구조
/opt/mtmon/
├── (나머지 소스코드)
└── venv/                  ← 가상환경

[libaio설치(선택)]
rpm -qa | grep libaio (확인)
yum install libaio (없는 경우)

3. 
# 1. Instant Client 경로를 등록 파일로 만들기
echo "/opt/oracle/instantclient_23_26" | sudo tee /etc/ld.so.conf.d/oracle-instantclient.conf

# 2. 캐시 갱신
sudo ldconfig

# 3. 확인 — 이게 나오면 성공
ldconfig -p | grep clntsh

4. 실행 및 관리
실행 명령어 : (venv) $ nohup venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 &
(원래 main.py에서 이것을 실행한다. reload를 적지 않으면 기본 false
uvicorn main:app --host 0.0.0.0 --port 8000 --reload # 켜야 할 때만 명시
reload는 소스 수정 시 자동 재기동되는데 개발계에서 주로 사용하고 운영계에선 사용안함.
workers 설정
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
보통 2~4정도면 충분
)
[crontab 등록]
10 3 1 * * cd /opt/mtmon && /opt/mtmon/venv/bin/python -m scripts.load_program_change >> /data/mtmon/logs/pcl_batch-$(date + \%Y\%m).log 2>&1

5. 배포서버 환경
로그파일 경로 : /data/mtmon/logs
상세로그파일 : /data/mtmon/logs/access app batch error
로그보관주기 : access(1년) app(1개월) batch(6개월) error(6개월)
크론탭 설정 : 
10 8 * * *  cd /opt/mtmon && /opt/mtmon/venv/bin/python -m scripts.load_daily_dept_transfer >> /data/mtmon/logs/dept_transfer_daily-$(date +\%Y\%m\%d).log 2>&1
10 3 1 * * cd /opt/mtmon && /opt/mtmon/venv/bin/python -m scripts.load_program_change >> /data/mtmon/logs/pcl_batch-$(date + \%Y\%m).log 2>&1

시스템데몬 등록
/etc/systemd/system/mtmon.service

[Unit]
Description=My FastAPI Application
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/mtmon
Environment="PATH=/opt/mtmon/venv/bin"
ExecStart=/opt/mtmon/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/data/mtmon/logs/systemd/app.log
StandardError=append:/data/mtmon/logs/systemd/error.log

[Install]
WantedBy=multi-user.target


sudo systemctl daemon-reload
sudo systemctl enable myapp        # 부팅 시 자동 시작
sudo systemctl start myapp         # 시작
sudo systemctl stop myapp          # 중지
sudo systemctl restart myapp       # 재시작
sudo systemctl status myapp        # 상태 확인
journalctl -u myapp -f             # 실시간 로그