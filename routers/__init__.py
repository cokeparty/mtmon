"""
라우터 패키지 (주소 · 화면)
- auth          로그인 · 회원가입 · 비밀번호 변경
- dashboard     /dashboard  메인 대시보드
- program       /program    프로그램변경 모니터링
- depart        /depart     부서이동자 권한 정리 (월간 · 일간)
- dml_manager   /dml/manager    DML 담당자 뷰 (CSV 업로드, 진행률)
- dml_developer /dml/developer  DML 개발자 뷰 (본인 그룹 SR 입력)
- ddl           /ddl        DDL 모니터링
- account       /account    계정관리 (운영자)
- batch         /batch      배치잡 목록 · 실행 이력

화면 렌더링 · 기본 회차 · DB 장애 응답은 core/web.py 공통 함수를 쓴다.
"""
