모니터링 웹 시스템 개발 명세서
읽기 전 확정 사항 (재문의 불필요)

결재(승인) 프로세스 없음 — 결재 DB·컬럼·판정 전부 제외
SR번호 획득 방식 — NFS 서버의 SR번호_SR내용 폴더 파일을 로그 basename과 매핑해서 획득 (로그 경로 정규식 아님)
수기 → 웹 전환 목적 — 기존 수기는 ... | wc로 건수만 셌음. 웹은 wc를 떼고 라인 전체를 파싱해 상세 리스트로 적재
출력 양식 — 수기 결과지 17컬럼 그대로 유지. 단 결재 3컬럼은 빈칸 출력(양식 호환용)
정상여부 판정 — 일반 / 긴급변경 / SR없음 / 매핑충돌(경고) 4갈래. 결재누락 판정 없음
5개 영역의 사내 IT 모니터링을 통합한 웹 시스템. 담당자가 월별로 회차를 마감 처리하고, 일부 모듈은 개발자가 직접 SR번호를 입력한다.

1. 프로그램 개요
1.1 목적
사내 IT 운영 통제 항목(프로그램 변경 / 부서이동자 / DML / DDL / 보안접근로그)을 월별 회차 단위로 수집·검증·기록한다. 외부에서 자동 수집한 로그(SFTP xferlog, DBSAFER CSV, OS 로그)를 적재하고, SR 번호와 매핑하여 정상/이상 여부를 판정한다. 담당자/개발자 권한을 분리하여 입력·검토·마감을 수행한다.

1.2 모니터링 5종 요약
#	모니터링	데이터 소스	개발자 입력	핵심 로직
1	프로그램 변경	SFTP xferlog + NFS 서버(SR 폴더) + 외부 SR DB	❌	xferlog 파싱 → NFS 폴더 basename 매핑으로 SR번호 획득 → SR DB 조회 → 정상여부 판정
2	부서이동자	HR/권한 DB	❌	담당자가 유지/회수, SR번호 외부 검증
3	DML	DBSAFER CSV	✅	그루핑 후 개발자가 SR 일괄 입력
4	DDL	DBSAFER CSV	❌	자동 적재·조회만
5	보안접근로그	OS 로그 CSV (크론 자동)	❌	단순 적재·조회
⚠️ DML과 DDL은 데이터 소스는 비슷하지만 처리 방식이 완전히 다르다.

DML: 개발자가 본인 그룹 SR번호 직접 입력 → 2개 뷰(담당자/개발자)
DDL: 담당자 업로드만 → 1개 뷰(담당자)
1.3 사용자 권한
역할	가능 작업
담당자(manager)	모든 모니터링 조회/입력/엑셀, CSV 업로드, SFTP 로그 수집 실행, 회차 마감
개발자(developer)	DML 본인 담당 그룹의 SR 번호 입력만. 다른 화면 접근 불가
2. 화면 구성
2.1 네비게이션
대시보드 | 프로그램 변경 | 부서이동자 | DML | DDL | 보안접근로그 ※ 개발자 로그인 시 DML 메뉴만 표시.

2.2 화면 목록
#	화면	URL	권한
1	로그인	/login	공개
2	대시보드	/dashboard	담당자
3	프로그램 변경	/program-change	담당자
4	부서이동자	/dept-transfer	담당자
5	DML 담당자 뷰	/dml/manager	담당자
6	DML 개발자 뷰	/dml/developer	개발자
7	DDL	/ddl	담당자
8	보안접근로그	/security-log	담당자
2.3 화면별 상세
① 대시보드 (/dashboard)

월 선택 + 전체 엑셀 일괄 출력
5개 카드(프로그램 변경 / 부서이동자 / DML / DDL / 보안접근로그): 각 카드에 총 건수·이상 건수·미처리 건수, 클릭 시 상세 이동
시스템별 현황(HR/조달구매/SR/PMS), 최근 이상 감지 N건
② 프로그램 변경 (/program-change)

