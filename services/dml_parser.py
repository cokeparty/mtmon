# services/dml_parser.py
"""
DML 로그 파싱 / SR 추출·전파 엔진 (sr_extract.py 웹 이식판)

[원본 대비 변경점]
1. 파일 경로 I/O 제거 → CSV bytes(업로드 스트림) 입력, DataFrame 반환
2. SR 패턴을 원본과 동일하게 수정: [A-Za-z]\\d{2}-\\d{8}-\\d{3}
3. clean_cmd() 추가 (♪ / \\r\\n\\t / \\x00 전처리)
4. Forward + Backward Two-Pointer 체인 전파 (원본 동일 로직)
5. build_groups()에 200초 시간윈도우 기반 그룹 분리 적용
6. 검증(정상/비정상)은 여기서 하지 않음 → dml_validation 담당
7. [수정] table_name 은 CSV 필수 컬럼에서 제외하고 command(SQL)에서 파싱
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

import pandas as pd

# ──────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────
TIME_WINDOW_SEC = 200
GROUP_KEYS      = ["user_name", "account", "table_name"]

# 원본 sr_ext.py 동일 패턴: H01-20260401-001 형식
SR_COMMENT_RE = re.compile(r"/\*.*?([A-Za-z]\d{2}-\d{8}-\d{3}).*?\*/", re.DOTALL)

# [수정] SQL 명령어에서 대상 테이블명 추출용 정규식
#   INSERT INTO t / UPDATE t / DELETE FROM t / MERGE INTO t 등 대응
TABLE_RE = re.compile(
    r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|INTO|FROM)\s+'r'["`\[]?([A-Za-z0-9_$#]+(?:\.[A-Za-z0-9_$#]+)?)',
    re.IGNORECASE,
)

# [수정] DML 작업유형 판별용 (SELECT 등 비대상 필터링에 활용 가능)
OP_RE = re.compile(r'^\s*(INSERT|UPDATE|DELETE|MERGE|SELECT)', re.IGNORECASE)

# 접속계정(소문자) → 업무명 고정 매핑
ACCOUNT_SYSTEM_MAP: dict[str, str] = {
    "apps":  "HR",
    "exhr":  "HR",
    "bizfu": "PMS",
    "emrou": "EPRO",
    "ssru":  "SR",
}

COLUMN_ALIASES = {
    "사용자명":   "user_name",
    "접속계정":   "account",
    "접속계정명": "account",
    "테이블명":   "table_name",
    "대상테이블": "table_name",
    "요청시각":   "req_time",
    "요청 시각":  "req_time",
    "수행시각":   "req_time",
    "수행시간":   "req_time",
    "실행구문":   "command",
    "명령어":     "command",
    "쿼리":       "command",
    "SQL":        "command",
}

REASON_NO_TABLE      = "NO_TABLE"
REASON_NO_DONOR      = "NO_DONOR"
REASON_OUT_OF_WINDOW = "OUT_OF_WINDOW"
REASON_SKIP_NAT      = "SKIP_NAT"


# ──────────────────────────────────────────────────────────────
# 결과 컨테이너
# ──────────────────────────────────────────────────────────────
@dataclass
class ParseResult:
    rows:   pd.DataFrame
    groups: pd.DataFrame
    stats:  dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────
def clean_cmd(s) -> str:
    """명령어 문자열 전처리 — 원본 sr_ext.py clean_cmd 동일."""
    if not isinstance(s, str):
        return ""
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = s.replace("♪", " ").replace("\x00", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# [수정] 명령어(SQL)에서 대상 테이블명 추출
def extract_table(cmd: str) -> str:
    """
    command(SQL 원문)에서 대상 테이블명을 추출한다.
    - INSERT INTO / UPDATE / DELETE FROM / MERGE INTO 패턴 인식
    - 'schema.table' 형태면 테이블명만 반환
    - 추출 실패 시 빈 문자열 반환 (→ propagate 단계에서 NO_TABLE 처리)
    """
    if not cmd:
        return ""
    m = TABLE_RE.search(cmd)
    if not m:
        return ""
    tbl = m.group(1).upper()
    return tbl.split(".")[-1]  # 'schema.table' → 'table'


# [수정] 명령어(SQL)에서 작업유형 추출
def extract_op(cmd: str) -> str:
    """command 에서 DML 작업유형(INSERT/UPDATE/DELETE/MERGE/SELECT) 추출."""
    if not cmd:
        return ""
    m = OP_RE.match(cmd)
    return m.group(1).upper() if m else ""


# ──────────────────────────────────────────────────────────────
# 1. CSV 로드 & 표준화
# ──────────────────────────────────────────────────────────────
def load_csv(content: bytes, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """업로드된 CSV bytes를 표준 컬럼 DataFrame으로 변환."""
    try:
        df = pd.read_csv(io.BytesIO(content), encoding=encoding, dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(content), encoding="cp949", dtype=str)

    # BOM·공백 제거 후 alias 적용
    df.columns = [c.strip().replace("\ufeff", "").replace("﻿", "") for c in df.columns]
    df = df.rename(columns={c: COLUMN_ALIASES.get(c, c) for c in df.columns})

    # [수정] table_name 을 필수에서 제외 (CSV에 없고, command에서 파싱)
    required = {"user_name", "account", "req_time", "command"}
    missing  = required - set(df.columns)
    if missing:
        # 한글 라벨로 보여줘서 사용자 친화적으로
        label = {
            "user_name": "사용자명",
            "account":   "접속계정",
            "req_time":  "요청 시각",
            "command":   "명령어",
        }
        raise ValueError(f"필수 컬럼 누락: {[label.get(m, m) for m in sorted(missing)]}")

    df["req_time"] = pd.to_datetime(df["req_time"], errors="coerce")

    # [수정] CSV에 테이블명 컬럼이 없으면 빈 컬럼 생성
    if "table_name" not in df.columns:
        df["table_name"] = ""

    for c in ["user_name", "account", "table_name", "command"]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    # 원본과 동일하게 명령어 전처리
    df["command"] = df["command"].map(clean_cmd)

    # [수정] 테이블명이 비어있는 행만 command(SQL)에서 추출
    empty_tbl = df["table_name"].eq("")
    df.loc[empty_tbl, "table_name"] = df.loc[empty_tbl, "command"].map(extract_table)

    # 접속계정 → 업무명 자동 매핑; 해당 없는 행 제외
    df["system_code"] = df["account"].str.lower().map(ACCOUNT_SYSTEM_MAP)
    excluded = int(df["system_code"].isna().sum())
    df = df[df["system_code"].notna()].reset_index(drop=True)

    df = df.sort_values("req_time", kind="mergesort", na_position="last").reset_index(drop=True)
    df["row_id"] = df.index
    return df, excluded


# ──────────────────────────────────────────────────────────────
# 2. 1차: 인라인 /* SR */ 주석에서 직접 추출
# ──────────────────────────────────────────────────────────────
def extract_inline_sr(df: pd.DataFrame) -> pd.DataFrame:
    """command 내 /* H01-YYYYMMDD-NNN */ 주석에서 SR번호 직접 추출."""
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
# 3. 2차: Forward + Backward Two-Pointer 체인 전파 (원본 동일)
# ──────────────────────────────────────────────────────────────
def propagate_within_groups(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    같은 (user_name, account, table_name) 그룹 내에서
    Forward pass → Backward pass 순으로 ±TIME_WINDOW_SEC 체인 전파.
    전파받은 행도 다음 행의 donor가 됨 (원본 sr_ext.py 동일 로직).
    Returns: (결과 DataFrame, 전파 건수)
    """
    df = df.sort_values(GROUP_KEYS + ["req_time"], kind="mergesort").reset_index(drop=True)

    WINDOW_NS  = pd.Timedelta(timedelta(seconds=TIME_WINDOW_SEC)).to_timedelta64()
    sr_arr     = df["sr_no"].to_numpy(copy=True, dtype=object)
    src_arr    = df["sr_source"].to_numpy(copy=True, dtype=object)
    time_arr   = df["req_time"].to_numpy()
    reason_arr = df["unmapped_reason"].to_numpy(copy=True, dtype=object)

    orig_empty = [not bool(v) for v in sr_arr]   # 전파 전 빈 행 마스크

    for keys, grp_idx in df.groupby(GROUP_KEYS, dropna=False).groups.items():
        idx         = list(grp_idx)
        user, acct, table = keys

        # 테이블명 없는 그룹 (command 파싱 실패 포함)
        if not table:
            for i in idx:
                if not sr_arr[i] and reason_arr[i] is None:
                    reason_arr[i] = "NO_TABLE: 명령어에서 테이블명 추출 실패"
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
        last_src  = None
        last_time = None
        for i in valid_idx:
            if sr_arr[i]:                       # 이미 SR 보유 → donor 갱신
                last_sr, last_src, last_time = sr_arr[i], src_arr[i], time_arr[i]
                continue
            if last_sr is not None and last_time is not None:
                if abs(time_arr[i] - last_time) <= WINDOW_NS:
                    sr_arr[i]   = last_sr
                    src_arr[i]  = "propagated"
                    reason_arr[i] = None
                    # 전파받은 행도 다음 donor가 됨 (체인 전파)
                    last_sr, last_src, last_time = last_sr, "propagated", time_arr[i]

        # ── Backward pass: 뒤에서 앞으로, 빈 행 보강 ──
        next_sr   = None
        next_src  = None
        next_time = None
        for i in reversed(valid_idx):
            if sr_arr[i]:
                next_sr, next_src, next_time = sr_arr[i], src_arr[i], time_arr[i]
                continue
            if next_sr is not None and next_time is not None:
                if abs(next_time - time_arr[i]) <= WINDOW_NS:
                    sr_arr[i]   = next_sr
                    src_arr[i]  = "propagated"
                    reason_arr[i] = None
                    next_sr, next_src, next_time = next_sr, "propagated", time_arr[i]

        # ── 끝까지 못 받은 행 사유 기록 ──
        group_has_donor = any(orig_empty[i] is False for i in idx)  # 원래 SR 보유행 존재 여부
        for i in valid_idx:
            if not sr_arr[i] and reason_arr[i] is None:
                if not group_has_donor:
                    reason_arr[i] = "NO_DONOR: 그룹 내 SR 보유 행 없음"
                else:
                    reason_arr[i] = f"OUT_OF_WINDOW: ±{TIME_WINDOW_SEC}s 내 donor 없음"

    # 결과 반영
    df["sr_no"]           = sr_arr
    df["sr_source"]       = src_arr
    df["unmapped_reason"] = reason_arr

    propagated_cnt = int(((df["sr_source"] == "propagated")).sum())
    return df.sort_values("row_id").reset_index(drop=True), propagated_cnt


