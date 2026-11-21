import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# [설계 요약]
#  - base_dir + path_globs(ASCII) 를 셸이 glob 전개 → 한글 폴더는 '*'로 매칭.
#    (Python이 한글 경로를 직접 만들지 않으므로 인코딩 깨짐 원천 차단)
#  - 월 폴더가 '1월','03월','3월' 등 들쭉날쭉이어도 path_globs 마지막을 '*'로 두어
#    전부 긁고, SR 추출은 'OO월' 폴더 바로 아래 SR 폴더명에서 findall()[0] 로 처리.
#  - SR 폴더는 고정 깊이(= len(path_globs))에 존재한다고 전제.
# ─────────────────────────────────────────────────────────────────────────────

# SR 토큰: 'B05-20260210-004' (영문1 + 숫자2 - 숫자8 - 숫자3).
SR_PATTERN = re.compile(r"[A-Za-z]\d{2}-\d{8}-\d{3}")


@dataclass
class NfsConfig:
    host: str
    user: str
    base_dir: str
    path_globs: List[str]
    port: int = 22
    key_path: Optional[str] = None
    password: Optional[str] = None
    encoding: str = "cp949"
    debug: bool = False           # ★추가: 진단 출력 on/off


@dataclass
class NfsHit:
    sr_no: str
    nfs_path: str
    nfs_path_bytes: bytes
    nfs_mtime: datetime


def _shell_glob_escape(s: str) -> str:
    """glob 메타문자(* ? [ ])는 살리고, 나머지 셸 특수문자는 escape.
    예: 'ERP(HR)' -> 'ERP\\(HR\\)'

    주의: path_globs 는 ASCII 만 넣는 것을 원칙으로 한다(한글 폴더는 '*' 로 매칭).
          따라서 한글 예외(가-힣)는 불필요 → 제거하여 의도를 명확히 한다.
          만약 path_globs 에 한글을 직접 넣는다면 cmd.encode(encoding) 으로 보내므로
          \\w(유니코드) 가 한글을 단어문자로 보아 escape 대상에서 자동 제외된다.
    """
    return re.sub(r'([^\w*?\[\]/.\-])', r'\\\1', s)


def decode_path_line(raw_bytes: bytes, encoding: str = "cp949") -> str:
    # 파일시스템 인코딩(cp949) 우선. utf-8 을 먼저 두면 cp949 한글이
    # 우연히 디코딩되어 모지바케가 날 수 있으므로 순서 고정.
    for enc in (encoding, "euc-kr", "utf-8"):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes.decode("latin-1")


