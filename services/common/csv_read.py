"""DBSAFER CSV 읽기 — 필요한 칼럼만 골라낸다.

DBSAFER 에서 내려받은 CSV 를 칼럼 4개로 줄이지 않고 전체 칼럼 그대로 올려도 된다.
칼럼 이름(별칭)으로 필요한 칼럼만 찾아 쓰고 나머지는 버린다.
  - 이름 비교 시 앞뒤·중간 공백과 BOM 은 무시 ("요청 시각" = "요청시각")
  - 같은 용도의 칼럼이 여러 개면(예: 접속계정, 접속계정명) 별칭 목록에서 먼저 적힌 것을 쓴다
"""
from __future__ import annotations

import io
import re

import pandas as pd


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", str(name).replace("﻿", "")).lower()


def read_select(content: bytes, aliases: dict[str, str],
                encoding: str = "utf-8-sig") -> pd.DataFrame:
    """CSV bytes → 별칭으로 찾은 표준 칼럼만 담은 DataFrame (값은 모두 문자열).

    aliases: {CSV 칼럼명: 표준 칼럼명} — 순서가 우선순위.
    """
    if not content or not content.strip():
        raise ValueError("빈 파일입니다.")
    try:
        df = pd.read_csv(io.BytesIO(content), encoding=encoding, dtype=str)
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(content), encoding="cp949", dtype=str)
    except pd.errors.EmptyDataError:
        raise ValueError("빈 파일입니다.")

    # 표준 칼럼별로 우선순위가 가장 높은 CSV 칼럼 하나를 고른다
    rank = {}                                    # 정규화된 별칭 → (우선순위, 표준명)
    for i, (alias, target) in enumerate(aliases.items()):
        rank.setdefault(_norm(alias), (i, target))
    chosen: dict[str, tuple[int, str]] = {}      # 표준명 → (우선순위, CSV 칼럼명)
    for col in df.columns:
        hit = rank.get(_norm(col))
        if hit is None:
            continue
        prio, target = hit
        if target not in chosen or prio < chosen[target][0]:
            chosen[target] = (prio, col)

    picked = df[[col for _, col in chosen.values()]].copy()
    picked.columns = list(chosen.keys())
    return picked