# ──────────────────────────────────────────────────────────────
# 4. 200초 시간윈도우 기반 그룹 분리
# ──────────────────────────────────────────────────────────────
def _assign_time_groups(df: pd.DataFrame) -> pd.DataFrame:
    """
    (user_name, account, table_name) 키 내에서 시간 간격이
    TIME_WINDOW_SEC를 초과하면 새 time_group으로 분리.
    """
    df = df.sort_values(GROUP_KEYS + ["req_time"], kind="mergesort").reset_index(drop=True)
    df["time_group"] = 0

    gid = 0
    for _, grp_idx in df.groupby(GROUP_KEYS, dropna=False).groups.items():
        idx  = list(grp_idx)
        prev = None
        for i in idx:
            t = df.at[i, "req_time"]
            if prev is None or pd.isna(t) or pd.isna(prev):
                gid += 1
            elif (t - prev).total_seconds() > TIME_WINDOW_SEC:
                gid += 1
            df.at[i, "time_group"] = gid
            prev = t

    return df.sort_values("row_id").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────
# 5. 그룹 메타데이터 생성
# ──────────────────────────────────────────────────────────────
def build_groups(df: pd.DataFrame) -> pd.DataFrame:
    """
    time_group 단위로 그룹 메타 생성.
    각 그룹의 대표 SR(가장 많이 등장한 값), 시간범위, 행수, 상태 산출.
    """
    df = _assign_time_groups(df)

    records = []
    for tg, g in df.groupby("time_group", dropna=False):
        srs = g["sr_no"].dropna()
        srs = srs[srs.astype(bool)]
        if len(srs):
            sr_no = srs.mode().iat[0]          # 최빈 SR
        else:
            sr_no = None

        records.append({
            "time_group":  int(tg),
            "user_name":   g["user_name"].iat[0],
            "account":     g["account"].iat[0],
            "table_name":  g["table_name"].iat[0],
            "system_code": g["system_code"].iat[0],
            "time_from":   g["req_time"].min(),
            "time_to":     g["req_time"].max(),
            "row_count":   int(len(g)),
            "sr_no":       sr_no,
            "status":      "적용됨" if sr_no else "미입력",
        })


    groups = pd.DataFrame(records)

    # [수정] rows·groups 모두 group_id로 통일
    groups = groups.rename(columns={"time_group": "group_id"})
    df     = df.rename(columns={"time_group": "group_id"})

    return df, groups