def build_index(cfg: NfsConfig) -> Dict[bytes, List[NfsHit]]:
    import paramiko

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": cfg.host,
        "port": int(cfg.port),
        "username": cfg.user,
        "timeout": 15,
        "banner_timeout": 15,
        "auth_timeout": 15,
    }
    if cfg.key_path:
        connect_kwargs["key_filename"] = cfg.key_path
    elif cfg.password:
        connect_kwargs["password"] = cfg.password
    else:
        raise ValueError("key_path 또는 password 중 하나는 반드시 필요합니다.")

    cli.connect(**connect_kwargs)

    index: Dict[bytes, List[NfsHit]] = defaultdict(list)
    try:
        full_glob = "/".join([cfg.base_dir] + cfg.path_globs)
        full_glob = _shell_glob_escape(full_glob)        # ERP(HR) 괄호 escape
        sr_part_index = len(cfg.path_globs)              # SR 폴더 part 의 0-base 인덱스
        log.debug("[NFS서버] glob 경로: %s", full_glob)
        # ★ bash 강제: dash 등에서 printf '\0'(NUL) 미지원 회피.
        # ★ find 에 2>/dev/null: 개별 폴더 권한오류로 루프 전체가 흔들리지 않게.
        inner = (
            f"for d in {full_glob}/*/; do "
            f'[ -d "$d" ] || continue; '
            f'find "$d" -type f -print0 2>/dev/null | '
            f'while IFS= read -r -d "" f; do '
            f'printf "%s\\t%s\\0" "$(stat -c %Y "$f")" "$f"; '
            f"done; "
            f"done"
        )
        cmd = f"bash -c {_sh_quote(inner)}"

        # 서버 FS 가 cp949 → cmd 를 cp949 bytes 로 직접 전송(한글 폴더 glob 매칭 보장).
        cmd_bytes = cmd.encode(cfg.encoding)
        stdin, stdout, stderr = cli.exec_command(cmd_bytes)
        raw = stdout.read()
        err = stderr.read()
        exit_code = stdout.channel.recv_exit_status()

        err_text = err.decode("utf-8", "replace").strip()
        if err_text:
            perm_lines = [l for l in err_text.splitlines()
                          if "permission denied" in l.lower() or "cannot open" in l.lower()]
            if perm_lines:
                log.warning("[NFS서버] 읽기 권한 오류 %d건 (host=%s): %s",
                            len(perm_lines), cfg.host, "; ".join(perm_lines[:3]))
            else:
                log.debug("[NFS서버] stderr (host=%s): %s", cfg.host, err_text[:300])

        if cfg.debug:
            log.debug("[NFS서버/debug] host=%s exit=%s raw_len=%d stderr=%s",
                      cfg.host, exit_code, len(raw), err_text[:200])
            shown = 0
            for rec in raw.split(b"\x00"):
                if b"\t" not in rec:
                    continue
                _, path_b = rec.split(b"\t", 1)
                rel = decode_path_line(path_b, cfg.encoding)
                rel = rel[len(cfg.base_dir):].lstrip("/") if rel.startswith(cfg.base_dir) else rel
                log.debug("  NFS경로: %s => SR=%s", rel.split("/"),
                          _extract_sr_no(path_b, cfg.base_dir, cfg.encoding, sr_part_index))
                shown += 1
                if shown >= 50:
                    break

        dropped = 0
        for rec in raw.split(b"\x00"):
            if not rec or b"\t" not in rec:
                continue
            epoch_b, path_b = rec.split(b"\t", 1)

            # mtime 은 항상 ASCII 숫자. 깨지면 데이터 이상 → 카운트 후 skip.
            try:
                epoch = float(epoch_b.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                dropped += 1
                continue

            sr_no = _extract_sr_no(path_b, cfg.base_dir, cfg.encoding, sr_part_index)
            if not sr_no:
                continue

            basename_b = path_b.rsplit(b"/", 1)[-1]
            index[basename_b].append(
                NfsHit(
                    sr_no=sr_no,
                    nfs_path=decode_path_line(path_b, cfg.encoding),
                    nfs_path_bytes=path_b,
                    nfs_mtime=datetime.fromtimestamp(epoch),
                )
            )

        if dropped:
            log.warning("[NFS서버] mtime 파싱 실패로 버린 레코드: %d건 (host=%s)", dropped, cfg.host)
    finally:
        cli.close()

    log.info("[NFS서버] 인덱스 구축 완료 host=%s | 파일 수=%d", cfg.host, len(index))
    log.debug("[NFS서버] 인덱스 샘플(상위10): %s",
              [k.decode(cfg.encoding, "replace") for k in list(index)[:10]])
    return index


def _sh_quote(s: str) -> str:
    """single-quote 로 안전하게 감싸기 (한글 포함 임의 문자열 대응).
    내부의 ' 만 '\\'' 로 escape.
    """
    return "'" + s.replace("'", "'\\''") + "'"

def _extract_sr_no(
    path_bytes: bytes,
    base: str,
    encoding: str,
    sr_part_index: int,
) -> Optional[str]:
    """
    SR 번호 추출 (고정 깊이 + 맨 앞 SR).

    [규칙]
      - SR 폴더는 항상 'OO월' 폴더 바로 아래(고정 깊이)에 있다.
        → rel 경로를 '/'로 쪼갰을 때 sr_part_index 위치의 part 가 SR 폴더명이다.
        → 그 part '한 개'에서만 SR을 찾는다(하위 파일경로/상위폴더 오염 차단).
      - 폴더명 안에 SR이 여러 개여도 '가장 앞에(먼저) 등장하는' SR을 채택.
        → 구분자('_'/공백)에 의존하지 않고 findall()[0] 로 맨 앞 SR을 뽑는다.

    [인자]
      path_bytes    : find 가 출력한 파일 경로(bytes, 디코딩 전).
      base          : nfs_root(=cfg.base_dir). rel 경로 산출용.
      encoding      : 파일시스템 인코딩(cp949 우선).
      sr_part_index : SR 폴더 part 의 0-base 인덱스(= len(cfg.path_globs)).

    [반환]
      맨 앞 SR 문자열 / 없으면 None.
    """
    path = decode_path_line(path_bytes, encoding)

    # base 를 떼어 상대경로로 변환. base 로 시작하지 않으면 그대로 사용.
    if path.startswith(base):
        rel = path[len(base):].lstrip("/")
    else:
        rel = path.lstrip("/")

    parts = rel.split("/")

    # 고정 깊이에 SR 폴더 part 가 존재하지 않으면 SR 폴더 경로가 아님.
    if len(parts) <= sr_part_index:
        return None

    sr_folder = parts[sr_part_index]      # ★ 고정 깊이의 SR 폴더명 한 개만 검사

    # 그 폴더명 안에서 등장 순서대로 SR 토큰을 모두 찾고, 맨 앞[0] 채택.
    #   예) "B06-20260427-001 B05-20260210-004 시스템개선 추가 반영건"
    #       → ['B06-20260427-001', 'B05-20260210-004'] → 'B06-20260427-001'
    matches = SR_PATTERN.findall(sr_folder)
    if matches:
        return matches[0]
