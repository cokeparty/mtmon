"""
HR(Tibero) DB 조회 — JDBC(tibero7-jdbc.jar) 를 JPype 로 호출한다.

부서이동자 일간·월간 쿼리는 모두 이 DB 하나에만 접속한다.
조달구매(epro) · PMS(proj) 테이블은 Tibero 의 DB 링크(@DXHRT_BPMT1)로 조회한다.

  * 서버에 Java(JRE 8 이상)가 있어야 한다. java 가 PATH 에 없으면 .env 의 JAVA_HOME 을 적는다.
  * 모든 값은 문자열(getString)로 받는다 — 날짜는 수집기에서 date 로 바꾼다.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

from config import settings

_DRIVER = "com.tmax.tibero.jdbc.TbDriver"
_ROOT = Path(__file__).resolve().parents[2]
_jvm_lock = threading.Lock()


def _jar_path() -> str:
    p = Path(settings.TIBERO_JDBC_JAR)
    if not p.is_absolute():
        p = _ROOT / p
    if not p.is_file():
        raise RuntimeError(f"Tibero JDBC 드라이버 파일이 없습니다: {p}")
    return str(p)


def _ensure_jvm():
    import jpype
    with _jvm_lock:
        if jpype.isJVMStarted():
            return jpype
        if settings.JAVA_HOME:
            os.environ["JAVA_HOME"] = settings.JAVA_HOME
        jpype.startJVM(classpath=[_jar_path()], convertStrings=True)
        jpype.JClass(_DRIVER)          # 드라이버 등록
        return jpype


def _url() -> str:
    """TIBERO_DSN 형식: host:port/DB이름 → jdbc:tibero:thin:@host:port:DB이름"""
    if not settings.TIBERO_DSN:
        raise RuntimeError("TIBERO_DSN 이 .env 에 설정되지 않았습니다.")
    host_port, dbname = settings.TIBERO_DSN.rsplit("/", 1)
    return f"jdbc:tibero:thin:@{host_port}:{dbname}"


def query(sql: str) -> list[dict]:
    """SELECT 실행 → [{소문자 칼럼명: 문자열|None}, ...]"""
    jpype = _ensure_jvm()
    DriverManager = jpype.JClass("java.sql.DriverManager")
    DriverManager.setLoginTimeout(10)
    conn = DriverManager.getConnection(_url(), settings.TIBERO_USER, settings.TIBERO_PASSWORD)
    try:
        conn.setReadOnly(True)
        stmt = conn.createStatement()
        try:
            rs = stmt.executeQuery(sql)
            meta = rs.getMetaData()
            cols = [str(meta.getColumnLabel(i)).lower() for i in range(1, meta.getColumnCount() + 1)]
            rows: list[dict] = []
            while rs.next():
                rows.append({c: (None if (v := rs.getString(i)) is None else str(v))
                             for i, c in enumerate(cols, start=1)})
            return rows
        finally:
            stmt.close()
    finally:
        conn.close()
