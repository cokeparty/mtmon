"""
================================================================================
 프로그램명   : sr_enrich.py
 설명         : DB 명령어 로그 엑셀에 SR 정보를 매핑하여 채워주는 프로그램
                - 엑셀의 SR번호 컬럼을 기준으로 sr_master 조회
                - SR제목, 작업구분, 작업승인일, SR종료일 4개 컬럼을 채움
                - 요청 시각 vs 작업승인일/SR종료일 절차 준수 여부 검증
 작성자       : (작성자명)
 최초작성일   : 2026-04-01
================================================================================
 [변경 이력]
 ────────────────────────────────────────────────────────────────────────────────
  버전    | 변경일자     | 작성자    | 변경 내용
 ────────────────────────────────────────────────────────────────────────────────
  v1.0    | 2026-04-01  | (작성자)  | 최초 작성
  v1.1    | 2026-04-01  | (작성자)  | NULL→'-' 치환, 미리보기 출력 제거
  v1.2    | 2026-04-01  | (작성자)  | 날짜형 컬럼 문자열 변환 후 '-' 치환
  v1.3    | 2026-04-01  | (작성자)  | SQLAlchemy 엔진 + URL 인코딩
  v1.4    | 2026-04-01  | (작성자)  | 로그 파일 기능 추가 (p() 헬퍼)
  v1.5    | 2026-04-01  | (작성자)  | SQL CASE 문으로 매핑 일원화
  v1.6    | 2026-04-01  | (작성자)  | 날짜 셀 서식 'yyyy-mm-dd' 적용
  v1.7    | 2026-04-01  | (작성자)  | '검증결과' 컬럼 + 색칠 추가
  v1.8    | 2026-04-01  | (작성자)  | 입력 파일 CSV → XLSX 전환
  v1.9    | 2026-04-01  | (작성자)  | 파일명 규칙 변경 + DRM 해제 단계 반영
                                     ─────────────────────────────────────────
                                     [입출력 파일·폴더 규칙 변경]
                                     - 입력 폴더 : 02.admin → 03.unlocked
                                     - 입력 파일 : dbms_log_admin_{app}_merged.xlsx
                                                 → dbsafer_{cat}_{app}-unlocked.xlsx
                                     - 출력 폴더 : 03.finished → 04.finished
                                     - 출력 파일 : dbms_log_finished_{app}.xlsx
                                                 → dbsafer_{cat}_{app}-finished.xlsx
                                     - 로그 파일 : sr_enrich_{app}.log
                                                 → sr_enrich_{cat}_{app}.log

                                     [실행 인자 변경]
                                     - argv[1] = category (dml/ddl, 필수, choices)
                                     - argv[2] = app_name (hr/sr/epro/pms 등)
                                     - 사용법: python sr_enrich.py dml pms

                                     [리팩토링]
                                     - 전역 상수 → Config dataclass 도입
                                       (sr_extract.py와 구조 통일)
                                     - 출력 디렉토리 자동 생성
                                     - 폴더 번호 체계 정합화
                                       (01.org / 02.admin / 03.unlocked /
                                        04.finished / log)
 ────────────────────────────────────────────────────────────────────────────────
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

# ════════════════════════════════════════════════════════════════════════════════
# ■ 상수 영역
# ════════════════════════════════════════════════════════════════════════════════

# ── 카테고리 허용값 ──────────────────────────────────────────────
ALLOWED_CATEGORIES = ["dml", "ddl"]

# ── 엑셀 컬럼명 ─────────────────────────────────────────────────
SR_NO_COLUMN         = "SR번호"
REQUEST_TIME_COLUMN  = "요청 시각"

# ── 입력 시트 ────────────────────────────────────────────────────
INPUT_SHEET = None  # None=첫 시트, 또는 "Sheet1" / 0

# ── DB 설정 ──────────────────────────────────────────────────────
DB_CONNECT_TIMEOUT = 10

# ── NULL 표시 / 날짜 형식 ────────────────────────────────────────
NULL_DISPLAY            = "-"
DATE_FORMAT_STORE       = "%Y-%m-%d %H:%M:%S"
EXCEL_DATE_DISPLAY_ONLY = True
EXCEL_DATE_DISPLAY_FMT  = "yyyy-mm-dd"

# ── 검증(검증결과) 설정 ──────────────────────────────────────────
VALIDATION_COLUMN     = "검증결과"
VALIDATION_OK         = "정상"
VALIDATION_NG         = "비정상"
EMERGENCY_WORK_TYPES  = ("데이터긴급변경", "긴급변경_사후")
EMERGENCY_CLOSE_DAYS  = 5

# 파스텔 색상 (ARGB)
COLOR_OK_FILL = "FFD4EDDA"  # 파스텔 그린
COLOR_NG_FILL = "FFF8D7DA"  # 파스텔 레드

# ── 로그 / 미리보기 ─────────────────────────────────────────────
LOG_MODE          = "w"     # "w" 덮어쓰기 / "a" 이어쓰기 / "x" 충돌 시 에러
LOG_WITH_TIME     = True
UNMATCHED_PREVIEW = 5

# ── 지원 입력 확장자 ────────────────────────────────────────────
SUPPORTED_INPUT_EXT = (".xlsx", ".xlsm")


# ════════════════════════════════════════════════════════════════════════════════
# ■ Config
# ════════════════════════════════════════════════════════════════════════════════
@dataclass
class Config:
    category: str            # dml / ddl
    app_name: str            # hr / sr / epro / pms ...

    base_dir: Path = field(default_factory=lambda: Path("."))

    @property
    def stem(self) -> str:
        """공통 파일명 어간: dbsafer_[구분]_[업무명]"""
        return f"dbsafer_{self.category}_{self.app_name}"

    @property
    def org_dir(self) -> Path:
        return self.base_dir / "01.org"

    @property
    def admin_dir(self) -> Path:
        return self.base_dir / "02.admin"

    @property
    def unlocked_dir(self) -> Path:
        return self.base_dir / "03.unlocked"

    @property
    def finished_dir(self) -> Path:
        return self.base_dir / "04.finished"

    @property
    def log_dir(self) -> Path:
        return self.base_dir / "log"

    @property
    def input_file(self) -> Path:
        return self.unlocked_dir / f"{self.stem}-unlocked.xlsx"

    @property
    def output_file(self) -> Path:
        return self.finished_dir / f"{self.stem}-finished.xlsx"

    @property
    def log_file(self) -> Path:
        return self.log_dir / f"sr_enrich_{self.category}_{self.app_name}.log"

    def ensure_dirs(self):
        for d in (self.unlocked_dir, self.finished_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════════════════════════
# ■ 인자 파싱
# ════════════════════════════════════════════════════════════════════════════════
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="매핑된 SR번호에 해당하는 SR내용을 채우는 프로그램",
        epilog="예시) python sr_enrich.py dml pms\n"
               "      python sr_enrich.py ddl epro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "category",
        choices=ALLOWED_CATEGORIES,
        help=f"로그 구분 ({'/'.join(ALLOWED_CATEGORIES)})",
    )
    parser.add_argument(
        "app_name",
        help="대상 업무명 (예: hr, sr, epro, pms)",
    )
    return parser.parse_args()


# ════════════════════════════════════════════════════════════════════════════════
# ■ 로그 헬퍼
# ════════════════════════════════════════════════════════════════════════════════
_LOG_FP = None


def open_log(log_path: Path):
    global _LOG_FP
    _LOG_FP = open(log_path, mode=LOG_MODE, encoding="utf-8")

def close_log():
    global _LOG_FP
    if _LOG_FP is not None:
        try:
            _LOG_FP.close()
        except Exception:
            pass
        _LOG_FP = None


def p(msg=""):
    msg = str(msg)
    print(msg)
    if _LOG_FP is not None:
        try:
            if LOG_WITH_TIME and msg.strip():
                ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
                _LOG_FP.write(ts + msg + "\n")
            else:
                _LOG_FP.write(msg + "\n")
            _LOG_FP.flush()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════════
# ■ DB 처리
# ════════════════════════════════════════════════════════════════════════════════
def load_db_config():
    load_dotenv()
    config = {
        "host":     os.getenv("DB_HOST"),
        "port":     os.getenv("DB_PORT"),
        "database": os.getenv("DB_NAME"),
        "user":     os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }
    missing = [k for k, v in config.items() if not v]
    if missing:
        p(f"[오류] .env 파일에 다음 정보가 누락되었습니다: {missing}")
        sys.exit(1)
    return config


def create_db_engine(config):
    user_enc = quote_plus(config["user"])
    pwd_enc  = quote_plus(config["password"])

    db_url = (
        f"postgresql+psycopg2://{user_enc}:{pwd_enc}"
        f"@{config['host']}:{config['port']}/{config['database']}"
    )
    engine = create_engine(
        db_url,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT},
    )
    return engine


def fetch_sr_master(conn):
    sql_query = """
    SELECT 
        sr_no AS "SR번호", 
        request_subject AS "SR제목",
        CASE 
            WHEN work_cd = 'W01' THEN '시스템개선'
            WHEN work_cd = 'W04' THEN '데이터변경'
            WHEN work_cd = 'W02' THEN '긴급변경_사후'
            WHEN work_cd = 'W09' THEN '데이터긴급변경'
            WHEN work_cd = 'W05' THEN '권한신청'
            WHEN work_cd = 'W06' THEN '데이터추출'
        END AS "작업구분",
        CASE 
            WHEN work_cd IN ('W01', 'W02') THEN release_ok_confirm_date
            WHEN work_cd IN ('W04', 'W09', 'W05') THEN work_appr_date
            WHEN work_cd = 'W06' THEN work_req_date
        END AS "작업승인일",
        CASE 
            WHEN work_cd IN ('W06', 'W05') THEN work_conf_date
            ELSE sr_close_date                                              
        END AS "SR종료일",
        work_req_date            AS "작업요청일(데이터추출)",
        work_conf_date           AS "작업완료일(데이터추출, 권한신청)",
        work_appr_date           AS "변경승인일",
        apply_appr_date          AS "반영승인일",
        release_ok_confirm_date  AS "자원이행확인일",
        sr_close_date            AS "SR종료일(원본)"
    FROM sr_master;
    """
    df = pd.read_sql(sql_query, conn)
    return df


# ════════════════════════════════════════════════════════════════════════════════
# ■ 엑셀 입출력
# ════════════════════════════════════════════════════════════════════════════════
def load_excel(file_path: Path, sheet=None):
    """엑셀 파일을 로드한다.
    - sheet: None(=첫 시트) | 시트명(str) | 시트인덱스(int)
    """
    ext = file_path.suffix.lower()
    if ext not in SUPPORTED_INPUT_EXT:
        raise ValueError(
            f"지원하지 않는 입력 형식입니다: '{ext}' "
            f"(지원: {SUPPORTED_INPUT_EXT})"
        )

    sheet_arg = 0 if sheet is None else sheet
    df = pd.read_excel(file_path, sheet_name=sheet_arg, engine="openpyxl")

    sheet_label = sheet_arg if not isinstance(sheet_arg, int) else f"index={sheet_arg}"
    p(f"[INFO] 엑셀 로드 완료 (시트: {sheet_label}): 총 {len(df)}행")
    return df


def save_excel_with_format(df, file_path, date_cols, display_fmt,
                           validation_col=None):
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import PatternFill

    fill_ok = PatternFill(start_color=COLOR_OK_FILL,
                          end_color=COLOR_OK_FILL,
                          fill_type="solid")
    fill_ng = PatternFill(start_color=COLOR_NG_FILL,
                          end_color=COLOR_NG_FILL,
                          fill_type="solid")

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
        ws = writer.book.active

        col_idx_map = {name: idx + 1 for idx, name in enumerate(df.columns)}

        # 1) 날짜 컬럼 표시 형식
        if display_fmt:
            for col in date_cols:
                if col not in col_idx_map:
                    continue
                col_letter = get_column_letter(col_idx_map[col])
                for row in range(2, len(df) + 2):
                    cell = ws[f"{col_letter}{row}"]
                    if isinstance(cell.value, datetime):
                        cell.number_format = display_fmt

        # 2) 검증결과 셀 색상
        if validation_col and validation_col in col_idx_map:
            v_letter = get_column_letter(col_idx_map[validation_col])
            for row in range(2, len(df) + 2):
                cell = ws[f"{v_letter}{row}"]
                val = cell.value
                if val == VALIDATION_OK:
                    cell.fill = fill_ok
                elif val == VALIDATION_NG:
                    cell.fill = fill_ng


# ════════════════════════════════════════════════════════════════════════════════
# ■ 검증 로직
# ════════════════════════════════════════════════════════════════════════════════
def has_sr_no(value):
    if value is None:
        return False
    s = str(value).strip()
    if s == "" or s.lower() == "nan" or s.lower() == "none":
        return False
    return True


def judge_validation(req_dt, appr_dt, close_dt, work_type):
    """
    원칙 ① 요청 시각 ≥ 작업승인일  → 정상
    원칙 ② 작업구분이 긴급 계열이고 요청 시각 < 작업승인일 인 경우,
           SR종료일 ≤ 요청 시각 + 5일 이면 정상
    그 외는 비정상.
    필수 값(요청/승인) 누락 시에는 None 반환(판정 불가).
    """
    if pd.isna(req_dt) or pd.isna(appr_dt):
        return None

    if req_dt >= appr_dt:
        return VALIDATION_OK

    if work_type in EMERGENCY_WORK_TYPES:
        if pd.isna(close_dt):
            return VALIDATION_NG
        deadline = req_dt + timedelta(days=EMERGENCY_CLOSE_DAYS)
        if close_dt <= deadline:
            return VALIDATION_OK
        else:
            return VALIDATION_NG

    return VALIDATION_NG


# ════════════════════════════════════════════════════════════════════════════════
# ■ 메인
# ════════════════════════════════════════════════════════════════════════════════
def main(cfg: Config):
    p("=" * 70)
    p("  엑셀에 SR 정보 매핑 프로그램")
    p("=" * 70)
    p(f"  CATEGORY  : {cfg.category}")
    p(f"  APP_NAME  : {cfg.app_name}")
    p(f"  입력 파일 : {cfg.input_file}")
    p(f"  입력 시트 : {INPUT_SHEET if INPUT_SHEET is not None else '(첫 번째 시트)'}")
    p(f"  출력 파일 : {cfg.output_file}")
    p(f"  로그 파일 : {cfg.log_file} (mode='{LOG_MODE}')")
    p("=" * 70)

    if not cfg.input_file.exists():
        p(f"[오류] 입력 파일을 찾을 수 없습니다: {cfg.input_file}")
        sys.exit(1)

    ext_in = cfg.input_file.suffix.lower()
    if ext_in not in SUPPORTED_INPUT_EXT:
        p(f"[오류] 지원하지 않는 입력 파일 형식: {ext_in} (지원: {SUPPORTED_INPUT_EXT})")
        sys.exit(1)

    try:
        df_log = load_excel(cfg.input_file, sheet=INPUT_SHEET)
    except Exception as e:
        p(f"[오류] 엑셀 읽기 실패: {e}")
        sys.exit(1)

    df_log.columns = df_log.columns.astype(str).str.strip()
    if SR_NO_COLUMN not in df_log.columns:
        p(f"[오류] '{SR_NO_COLUMN}' 컬럼이 없습니다.")
        p(f"       현재 컬럼: {df_log.columns.tolist()}")
        sys.exit(1)

    if REQUEST_TIME_COLUMN not in df_log.columns:
        p(f"[경고] 요청시각 컬럼('{REQUEST_TIME_COLUMN}')이 없어 검증을 건너뜁니다.")

    db_config = load_db_config()
    p(f"[INFO] DB 접속 시도: {db_config['host']}:{db_config['port']} / {db_config['database']}")

    engine = None
    try:
        engine = create_db_engine(db_config)
        with engine.connect() as conn:
            p("[INFO] DB 접속 성공")
            df_sr = fetch_sr_master(conn)
            p(f"[INFO] sr_master 조회 완료: {len(df_sr)}건")
    except Exception as e:
        p(f"[오류] DB 처리 중 오류: {e}")
        sys.exit(1)
    finally:
        if engine is not None:
            engine.dispose()
            p("[INFO] DB 연결 종료")

    # ── 매핑에 필요한 컬럼만 추출 ──
    df_sr_mapped = df_sr[[SR_NO_COLUMN, "SR제목", "작업구분", "작업승인일", "SR종료일"]].copy()

    # ── 입력 엑셀에 동일 컬럼이 있다면 제거 후 머지 ──
    for col in ["SR제목", "작업구분", "작업승인일", "SR종료일"]:
        if col in df_log.columns:
            df_log.drop(columns=[col], inplace=True)

    has_sr_mask = df_log[SR_NO_COLUMN].apply(has_sr_no).reset_index(drop=True)

    df_log["_sr_no_key"] = df_log[SR_NO_COLUMN].apply(
        lambda x: str(x).strip() if has_sr_no(x) else None
    )
    df_sr_mapped[SR_NO_COLUMN] = df_sr_mapped[SR_NO_COLUMN].astype(str).str.strip()

    df_result = df_log.merge(
        df_sr_mapped,
        left_on="_sr_no_key",
        right_on=SR_NO_COLUMN,
        how="left",
        suffixes=("", "_sr"),
    )

    if f"{SR_NO_COLUMN}_sr" in df_result.columns:
        df_result.drop(columns=[f"{SR_NO_COLUMN}_sr"], inplace=True)
    df_result.drop(columns=["_sr_no_key"], inplace=True)
    df_result.reset_index(drop=True, inplace=True)

    # ── 결과 통계 ──
    total_with_sr = has_sr_mask.sum()
    matched = df_result["SR제목"].notna().sum()
    unmatched_with_sr = (has_sr_mask & df_result["SR제목"].isna()).sum()

    p("")
    p("=" * 70)
    p("  매핑 결과")
    p("=" * 70)
    p(f"  전체 행 수             : {len(df_result):>6} 건")
    p(f"  SR번호 보유            : {total_with_sr:>6} 건")
    p(f"  매칭 성공              : {matched:>6} 건")
    p(f"  매칭 실패(SR번호有)    : {unmatched_with_sr:>6} 건")
    p(f"  SR번호 없음(빈값 유지) : {len(df_result) - total_with_sr:>6} 건")

    unmatched_sr_list = df_result.loc[
        has_sr_mask.values & df_result["SR제목"].isna(),
        SR_NO_COLUMN,
    ].unique().tolist()

    if len(unmatched_sr_list) > 0:
        p("")
        p(f"[참고] 매칭 안 된 SR번호 예시 (최대 {UNMATCHED_PREVIEW}개):")
        for sr in unmatched_sr_list[:UNMATCHED_PREVIEW]:
            p(f"    - {sr}")

    # ──────────────────────────────────────────────
    # 날짜 컬럼 정규화 (검증 전, datetime 타입 보장)
    # ──────────────────────────────────────────────
    target_cols = ["SR제목", "작업구분", "작업승인일", "SR종료일"]
    date_cols   = ["작업승인일", "SR종료일"]

    ext_out = cfg.output_file.suffix.lower()
    use_excel_display = (ext_out == ".xlsx" and EXCEL_DATE_DISPLAY_ONLY)

    for col in date_cols:
        if col in df_result.columns:
            df_result[col] = pd.to_datetime(df_result[col], errors="coerce")

    if REQUEST_TIME_COLUMN in df_result.columns:
        df_result[REQUEST_TIME_COLUMN] = pd.to_datetime(
            df_result[REQUEST_TIME_COLUMN], errors="coerce"
        )

    # ──────────────────────────────────────────────
    # 검증결과 컬럼 추가
    # ──────────────────────────────────────────────
    if REQUEST_TIME_COLUMN in df_result.columns:
        def _row_judge(row):
            if not has_sr_no(row.get(SR_NO_COLUMN)):
                return None
            wt = row.get("작업구분")
            if wt is None or (isinstance(wt, float) and pd.isna(wt)) or wt == NULL_DISPLAY:
                return None
            return judge_validation(
                req_dt=row.get(REQUEST_TIME_COLUMN),
                appr_dt=row.get("작업승인일"),
                close_dt=row.get("SR종료일"),
                work_type=wt,
            )

        df_result[VALIDATION_COLUMN] = df_result.apply(_row_judge, axis=1)

        v_ok = (df_result[VALIDATION_COLUMN] == VALIDATION_OK).sum()
        v_ng = (df_result[VALIDATION_COLUMN] == VALIDATION_NG).sum()
        v_na = df_result[VALIDATION_COLUMN].isna().sum()
        p("")
        p("─" * 70)
        p("  절차 검증 결과")
        p("─" * 70)
        p(f"  정상      : {v_ok:>6} 건")
        p(f"  비정상    : {v_ng:>6} 건")
        p(f"  판정 불가 : {v_na:>6} 건 (요청/승인일 누락 등)")
    else:
        df_result[VALIDATION_COLUMN] = None

    # ──────────────────────────────────────────────
    # 날짜 컬럼 출력 형식 처리
    # ──────────────────────────────────────────────
    for col in date_cols:
        if col not in df_result.columns:
            continue
        if use_excel_display:
            df_result[col] = df_result[col].astype(object)
            df_result[col] = df_result[col].where(df_result[col].notna(), None)
        else:
            df_result[col] = df_result[col].apply(
                lambda x: x.strftime(DATE_FORMAT_STORE) if pd.notna(x) else None
            )

    if REQUEST_TIME_COLUMN in df_result.columns:
        if use_excel_display:
            df_result[REQUEST_TIME_COLUMN] = df_result[REQUEST_TIME_COLUMN].astype(object)
            df_result[REQUEST_TIME_COLUMN] = df_result[REQUEST_TIME_COLUMN].where(
                df_result[REQUEST_TIME_COLUMN].notna(), None
            )
        else:
            df_result[REQUEST_TIME_COLUMN] = df_result[REQUEST_TIME_COLUMN].apply(
                lambda x: x.strftime(DATE_FORMAT_STORE) if pd.notna(x) else None
            )

    # ──────────────────────────────────────────────
    # NULL → '-' 치환 (SR번호 있는 행만)
    # ──────────────────────────────────────────────
    fill_cols = target_cols + [VALIDATION_COLUMN]
    for col in fill_cols:
        if col not in df_result.columns:
            continue
        df_result[col] = df_result[col].astype(object)
        mask_fill = has_sr_mask.values & df_result[col].isna()
        df_result.loc[mask_fill, col] = NULL_DISPLAY

    # ── 결과 파일 저장 (XLSX 전용) ──
    try:
        if ext_out != ".xlsx":
            p(f"[오류] 출력 파일은 .xlsx 만 지원합니다: {ext_out}")
            sys.exit(1)

        save_excel_with_format(
            df_result,
            cfg.output_file,
            date_cols=date_cols + (
                [REQUEST_TIME_COLUMN] if REQUEST_TIME_COLUMN in df_result.columns else []
            ),
            display_fmt=EXCEL_DATE_DISPLAY_FMT if use_excel_display else None,
            validation_col=VALIDATION_COLUMN,
        )
        p("")
        p(f"[INFO] 결과 저장 완료: {cfg.output_file}")
    except SystemExit:
        raise
    except Exception as e:
        p(f"[오류] 결과 저장 실패: {e}")
        sys.exit(1)

    p("=" * 70)
    p("  처리 완료")
    p("=" * 70)


# ════════════════════════════════════════════════════════════════════════════════
# ■ 엔트리포인트
# ════════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    args = parse_args()
    cfg = Config(
        category=args.category.strip().lower(),
        app_name=args.app_name.strip(),
    )
    cfg.ensure_dirs()

    open_log(cfg.log_file)
    try:
        main(cfg)
    finally:
        close_log()
