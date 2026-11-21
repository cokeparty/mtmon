필요사항

1. 패키지 다운로드(개발서버)
실행환경 : 개발용 PC 윈도우에서 실행
특이사항 : 프로젝트 루트에 wheelhouse/ 경로생김. 폐쇄망은 pip install을 통해 외부에서 라이브러리 설치를 못하므로 그 라이브러리들을 미리 인터넷망에서 다운로드하여 폐쇄망에 옮기기 위한 폴더라고 보면됨.

## 0) 깨끗하게 시작
Remove-Item -Recurse -Force wheelhouse -ErrorAction SilentlyContinue

## 1) 문제 패키지(환경 마커 복잡) 개별 다운로드
py -m pip download uvloop httptools websockets watchfiles greenlet -d wheelhouse --only-binary=:all: --platform manylinux_2_17_x86_64 --python-version 3.11 --implementation cp --abi cp311 --no-deps

## 2) oracledb 단독 다운로드 (플랫폼 태그 여러 개 지정)
py -m pip download oracledb -d wheelhouse --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --python-version 3.11 --implementation cp --abi cp311 --no-deps

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
(venv) $ pip install --no-index --find-links=./wheelhouse -r requirements.txt oracledb

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