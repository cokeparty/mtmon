"""
================================================================================
 프로그램명   : sr_extract.py
 설명         : DB 명령어 로그 CSV에서 SR번호를 추출/전파하여 채워주는 프로그램
                - /* SR번호 */ 주석에서 1차 추출
                - 동일 사용자/접속계정/테이블 그룹 내 시간 윈도우(±N초)
                  Two-Pointer 체인 전파로 2차 보강
                - 미매핑 행은 사용자명 기준으로 별도 파일로 분리 저장
 작성자       : (작성자명)
 최초작성일   : 2026-04-01
================================================================================
 [변경 이력]
 ────────────────────────────────────────────────────────────────────────────────
  버전    | 변경일자     | 작성자    | 변경 내용
 ────────────────────────────────────────────────────────────────────────────────
  v1.0    | 2026-04-01  | (작성자)  | 최초 작성
  v1.1    | 2026-04-01  | (작성자)  | 로깅/안정성 보완 (FileOnlyTee, NaT 처리)
  v1.2    | 2026-04-01  | (작성자)  | 2차 전파 BFS 체인 전파로 변경
  v1.3    | 2026-04-01  | (작성자)  | Two-Pointer 방식 O(N) 성능 최적화
  v1.4    | 2026-04-01  | (작성자)  | XLSX 출력 + 사용자명 기준 시트 분리
  v1.5    | 2026-04-01  | (작성자)  | DEBUG_MODE 옵션 추가
  v1.6    | 2026-04-01  | (작성자)  | argparse 도입 (APP_NAME 인자화)
  v1.7    | 2026-04-01  | (작성자)  | 파일명 규칙 변경 + 사용자별 파일 분리
                                     ─────────────────────────────────────────
                                     [입출력 파일명 규칙 변경]
                                     - 입력 : dbsafer_[구분]_[업무명]-org.csv
                                     - 출력 : dbsafer_[구분]_[업무명]-admin.xlsx
                                     - 사용자별:
                                       dbsafer_[구분]_[업무명]-admin_[사용자명].xlsx
                                     - 로그 : sr_ext_[구분]_[업무명].log

                                     [실행 인자 변경]
                                     - argv[1] = category (dml/ddl, 필수, choices)
                                     - argv[2] = app_name (hr/sr/epro/pms 등)
                                     - 사용법: python sr_extract.py dml pms

                                     [사용자별 분리 방식 변경]
                                     - 기존: 한 xlsx 안에 사용자명별 시트로 분리
                                     - 변경: 사용자명별로 개별 xlsx 파일 생성
                                            (메일 송부 자동화 용이)
                                     - 메인 파일에서 미매핑 행 삭제 로직은 유지
                                     - 시트명 31자 제한 → 파일명 안전 처리로 대체

                                     [리팩토링]
                                     - 전역 스크립트 → 함수 단위 모듈화
                                     - Config 클래스 도입으로 설정 일원화
                                     - safe_filename() 유틸 함수 추가
                                     - 출력 디렉토리 자동 생성
 ────────────────────────────────────────────────────────────────────────────────
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ============================================================
# ⚙️ 상수 및 설정
# ============================================================

# 컬럼명
COL_CMD     = "명령어"
COL_TIME    = "요청 시각"
COL_ACCOUNT = "접속계정"
COL_USER    = "사용자명"
COL_SR      = "SR번호"
COL_REASON  = "미매핑사유"

# 시트 / 라벨
MAIN_SHEET_NAME    = "data"
UNKNOWN_USER_LABEL = "미상"

# 인코딩
ENCODING = "utf-8-sig"

# 처리 파라미터 (실행 인자로 받지 않는 내부 고정값)
TIME_WINDOW_SEC  = 200
STRICT_AMBIGUOUS = False  # True면 윈도우 내 서로 다른 SR 섞이면 채우지 않음

# 카테고리 허용값
ALLOWED_CATEGORIES = ["dml", "ddl"]

# 파일명 안전화: Windows/Linux 공통 금지문자 + 한글은 허용
INVALID_FILENAME_CHARS = re.compile(r'[\\/\*\?\:\[\]\<\>\|\"]')

# 정규식 (모듈 레벨에서 컴파일)
SR_PATTERN = re.compile(r"/\*.*?([A-Za-z]\d{2}-\d{8}-\d{3}).*?\*/", re.DOTALL)
TABLE_PATTERN = re.compile(
    r"^\s*(?:/\*.*?\*/\s*)*"
    r"(?:insert\s+into|delete\s+from|update)\s+"
    r"([A-Za-z_][\w\.\$#]*)",
    re.IGNORECASE | re.DOTALL,
)


# ============================================================
# 📦 Config
# ============================================================
@dataclass
class Config:
    category: str          # dml / ddl
    app_name: str          # hr / sr / epro / pms ...
    debug_mode: bool = False

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
    def log_dir(self) -> Path:
        return self.base_dir / "log"

    @property
    def input_file(self) -> Path:
        return self.org_dir / f"{self.stem}-org.csv"

    @property
    def output_file(self) -> Path:
        return self.admin_dir / f"{self.stem}-admin.xlsx"

    @property
    def log_file(self) -> Path:
        return self.log_dir / f"sr_ext_{self.category}_{self.app_name}.log"

    def user_output_file(self, user_label: str) -> Path:
        """사용자별 미매핑 파일 경로"""
        safe = safe_filename(user_label)
        return self.admin_dir / f"{self.stem}-admin_{safe}.xlsx"

    def ensure_dirs(self):
        for d in (self.org_dir, self.admin_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


# ============================================================
# 🪵 로거
# ============================================================
class FileOnlyTee:
    def __init__(self, file_path, mode="w", encoding="utf-8"):
        self.terminal = sys.stdout
        self.log_file = open(file_path, mode, encoding=encoding)

    def write(self, msg):
        self.terminal.write(msg)
        self.log_file.write(msg)
        self.log_file.flush()

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

    def close(self):
        try:
            self.log_file.close()
        except Exception:
            pass


# ============================================================
# 🛠️ 유틸
# ============================================================
def safe_filename(name: str) -> str:
    """파일명에 쓸 수 없는 문자를 _ 로 치환. 빈 값은 '미상' 처리."""
    base = (name or "").strip() or UNKNOWN_USER_LABEL
    base = INVALID_FILENAME_CHARS.sub("_", base)
    # 공백/연속 _ 정리
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"_{2,}", "_", base)
    return base.strip("_") or UNKNOWN_USER_LABEL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DBSAFER에서 추출된 CSV 로그에서 SR번호를 추출/전파하는 프로그램",
        epilog="예시) python sr_extract.py dml pms\n"
               "      python sr_extract.py ddl epro --debug",
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
    parser.add_argument(
        "-d", "--debug",
        action="store_true",
        help="디버그 모드 (엑셀에 미매핑사유 컬럼 포함)",
    )
    return parser.parse_args()


def clean_cmd(s) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = s.replace("♪", " ").replace("\x00", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def extract_sr(cmd):
    m = SR_PATTERN.search(cmd) if isinstance(cmd, str) else None
    return m.group(1).upper() if m else None


def extract_table(cmd):
    m = TABLE_PATTERN.search(cmd) if isinstance(cmd, str) else None
    return m.group(1).split(".")[-1].upper() if m else None


# ============================================================
# 1. CSV 로드 및 전처리
# ============================================================
def load_and_prepare(cfg: Config) -> pd.DataFrame:
    if not cfg.input_file.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {cfg.input_file}")

    df = pd.read_csv(cfg.input_file, encoding=ENCODING, dtype=str).fillna("")
    df.columns = [c.strip().replace("\ufeff", "") for c in df.columns]

    if COL_SR not in df.columns:
        df[COL_SR] = ""
    df[COL_SR] = df[COL_SR].astype(str).str.strip()

    df[COL_TIME] = pd.to_datetime(df[COL_TIME], errors="coerce")
    nat_count = df[COL_TIME].isna().sum()
    if nat_count > 0:
        print(f"⚠️ 요청 시각 파싱 실패: {nat_count}건")

    df = df.sort_values(by=COL_TIME, kind="mergesort", na_position="last").reset_index(drop=True)
    df["_orig_row"] = df.index + 2
    df["_cmd_clean"] = df[COL_CMD].apply(clean_cmd)

    print(f"▶ 요청 시각 기준 정렬 완료 (총 {len(df)}행)\n")
    return df


# ============================================================
# 2. 1차: 주석 SR 추출
# ============================================================
def extract_sr_stage1(df: pd.DataFrame) -> int:
    extracted = df["_cmd_clean"].apply(extract_sr)
    mask_empty = df[COL_SR].eq("")
    fill_idx = mask_empty & extracted.notna()
    df.loc[fill_idx, COL_SR] = extracted[fill_idx]
    count = int(fill_idx.sum())
    print(f"[1차] /* */ 주석 추출: {count}건")
    return count


# ============================================================
# 3. 2차: Two-Pointer 체인 전파
# ============================================================
def propagate_sr_stage2(df: pd.DataFrame) -> dict:
    """
    동일 (사용자/접속계정/테이블) 그룹 내에서 시간 윈도우(±N초) 기반
    Two-Pointer 양방향 패스로 SR 전파.
    Returns: 통계 dict
    """
    df["_table"] = df["_cmd_clean"].apply(extract_table)
    df[COL_REASON] = ""

    df.sort_values(
        by=[COL_USER, COL_ACCOUNT, "_table", COL_TIME],
        kind="mergesort",
        inplace=True,
    )
    df.reset_index(drop=True, inplace=True)

    no_table = no_candidate = skip_nat = 0

    sr_arr     = df[COL_SR].to_numpy(copy=True)
    time_arr   = df[COL_TIME].to_numpy()
    reason_arr = df[COL_REASON].to_numpy(copy=True).astype(object)

    WINDOW_NS = pd.Timedelta(timedelta(seconds=TIME_WINDOW_SEC)).to_timedelta64()

    orig_empty_mask_pre = df[COL_SR].to_numpy() == ""

    for keys, idx in df.groupby([COL_USER, COL_ACCOUNT, "_table"], dropna=False).groups.items():
        idx = list(idx)
        user, acct, table = keys

        # 테이블명 추출 실패 그룹
        if not table:
            for i in idx:
                if not sr_arr[i]:
                    no_table += 1
                    reason_arr[i] = "NO_TABLE: 명령어에서 테이블명 추출 실패"
            continue

        valid_idx = [i for i in idx if not pd.isna(time_arr[i])]
        nat_idx   = [i for i in idx if pd.isna(time_arr[i])]

        # NaT 행 처리
        for i in nat_idx:
            if not sr_arr[i]:
                skip_nat += 1
                reason_arr[i] = "SKIP_NAT: 요청 시각 파싱 실패"

        if not valid_idx:
            continue

        valid_idx.sort(key=lambda i: time_arr[i])
        n = len(valid_idx)

        # donor 자체가 없는 그룹
        if not any(sr_arr[i] for i in valid_idx):
            for i in valid_idx:
                if not sr_arr[i]:
                    no_candidate += 1
                    reason_arr[i] = (
                        f"NO_DONOR: 그룹({user}/{acct}/{table}) 내 SR 보유 donor 없음"
                    )
            continue

        # ---- Forward pass ----
        last_donor_pos = -1
        for k in range(n):
            i = valid_idx[k]
            if sr_arr[i]:
                last_donor_pos = k
                continue
            if last_donor_pos == -1:
                continue
            diff = time_arr[i] - time_arr[valid_idx[last_donor_pos]]
            if diff <= WINDOW_NS:
                sr_arr[i] = sr_arr[valid_idx[last_donor_pos]]
                last_donor_pos = k

        # ---- Backward pass ----
        last_donor_pos = -1
        sr_back = sr_arr.copy()
        for k in range(n - 1, -1, -1):
            i = valid_idx[k]
            if sr_back[i]:
                last_donor_pos = k
                continue
            if last_donor_pos == -1:
                continue
            diff = time_arr[valid_idx[last_donor_pos]] - time_arr[i]
            if diff <= WINDOW_NS:
                sr_arr[i] = sr_arr[valid_idx[last_donor_pos]]
                last_donor_pos = k

        # 미매핑 사유 기록 (양방향 후에도 비어있는 행)
        for k in range(n):
            i = valid_idx[k]
            if sr_arr[i]:
                continue
            no_candidate += 1
            reason_arr[i] = f"OUT_OF_WINDOW: ±{TIME_WINDOW_SEC}초 내 donor 없음"

    # 채워진 건수 계산
    now_filled_mask = sr_arr != ""
    propagated = int((orig_empty_mask_pre & now_filled_mask).sum())

    df[COL_SR]     = sr_arr
    df[COL_REASON] = reason_arr

    print(f"[2차] 윈도우(±{TIME_WINDOW_SEC}초) Two-Pointer 체인 전파: {propagated}건")

    return {
        "propagated":   propagated,
        "no_table":     no_table,
        "no_candidate": no_candidate,
        "skip_nat":     skip_nat,
    }


# ============================================================
# 4. 결과 분리 및 저장
# ============================================================
def split_mapped_unmapped(df: pd.DataFrame, debug_mode: bool):
    """매핑완료 / 미매핑 분리 및 컬럼 정리"""
    # 시간 기준 재정렬 + 작업 컬럼 제거
    df = df.sort_values(by=COL_TIME, kind="mergesort", na_position="last").reset_index(drop=True)
    df = df.drop(columns=["_cmd_clean", "_table", "_orig_row"], errors="ignore")

    mapped_mask = df[COL_SR].astype(str).str.strip() != ""
    df_mapped   = df[mapped_mask].copy()
    df_unmapped = df[~mapped_mask].copy()

    # 매핑완료 시트의 미매핑사유는 의미 없으므로 비움
    if COL_REASON in df_mapped.columns:
        df_mapped[COL_REASON] = ""

    # DEBUG_MODE=False 면 엑셀 출력에서 미매핑사유 컬럼 제거
    if not debug_mode:
        df_mapped   = df_mapped.drop(columns=[COL_REASON], errors="ignore")
        df_unmapped = df_unmapped.drop(columns=[COL_REASON], errors="ignore")

    return df_mapped, df_unmapped, mapped_mask


def save_main_xlsx(cfg: Config, df_mapped: pd.DataFrame):
    """메인 파일 저장 (매핑완료된 행만)"""
    with pd.ExcelWriter(cfg.output_file, engine="openpyxl") as writer:
        df_mapped.to_excel(writer, sheet_name=MAIN_SHEET_NAME, index=False)
    print(f"저장 완료 → {cfg.output_file} (시트: {MAIN_SHEET_NAME})")


def save_user_xlsx_files(cfg: Config, df_unmapped: pd.DataFrame) -> dict:
    """
    사용자명별로 미매핑 행을 개별 xlsx 파일로 저장.
    Returns: {user_label: (file_path, count)} 매핑
    """
    result = {}

    if df_unmapped.empty:
        print("\n[사용자별 미매핑 파일] 미매핑 행 없음")
        return result

    user_series = df_unmapped[COL_USER].fillna("").astype(str).str.strip()
    user_series = user_series.replace("", UNKNOWN_USER_LABEL)
    df_unmapped = df_unmapped.copy()
    df_unmapped["_user_key"] = user_series

    # 동일 safe_filename 으로 충돌하는 사용자명 처리
    used_paths = set()
    for user_label in df_unmapped["_user_key"].unique():
        sub = df_unmapped[df_unmapped["_user_key"] == user_label].drop(columns=["_user_key"])

        # 파일 경로 생성 (충돌 시 _2, _3 ... 접미사)
        path = cfg.user_output_file(user_label)
        suffix = 1
        while path in used_paths:
            suffix += 1
            path = cfg.admin_dir / f"{cfg.stem}-admin_{safe_filename(user_label)}_{suffix}.xlsx"
        used_paths.add(path)

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            sub.to_excel(writer, sheet_name=MAIN_SHEET_NAME, index=False)

        result[user_label] = (path, len(sub))

    return result


# ============================================================
# 5. 요약 출력
# ============================================================
def print_summary(
    cfg: Config,
    df: pd.DataFrame,
    mapped_mask: pd.Series,
    stats: dict,
    user_files: dict,
    elapsed: float,
):
    total      = len(df)
    filled     = int(mapped_mask.sum())
    unmapped_n = int((~mapped_mask).sum())

    print(f"\n총 {total}행 / SR번호 채워진 행: {filled} "
          f"({(filled / total * 100) if total else 0:.1f}%)")
    print(f"미매핑 행: {unmapped_n}건")
    print(
        f"미채움 사유 분포: "
        f"NO_TABLE={stats['no_table']}, "
        f"NO_DONOR/OUT_WIN={stats['no_candidate']}, "
        f"SKIP_NAT={stats['skip_nat']}"
    )

    if user_files:
        print("\n[사용자별 미매핑 파일]")
        for user_label, (path, cnt) in sorted(user_files.items()):
            print(f"  - {user_label:<20s} : {cnt:>5}건  →  {path.name}")

    print(f"\n소요 시간: {elapsed:.2f}초")
    print(
        f"  · 미매핑사유 컬럼: "
        f"{'포함 (DEBUG_MODE=True)' if cfg.debug_mode else '미포함 (DEBUG_MODE=False)'}"
    )
    print(f"로그 저장 → {cfg.log_file}")


# ============================================================
# 🚀 main
# ============================================================
def main():
    args = parse_args()
    cfg = Config(
        category=args.category.strip().lower(),
        app_name=args.app_name.strip(),
        debug_mode=args.debug,
    )
    cfg.ensure_dirs()

    # 로거 세팅 (디렉토리 생성 후)
    tee = FileOnlyTee(cfg.log_file, mode="w", encoding="utf-8")
    sys.stdout = tee
    start_ts = datetime.now()

    try:
        print(f"▶ CATEGORY        : {cfg.category}")
        print(f"▶ APP_NAME        : {cfg.app_name}")
        print(f"▶ INPUT  FILE     : {cfg.input_file}")
        print(f"▶ OUTPUT FILE     : {cfg.output_file}")
        print(f"▶ 시간 윈도우     : ±{TIME_WINDOW_SEC}초")
        print(f"▶ STRICT_AMBIGUOUS: {STRICT_AMBIGUOUS}")
        print(f"▶ DEBUG_MODE      : {cfg.debug_mode}  "
              f"({'엑셀에 미매핑사유 컬럼 포함' if cfg.debug_mode else '엑셀에서 미매핑사유 컬럼 제외'})\n")

        # 1) 로드
        df = load_and_prepare(cfg)

        # 2) 1차 추출
        extract_sr_stage1(df)

        # 3) 2차 전파
        stats = propagate_sr_stage2(df)

        # 4) 분리
        df_mapped, df_unmapped, mapped_mask = split_mapped_unmapped(df, cfg.debug_mode)

        # 5) 저장 (메인 + 사용자별)
        save_main_xlsx(cfg, df_mapped)
        user_files = save_user_xlsx_files(cfg, df_unmapped)

        # 6) 요약
        elapsed = (datetime.now() - start_ts).total_seconds()
        print_summary(cfg, df, mapped_mask, stats, user_files, elapsed)

    finally:
        sys.stdout = tee.terminal
        tee.close()


if __name__ == "__main__":
    main()