시스템 탭(HR/조달구매/SR/PMS)
버튼: [SFTP 로그 수집] [엑셀]
필터: 소스파일명/SR번호 검색 + 결과(전체/정상/SR없음/경고/이상)
출력 17컬럼 (수기 결과지 그대로): 월 / 일 / 시간 / 소스파일명 / SR번호 / SR제목 / 작업구분 / 작업승인일 / SR종료일 / 프로그램 변경요청·승인 / 사용자테스트 / 이관전 승인 / 개발자 / 이관자 / 검토수행자 / 모니터링결과 / 정상여부
굵게 표시한 결재 3컬럼은 승인 프로세스가 없으므로 항상 빈칸 출력(양식 호환 목적)
이상 행 강조, 비고 입력 가능
푸터: 마지막 수집 시각, 실행한 수집 명령어 표시 (기존 수기의 끝 | wc는 제거하고 라인 전체를 파싱·적재)
③ 부서이동자 (/dept-transfer)

시스템 탭, [이동자 조회] [엑셀]
테이블: 이동자·이전부서→신규·앱/권한·역할·처리(유지/회수)·SR번호·상태
SR번호 입력 시 외부 SR DB 유효성 검증
④ DML 담당자 뷰 (/dml/manager)

시스템 탭, [CSV 업로드] [자동매핑 실행] [엑셀]
진행률 바, 개발자별 처리 현황 테이블
⑤ DML 개발자 뷰 (/dml/developer)

본인 담당 그룹만 표시
시스템 탭, 그룹 카드(헤더 + SR번호 입력 + Enter → 일괄 적용)
그룹 정의: 요청시각 200초 간격 + 동일 db_user + conn_account + target_table
⑥ DDL (/ddl)

시스템 탭, [CSV 업로드] [엑셀]
테이블: 일시·db_user·conn_account·target_object·DDL종류·쿼리요약
DROP/TRUNCATE 등 이상 패턴 강조
⑦ 보안접근로그 (/security-log)

월 선택 + 엑셀
KPI: 전체 / 야간(22~06) / 실패로그인 / 소스 4종
필터: 소스(message/last/lastlog/secure)·시간대·계정명
3. 데이터 모델 (개념)
모든 트랜잭션 테이블은 period_id(월 회차 FK) 를 갖는다.

3.1 공통/마스터
user: 사용자(로그인ID, 이름, 이메일, 역할 manager/developer, 활성여부)
monitoring_period: 월 회차(year_month 예 '2026-04', 상태 open/closed, 마감시각·마감자)
server_config: 시스템별(HR/EPRO/SR/PMS) 설정
A 서버 (xferlog 로그서버): SSH 접속정보, 로그 디렉토리(예 /data/sftp_log_backup), 로그 패턴(예 *{ym}*), 포함 경로(예 /tomcat8/webapps/ROOT), 포함 플래그(예 _ i)
B 서버 (NFS, SR번호 폴더): NFS SSH 접속정보, 베이스 디렉토리(하위 구조: 업무명/SR번호_SR내용/.../파일)
3.2 프로그램 변경 (program_change_log)
하나의 행에 다음 4단계 정보를 담는다.

① SFTP xferlog 원본: 월, 일, 시간, 합산 배포시각(deploy_time, 정렬/조회/충돌해소 기준), 소스파일명(basename = 매핑 키), 전체경로, 이관자(deployer)
② NFS 매핑 결과: 매핑된 NFS 파일 경로, NFS mtime(충돌해소 근거), map_type(single/time-resolved/none/conflict)
③ 외부 SR DB 스냅샷: SR번호, SR제목, 작업구분(데이터변경/시스템개선/긴급변경 등), 작업승인일, SR종료일, 개발자, 검토수행자
④ 시스템 판정(결재 컬럼 없음): 모니터링결과(result), 정상여부(normal_yn), 판정 사유(reason), 담당자 비고(remark)
정상여부 판정 규칙 (결재 누락 판정 없음)

