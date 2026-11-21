# services/ddl_parser.py
"""
DDL 로그 파싱 / SR 추출·전파 엔진

DML 파서(dml_parser.py)와 동일한 SR 추출·전파 로직을 사용하되
DDL 전용 처리 추가:
  - ddl_type 자동 감지 (CREATE/ALTER/DROP/TRUNCATE/RENAME)
  - target_object 컬럼 (테이블명 대신 오브젝트명)
  - 그룹화 없이 행 단위로 결과 반환

[수정] target_object 를 CSV 필수 컬럼에서 제외하고 command(SQL)에서 파싱
       → CSV에 오브젝트 컬럼이 없어도 업로드 가능
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

import pandas as pd

from services.common import csv_read

# ──────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────
TIME_WINDOW_SEC = 200
GROUP_KEYS      = ["user_name", "account", "target_object"]   # DDL 전용 키

# SR 패턴 (dml_parser 동일)
SR_COMMENT_RE = re.compile(r"/\*.*?([A-Za-z]\d{2}-\d{8}-\d{3}).*?\*/", re.DOTALL)

# DDL 타입 감지
# - /* block comment */ 와 -- line comment 모두 건너뜀
# - CREATE OR REPLACE 는 CREATE 로 분류
DDL_TYPE_RE = re.compile(
    r"^\s*"
    r"(?:"
        r"/\*.*?\*/\s*"           # /* block comment */
        r"|--[^\r\n]*[\r\n\s]*"   # -- line comment
    r")*"
    r"(CREATE|ALTER|DROP|TRUNCATE|RENAME)\b",
    re.IGNORECASE | re.DOTALL,
)

# [수정] DDL 명령어에서 대상 오브젝트명 추출용 정규식
#   CREATE TABLE t / ALTER TABLE t / DROP TABLE t / TRUNCATE TABLE t /
#   CREATE INDEX i / DROP VIEW v / RENAME ... TO t 등 대응
#   - 선행 /* SR */ 주석은 DDL_TYPE_RE와 별개로 here에서도 건너뜀
OBJECT_RE = re.compile(
    r"^\s*(?:/\*.*?\*/\s*)*"
    r"(?:CREATE|ALTER|DROP|TRUNCATE|RENAME)\s+"
    r"(?:GLOBAL\s+|TEMPORARY\s+|TEMP\s+|OR\s+REPLACE\s+|PUBLIC\s+|UNIQUE\s+|BITMAP\s+)*"
    r"(?:TABLE|VIEW|INDEX|SEQUENCE|SYNONYM|TRIGGER|PROCEDURE|FUNCTION|PACKAGE|"
    r"MATERIALIZED\s+VIEW|TYPE|USER|ROLE|DATABASE|SCHEMA|CLUSTER)?\s+"
    r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
    r'["`\[]?([A-Za-z0-9_$#]+(?:\.[A-Za-z0-9_$#]+)?)',
    re.IGNORECASE | re.DOTALL,
)

COLUMN_ALIASES = {
    "사용자명":       "user_name",
    "접속계정":       "account",
    "접속계정명":     "account",
    "대상오브젝트":   "target_object",
    "대상객체":       "target_object",
    "테이블명":       "target_object",
    "대상테이블":     "target_object",
    "요청시각":       "req_time",
    "요청 시각":      "req_time",
    "수행시각":       "req_time",
    "수행시간":       "req_time",
    "실행구문":       "command",
    "명령어":         "command",
    "쿼리":           "command",
    "SQL":            "command",
}

REASON_NO_OBJECT     = "NO_OBJECT"
REASON_NO_DONOR      = "NO_DONOR"
REASON_OUT_OF_WINDOW = "OUT_OF_WINDOW"
REASON_SKIP_NAT      = "SKIP_NAT"


# ──────────────────────────────────────────────────────────────
# 결과 컨테이너
# ──────────────────────────────────────────────────────────────
@dataclass
class DdlParseResult:
    rows:  pd.DataFrame
    stats: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────
def clean_cmd(s) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = s.replace("♪", " ").replace("\x00", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def detect_ddl_type(cmd: str) -> Optional[str]:
    if not cmd:
        return None
    m = DDL_TYPE_RE.match(cmd)
    return m.group(1).upper() if m else None


# [수정] 명령어(SQL)에서 대상 오브젝트명 추출
def extract_object(cmd: str) -> str:
    """
    command(DDL 원문)에서 대상 오브젝트명을 추출한다.
    - CREATE/ALTER/DROP/TRUNCATE/RENAME + 오브젝트유형 패턴 인식
    - 'schema.object' 형태면 오브젝트명만 반환
    - 추출 실패 시 빈 문자열 반환 (→ propagate 단계에서 NO_OBJECT 처리)
    """
    if not cmd:
        return ""
    m = OBJECT_RE.search(cmd)
    if not m:
        return ""
    obj = m.group(1).upper()
    return obj.split(".")[-1]  # 'schema.object' → 'object'


# ──────────────────────────────────────────────────────────────
# 1. CSV 로드 & 표준화
# ──────────────────────────────────────────────────────────────
def load_csv(content: bytes, encoding: str = "utf-8-sig") -> pd.DataFrame:
    # 전체 칼럼 CSV 를 올려도 필요한 칼럼만 골라 쓴다 (services/common/csv_read.py)
    df = csv_read.read_select(content, COLUMN_ALIASES, encoding)

    # [수정] target_object 를 필수에서 제외 (CSV에 없고, command에서 파싱)
    required = {"user_name", "account", "req_time", "command"}
    missing  = required - set(df.columns)
    if missing:
        label = {
            "user_name": "사용자명",
            "account":   "접속계정",
            "req_time":  "요청 시각",
            "command":   "명령어",
        }
        raise ValueError(f"필수 컬럼 누락: {[label.get(m, m) for m in sorted(missing)]}")

    df["req_time"] = pd.to_datetime(df["req_time"], errors="coerce")

    # [수정] CSV에 오브젝트명 컬럼이 없으면 빈 컬럼 생성 (KeyError 방지)
    if "target_object" not in df.columns:
        df["target_object"] = ""

    for c in ["user_name", "account", "target_object", "command"]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    df["command"] = df["command"].map(clean_cmd)

    # [수정] 오브젝트명이 비어있는 행만 command(SQL)에서 추출
    empty_obj = df["target_object"].eq("")
    df.loc[empty_obj, "target_object"] = df.loc[empty_obj, "command"].map(extract_object)

    df = df.sort_values("req_time", kind="mergesort", na_position="last").reset_index(drop=True)
    df["row_id"] = df.index
    return df


# ──────────────────────────────────────────────────────────────
# 2. DDL 타입 감지
# ──────────────────────────────────────────────────────────────
def detect_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ddl_type"] = df["command"].map(detect_ddl_type)
    return df


# ──────────────────────────────────────────────────────────────
# 3. SR 추출 (인라인 주석)
# ──────────────────────────────────────────────────────────────
def extract_inline_sr(df: pd.DataFrame) -> pd.DataFrame:
    def _find(cmd: str) -> Optional[str]:
        if not cmd:
            return None
        m = SR_COMMENT_RE.search(cmd)
        return m.group(1).upper() if m else None

    df = df.copy()
    df["sr_no"]           = df["command"].map(_find)
    df["sr_source"]       = df["sr_no"].map(lambda x: "auto" if x else None)
    df["unmapped_reason"] = None
    return df


# ──────────────────────────────────────────────────────────────
# 4. Forward + Backward Two-Pointer 전파 (dml_parser 동일)
# ──────────────────────────────────────────────────────────────
def propagate_within_groups(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    df = df.sort_values(GROUP_KEYS + ["req_time"], kind="mergesort").reset_index(drop=True)

    WINDOW_NS  = pd.Timedelta(timedelta(seconds=TIME_WINDOW_SEC)).to_timedelta64()
    sr_arr     = df["sr_no"].to_numpy(copy=True, dtype=object)
    src_arr    = df["sr_source"].to_numpy(copy=True, dtype=object)
    time_arr   = df["req_time"].to_numpy()
    reason_arr = df["unmapped_reason"].to_numpy(copy=True, dtype=object)

    orig_empty = [not bool(v) for v in sr_arr]   # 전파 전 빈 행 마스크

    for keys, grp_idx in df.groupby(GROUP_KEYS, dropna=False).groups.items():
        idx              = list(grp_idx)
        user, acct, obj  = keys

        # 오브젝트명 없는 그룹 (command 파싱 실패 포함)
        if not obj:
            for i in idx:
                if not sr_arr[i] and reason_arr[i] is None:
                    reason_arr[i] = "NO_OBJECT: 명령어에서 대상 오브젝트 추출 실패"
            continue

        valid_idx = [i for i in idx if not pd.isna(time_arr[i])]
        nat_idx   = [i for i in idx if pd.isna(time_arr[i])]

        for i in nat_idx:
            if not sr_arr[i]:
                reason_arr[i] = "SKIP_NAT: 요청 시각 파싱 실패"

        if not valid_idx:
            continue

        valid_idx.sort(key=lambda i: time_arr[i])

        # ── Forward pass: 앞에서 뒤로, 직전 donor에서 전파 ──
        last_sr   = None
        last_time = None
        for i in valid_idx:
            if sr_arr[i]:                       # 이미 SR 보유 → donor 갱신
                last_sr, last_time = sr_arr[i], time_arr[i]
                continue
            if last_sr is not None and last_time is not None:
                if abs(time_arr[i] - last_time) <= WINDOW_NS:
                    sr_arr[i]     = last_sr
                    src_arr[i]    = "propagated"
                    reason_arr[i] = None
                    # 전파받은 행도 다음 donor가 됨 (체인 전파)
                    last_sr, last_time = last_sr, time_arr[i]

        # ── Backward pass: 뒤에서 앞으로, 빈 행 보강 ──
        next_sr   = None
        next_time = None
        for i in reversed(valid_idx):
            if sr_arr[i]:
                next_sr, next_time = sr_arr[i], time_arr[i]
                continue
            if next_sr is not None and next_time is not None:
                if abs(next_time - time_arr[i]) <= WINDOW_NS:
                    sr_arr[i]     = next_sr
                    src_arr[i]    = "propagated"
                    reason_arr[i] = None
                    next_sr, next_time = next_sr, time_arr[i]

        # ── 끝까지 못 받은 행 사유 기록 ──
        group_has_donor = any(orig_empty[i] is False for i in idx)
        for i in valid_idx:
            if not sr_arr[i] and reason_arr[i] is None:
                if not group_has_donor:
                    reason_arr[i] = f"NO_DONOR: 그룹({user}/{acct}/{obj}) 내 SR 보유 행 없음"
                else:
                    reason_arr[i] = f"OUT_OF_WINDOW: ±{TIME_WINDOW_SEC}s 내 donor 없음"

    # 결과 반영
    df = df.copy()
    df["sr_no"]           = sr_arr
    df["sr_source"]       = src_arr
    df["unmapped_reason"] = reason_arr

    propagated = int((df["sr_source"] == "propagated").sum())
    return df.sort_values("row_id").reset_index(drop=True), propagated


# ──────────────────────────────────────────────────────────────
# 5. 엔트리포인트
# ──────────────────────────────────────────────────────────────
def parse(content: bytes, encoding: str = "utf-8-sig") -> DdlParseResult:
    df = load_csv(content, encoding=encoding)
    total = len(df)

    df = detect_types(df)
    df = extract_inline_sr(df)
    df, propagated = propagate_within_groups(df)

    mapped   = int(df["sr_no"].notna().sum())
    unmapped = total - mapped

    # [수정] 오브젝트 추출 실패 건수 통계 추가
    no_object_cnt = int((df["target_object"] == "").sum())

    stats = {
        "total_rows":      total,
        "auto":            int((df["sr_source"] == "auto").sum()),
        "propagated":      propagated,
        "mapped_rows":     mapped,
        "unmapped_rows":   unmapped,
        "no_object_rows":  no_object_cnt,
        "map_rate":        round(mapped / total * 100, 2) if total else 0.0,
    }
    return DdlParseResult(rows=df, stats=stats)