# ──────────────────────────────────────────────────────────────
# 6. 엔트리포인트
# ──────────────────────────────────────────────────────────────
def parse(content: bytes, encoding: str = "utf-8-sig") -> ParseResult:
    """
    CSV bytes → 파싱 → SR 추출/전파 → 그룹화까지 수행.
    검증(정상/비정상)은 여기서 하지 않음 (dml_validation 담당).
    """
    df, excluded = load_csv(content, encoding=encoding)
    total = len(df)

    df = extract_inline_sr(df)
    inline_cnt = int(df["sr_no"].notna().sum())

    df, propagated_cnt = propagate_within_groups(df)

    rows, groups = build_groups(df)

    mapped   = int(rows["sr_no"].notna().sum())
    unmapped = total - mapped

    # [수정] 테이블명 추출 실패 건수 통계 추가
    no_table_cnt = int((rows["table_name"] == "").sum())

    stats = {
        "total_rows":      total,
        "excluded_rows":   excluded,
        "inline_sr":       inline_cnt,
        "propagated_sr":   propagated_cnt,
        "mapped_rows":     mapped,
        "unmapped_rows":   unmapped,
        "no_table_rows":   no_table_cnt,
        "group_count":     int(len(groups)),
        "map_rate":        round(mapped / total * 100, 2) if total else 0.0,
    }

    return ParseResult(rows=rows, groups=groups, stats=stats)