분기	조건	판정
SR번호 없음	NFS 매핑 실패(map_type='none')	이상 (SR없음)
매핑 충돌	동일 basename 다수 + 전송시각 이전 파일 없음(map_type='conflict')	경고 (검토필요) — result='경고', normal_yn='이상'
일반 SR	작업구분 ≠ 긴급변경 / 배포일 ≥ 승인일	정상
일반 SR	배포일 < 승인일	이상 (사전배포)
긴급변경	종료일 ≤ 배포일 + 5일	정상
긴급변경	그 외	이상 (사후승인기한초과)
모니터링결과 vs 정상여부

result(모니터링결과): 정상 / SR없음 / 경고 / 이상 — 운영 모니터링 표시용
normal_yn(정상여부): 정상 / 이상 — 감사 보고서용 최종 판정
정상여부='이상' 또는 result='경고'인 행은 reason을 반드시 채운다.

3.3 부서이동자 (dept_transfer)
이동자, 이전부서, 신규부서, 앱명, 권한(역할)명
처리(action): 유지 / 회수 / 선택
SR번호(선택), 상태(미처리 / 완료)
3.4 DML (개발자 입력 필요)
dml_log: 요청시각, db_user, conn_account, target_table, 쿼리요약, 그룹 FK, SR번호(개발자 입력), 상태(미입력 / 적용됨)
dml_group: 기준시각, db_user, conn_account, target_table, 담당 개발자 FK, 행 건수, SR번호, 상태(미입력 / 적용됨)
3.5 DDL (개발자 입력 없음)
ddl_log: 요청시각, db_user, conn_account, target_object, DDL종류(CREATE/ALTER/DROP/TRUNCATE/RENAME), 쿼리요약, 이상여부(DROP/TRUNCATE 자동 표시)
※ DDL은 group, sr_no, developer_id, status 컬럼 없음. 단순 적재/조회용.
3.6 보안접근로그 (security_access_log)
이벤트시각, 소스(message/last/lastlog/secure), 계정, 출발 IP, 이벤트 설명, DBSAFER 서버
야간여부(22:00~06:00), 실패로그인 여부
4. 백엔드 모듈 구조 (FastAPI)
4.1 라우터
라우터	경로	권한
auth	/login, /logout	공개
dashboard	/dashboard	담당자
program_change	/program-change	담당자
dept_transfer	/dept-transfer	담당자
dml_manager	/dml/manager	담당자
dml_developer	/dml/developer	개발자
ddl	/ddl	담당자
security_log	/security-log	담당자
4.2 서비스
서비스	주요 역할
auth_service	로그인, 세션, 역할 검증
period_service	월 회차 CRUD, 마감
server_config_service	시스템별 A서버 SSH/로그 + B서버 NFS 설정 관리
sftp_log_collector	A서버 SSH 접속 → 로그 추출 명령 실행 → xferlog 라인 파싱 (wc 제거)
nfs_scanner	B서버(NFS) SSH 접속 → 업무명/SR번호_SR내용/ 트리 스캔(폴더 제외, 하위 파일 전부) → basename 인덱스 생성
sr_mapper	로그 basename ↔ NFS 인덱스 매핑. 충돌 시 mtime ≤ 전송시각 중 최근접 SR 선택
sr_db_client	외부 SR DB(PostgreSQL) 조회(제목·작업구분·승인일·종료일·개발자·검토자)
pcl_judger	정상여부 판정(일반/긴급변경/SR없음/매핑충돌). 결재 판정 없음
dept_transfer_service	HR/권한 DB 조회, SR 검증
dml_service	CSV 업로드, 그루핑, 자동매핑, 진행률 집계
ddl_service	CSV 업로드, 적재, 이상 패턴 표시
security_log_loader	크론 CSV 파싱·적재
excel_exporter	모듈별 엑셀 출력(조건부 서식)
⚠️ DML과 DDL은 별개 서비스. 공통 베이스 두지 말 것. ⚠️ 결재 DB 연동(approval_db_client) 없음. NFS 스캔(nfs_scanner)·매핑(sr_mapper)이 그 자리를 대신한다.

4.3 핵심 알고리즘
4.3.1 프로그램 변경 (SFTP xferlog → NFS 매핑 → SR DB → 판정)

