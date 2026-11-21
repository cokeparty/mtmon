# test_db_connection.py
import sys
import os

# 프로젝트 루트 경로를 Python Path에 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import create_engine, text
from config import settings


def mask_url(url: str) -> str:
    """URL에서 비밀번호 부분만 마스킹 처리"""
    if not url:
        return "(설정되지 않음)"
    if "@" in url and ":" in url.split("@")[0]:
        try:
            left, right = url.split("@", 1)
            schema_user, pwd = left.rsplit(":", 1)
            return f"{schema_user}:******@{right}"
        except ValueError:
            return "******"
    return url


def test_connection(name: str, db_url: str):
    print("\n" + "=" * 60)
    print(f" {name} 연결 테스트")
    print("=" * 60)

    # 1. URL 설정 여부 확인
    if not db_url:
        print(f"⏭️  [건너뜀] {name}의 URL이 설정되어 있지 않습니다 (빈 값).")
        return

    print(f"▶ 접속 URL: {mask_url(db_url)}")

    try:
        # 2. 임시 엔진 생성 (타임아웃 5초 설정)
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5}  # psycopg2 타임아웃
        )

        # 3. 실제 연결 및 쿼리 실행
        with engine.connect() as conn:
            # DB 버전 정보를 가져와서 연결 확인
            version = conn.execute(text("SELECT version();")).fetchone()
            print(f"\n✅ [성공] {name} 연결 및 쿼리 실행 완료!")
            print(f"   - DB 버전: {str(version[0])[:60]}...")

        engine.dispose()  # 테스트용 커넥션 정리

    except Exception as e:
        print(f"\n❌ [실패] {name} 연결 중 에러가 발생했습니다.")
        print(f"   - 에러 유형: {type(e).__name__}")
        print(f"   - 에러 내용: {str(e)[:200]}")  # 에러 너무 길면 잘라서 표시
        print("\n💡 조치 가이드:")
        print("   1. config.py 또는 .env 파일의 URL(IP, 포트, 계정, 비번)을 확인하세요.")
        print("   2. DB 서버 기동 상태 및 방화벽(접근 IP 허용) 여부를 확인하세요.")


if __name__ == "__main__":
    print("🔍 사내 IT 통합 모니터링 시스템 - DB 연결성 검증 도구")

    # 1. 메인 DB 테스트 (필수)
    test_connection("[1] 메인 DB (month_mon)", settings.DATABASE_URL)

    # 2. 외부 SR DB 테스트 (필수)
    test_connection("[2] 외부 SR DB", settings.SR_DB_URL)

    print("\n" + "=" * 60)
    print(" 검증 프로세스 종료")
    print("=" * 60)
    print("※ 참고: 명세서상 결재(APPROVAL) DB는 폐기되었으므로 테스트하지 않습니다.")
