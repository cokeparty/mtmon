# tests/test_load_program_change.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # tests → 루트

import pytest
from scripts import load_program_change as batch


# ---- 전월 산정 ----
def test_prev_month_ym(monkeypatch):
    import scripts.load_program_change as m
    from datetime import date

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 15)
    monkeypatch.setattr(m, "date", FakeDate)
    assert m.prev_month_ym() == "2026-02"


# ---- 인자 파싱 ----
def test_parse_args_default(monkeypatch):
    monkeypatch.setattr(batch, "prev_month_ym", lambda: "2026-02")
    ym, systems = batch.parse_args(["prog"])
    assert ym == "2026-02"
    assert systems == batch.SYSTEMS

def test_parse_args_specific():
    ym, systems = batch.parse_args(["prog", "2026-01", "HR"])
    assert ym == "2026-01" and systems == ["HR"]

def test_parse_args_bad_ym():
    with pytest.raises(SystemExit):
        batch.parse_args(["prog", "202601"])

def test_parse_args_bad_system():
    with pytest.raises(SystemExit):
        batch.parse_args(["prog", "2026-01", "UNKNOWN"])


# ---- run(): 정상/마감/예외 격리 ----
def test_run_all_success(monkeypatch):
    calls = []
    def fake_collect(db, sys_code, ym, url):
        calls.append(sys_code)
        return {"parsed_lines": 1, "inserted": 1, "skipped_dup": 0,
                "count_none": 0, "count_conflict": 0,
                "count_abnormal": 0, "count_normal": 1}
    monkeypatch.setattr(batch.collect_orchestrator, "collect", fake_collect)
    monkeypatch.setattr(batch, "SessionLocal", lambda: _FakeDB())

    fail = batch.run("2026-01", ["HR", "PMS"])
    assert fail == 0
    assert calls == ["HR", "PMS"]

def test_run_locked_period_is_skipped(monkeypatch):
    def fake_collect(db, sys_code, ym, url):
        raise PermissionError("마감 회차")
    monkeypatch.setattr(batch.collect_orchestrator, "collect", fake_collect)
    monkeypatch.setattr(batch, "SessionLocal", lambda: _FakeDB())

    fail = batch.run("2026-01", ["HR"])
    assert fail == 1   # 마감은 실패로 카운트되지만 예외로 죽지 않음

def test_run_one_fails_others_continue(monkeypatch):
    seen = []
    def fake_collect(db, sys_code, ym, url):
        seen.append(sys_code)
        if sys_code == "EPRO":
            raise RuntimeError("SR DB 연결 실패")
        return {"parsed_lines": 0, "inserted": 0, "skipped_dup": 0,
                "count_none": 0, "count_conflict": 0,
                "count_abnormal": 0, "count_normal": 0}
    monkeypatch.setattr(batch.collect_orchestrator, "collect", fake_collect)
    monkeypatch.setattr(batch, "SessionLocal", lambda: _FakeDB())

    fail = batch.run("2026-01", ["HR", "EPRO", "PMS"])
    assert fail == 1               # EPRO만 실패
    assert seen == ["HR", "EPRO", "PMS"]   # 실패해도 끝까지 순회


# ---- 가짜 DB 세션 (commit/close만 받아주면 됨) ----
class _FakeDB:
    def commit(self): pass
    def close(self): pass
    def rollback(self): pass