배경 흐름:

개발자 → NFS(B)의 업무명/SR번호_SR내용/에 파일 배치
이관자 → NFS(B) 파일을 대상 서버로 업로드(이관)
이관 전송 로그 → 서버 A(/data/sftp_log_backup)에 xferlog로 남음
모니터링 → A에서 이관 로그 추출, B의 SR번호 폴더로 basename 매핑
처리 단계:

A서버 SSH 접속 → 원격 명령 실행 (sftp_log_collector): 로그 디렉토리에서 회차 패턴 파일을 추출하되, 기존 수기의 끝 | wc(건수만)는 제거하고 라인 전체를 수집
xferlog 라인 파싱: 월/일/시간  → 합산 배포시각, 전체경로 → basename(매핑 키), 이관자 추출
NFS 인덱스 생성 (nfs_scanner): B서버 베이스 디렉토리 하위 전체 트리 스캔. 폴더는 무시하고 파일만 대상(하위 폴더 파일 전부 포함), 상위 SR번호_SR내용 폴더명에서 SR번호 추출 → {basename: [(sr_no, nfs_path, mtime)…]} 인덱스
basename 매핑 (sr_mapper):
후보 0건 → SR번호 없음, map_type='none'
후보 1건 → 채택, map_type='single'
후보 N건(충돌) → mtime ≤ 전송시각 중 가장 근접(최신) 채택, map_type='time-resolved'. 전송시각 이전 파일이 없으면 SR번호 없음, map_type='conflict'
외부 SR DB 조회 (sr_db_client): 매핑된 SR번호로 메타 조회 → 스냅샷 저장
판정 (pcl_judger): none → 이상(SR없음), conflict → 경고, 일반(사전배포 시 이상), 긴급변경(+5일 초과 시 이상), 그 외 정상
program_change_log INSERT
4.3.2 DML 그루핑 (sr_ext)

period_id, system_code 범위 내 dml_log를 요청시각 오름차순 정렬
순회하며 4조건 모두 만족 시 동일 그룹 판정:
직전 행과 요청시각 간격 ≤ 200초
db_user 동일
conn_account 동일
target_table 동일
조건이 깨지면 새 그룹 생성 → dml_group INSERT
각 dml_log의 그룹 FK 갱신
그룹 담당 개발자는 db_user → 개발자 매핑표로 결정. 매핑 없으면 담당자 뷰에서 수동 배정
4.3.3 DML 자동매핑 (sr_enrich)

개발자가 그룹 카드에 입력한 SR번호를 dml_group에 저장
같은 그룹의 모든 dml_log에 일괄 전파(Enter 시 batch update)
SR번호 외부 SR DB 유효성 검증(존재/상태) → 무효면 경고
그룹·로그 상태='적용됨' 전환, 진행률 재집계
4.3.4 DDL 이상 패턴

DDL종류가 DROP / TRUNCATE → 이상
target_object가 핵심 테이블 목록 매칭 → 이상
그 외 → 정상
※ DDL은 판정/SR입력 없음. 적재 + 표시만.
5. 파일 구조 (개요)
app/: main, config, database
models/: user, period, server_config, program_change(17컬럼·결재 컬럼 없음), dept_transfer, dml(log+group), ddl, security_log
routers/: auth, dashboard, program_change, dept_transfer, dml_manager, dml_developer, ddl, security_log
services/:
sftp_log_collector (A서버 SSH + xferlog 파싱, wc 제거)
nfs_scanner (B서버 NFS SR폴더 스캔 → basename 인덱스)
sr_mapper (basename 매핑 + mtime 충돌해소)
sr_db_client (외부 SR DB)
pcl_judger (일반/긴급변경/SR없음/충돌, 결재 판정 없음)
dml_service (그루핑 + 자동매핑), ddl_service (적재 + 이상표시, 별개 서비스)
auth/period/server_config/dept_transfer/security_log_loader/excel_exporter
templates/: base, login, dashboard, program_change(17컬럼·결재 3칸 빈칸), dept_transfer, dml_manager, dml_developer, ddl, security_log
static/: css/js
scripts/: load_security_log (크론 OS 로그 CSV 적재)
※ approval_db_client 없음(폐기). nfs_scanner + sr_mapper가 SR 획득을 담당.

6. 처리 흐름 요약
프로그램 변경 담당자 [SFTP 로그 수집] → A서버 SSH·로그 추출(wc 제거)·라인 파싱 → NFS 스캔(basename 인덱스) → basename 매핑(충돌 시 mtime ≤ 전송시각 최근접) → SR 메타 스냅샷 → 정상여부 판정 → program_change_log INSERT → 화면 17컬럼 테이블(결재 3칸 빈칸), 이상/경고 강조

DML

담당자 CSV 업로드 → dml_log 적재
담당자 [자동매핑 실행] → 그루핑(dml_group 생성)
개발자 로그인 → 본인 그룹 카드에 SR번호 입력(Enter) → 그룹 일괄 전파 + 검증
담당자 진행률 모니터링 → 회차 마감 → 엑셀
DDL / 부서이동자 / 보안접근로그

DDL: 담당자 CSV 업로드 → 적재 + 이상표시 → 조회/엑셀 (SR입력·판정 없음)
부서이동자: 이동자 조회 → 유지/회수 + SR 입력/검증 → 엑셀
보안접근로그: 크론 자동 적재 → KPI/필터 조회 → 엑셀
7. 외부 연동 정리
연동 대상	용도	방식	사용 모듈
로그서버 A (/data/sftp_log_backup)	SFTP xferlog 수집	SSH (paramiko)	프로그램 변경
NFS 서버 B (SR번호_SR내용 폴더)	basename		

8. 비기능 요구사항
인증/권한: 세션 기반, 라우터별 role 가드. 개발자는 DML 외 접근 차단.
회차 잠금: 마감(closed) 회차는 입력/수집/업로드 불가(조회·엑셀만).
SSH 보안: 키 파일 경로는 server_config에 보관, 비밀번호 평문 금지. paramiko AutoAddPolicy는 운영 환경 검토.
명령 인젝션 방지: log_pattern / include_path 등 설정값은 안전하게 이스케이프 처리(shlex.quote).
감사 로그: 수집 실행·CSV 업로드·SR 입력·마감 행위 기록.
엑셀: 이상=빨강, 경고=주황 조건부 서식. 결재 3컬럼은 헤더만 두고 빈칸.
9. 주요 결정 이력 (재문의 불필요)
항목	확정 내용	근거
결재 프로세스	없음 (DB·컬럼·판정 전부 제외)	운영상 승인 시스템 미연동
SR번호 획득	NFS SR번호_SR내용 폴더 ↔ 로그 basename 매핑	로그 경로엔 SR번호 없음
매핑 충돌	mtime ≤ 전송시각 중 최근접 SR 채택, 없으면 경고	직전 배치 파일이 실제 이관본
wc 의미	기존 수기 = 건수만 카운트. 웹은 wc 제거, 라인 전체 파싱	상세 리스트화가 본 작업 목적
출력 컬럼	17컬럼 양식 유지, 결재 3칸은 빈칸 출력	수기 결과지 호환
판정 갈래	정상/SR없음/경고/이상 (결재누락 없음)	결재 제거에 따른 단순화
DML vs DDL	별개 서비스·뷰 (공통 베이스 금지)	처리 방식 상이
정리하며 — 리팩토링 시 적용한 원칙
코드/스키마 DDL 전부 제거 → 표·불릿 기반 개념 설명으로 치환 (테이블별 핵심 컬럼만 자연어로 요약)
중복 블록 삭제 — 3.2의 program_change_log 정의가 원문에서 ②③④ 영역이 두 번 반복되어 있었는데 1회로 통합
판정 규칙을 표로 변환 — 분기/조건/판정을 한눈에 보이도록 정리
명령어 라인은 "명령 실행" 같은 서술로 대체해 의미만 보존
확정 사항·결정 이력 등 "되묻지 말 것" 항목은 그대로 유지(누락 시 재문의 유발 위험)