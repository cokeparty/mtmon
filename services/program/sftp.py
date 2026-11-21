import logging
import re
import shlex
import os
from dataclasses import dataclass
from datetime import datetime, time as dtime
from typing import List

log = logging.getLogger(__name__)

MONTHS = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

@dataclass
class XferRecord:
    log_month: int
    log_day: int
    log_time: dtime
    deploy_time: datetime
    file_name: str    # basename = 매핑 키
    full_path: str
    deployer: str

def build_command(log_dir, log_pattern, ym, include_path, include_flag) -> str:
    """wc 제거. 설정값은 shlex.quote (단 glob 패턴은 쉘 확장 필요)."""
    pattern = log_pattern.replace("{ym}", ym)   # ym=YYYYMM
    return (
        f"cd {shlex.quote(log_dir)} && "
        f"cat {pattern} | "
        f"grep {shlex.quote(include_path)} | "
        f"grep {shlex.quote(include_flag)}"
    )

# 형식: "Tue Apr  7 17:08:17 2026 1 ::ffff:1.2.3.4 703 /path/file b _ i r bpmu ftp 0 * c"
_LINE = re.compile(
    r"^\w{3}\s+(?P<mon>\w{3})\s+(?P<day>\d+)\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<year>\d{4})\s+"
    r"\d+\s+\S+\s+\d+\s+(?P<path>\S+)\s+"      # transfer-time, remote-host, size, filename
    r"\S+\s+\S+\s+\S+\s+\S+\s+(?P<user>\S+)"   # ... access-mode ... 이후 username
)

def parse_lines(raw: str, default_year: int) -> List[XferRecord]:
    out: List[XferRecord] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LINE.match(line)
        if not m:
            continue
        mon = MONTHS.get(m.group("mon"))
        day = int(m.group("day"))
        hh, mm, ss = map(int, m.group("time").split(":"))
        year = int(m.group("year")) or default_year
        dt = datetime(year, mon, day, hh, mm, ss)
        path = m.group("path")
        out.append(XferRecord(
            log_month=mon, log_day=day, log_time=dtime(hh, mm, ss),
            deploy_time=dt, full_path=path,
            file_name=os.path.basename(path),
            deployer=m.group("user"),
        ))
    return out
# ── HR 전용: "-rw-r--r-- 1 oraprod dba 864256 Mar 30 13:40 IS_DO01.fmb.20260330.134034"
_HR_LINE = re.compile(
    r"^[\-d][rwx-]{9}\s+"          # 권한
    r"\d+\s+"                       # 링크 수
    r"(?P<owner>\S+)\s+"            # 소유자 → deployer
    r"\S+\s+"                       # 그룹
    r"\d+\s+"                       # 크기
    r"\S+\s+\d+\s+\S+\s+"           # ls 날짜(Mar 30 13:40) — 미사용
    r"(?P<fname>\S+\.fmb)"          # ★ .fmb 까지 = 진짜 파일명(매핑 키)
    r"\.(?P<ts>\d{8}\.\d{6})\s*$"   # ★ .20260330.134034 = 배포 타임스탬프
)
def parse_lines_hr(raw: str, default_year: int) -> List[XferRecord]:
    """
    HR(Solaris) 전용 파서.
      입력: `ls -alR | grep fmb.YYYYMM` 출력
      - file_name  : '.fmb' 까지만 (IS_DO01.fmb)  ← SR 매핑 키
      - deploy_time: 파일명 끝 타임스탬프(YYYYMMDD.HHMMSS) → 초 단위 정확
      - deployer   : ls 소유자 컬럼(oraprod 등)
      - full_path  : ls -alR + grep 이라 경로 헤더가 없으므로 file_name 으로 대체
    """
    out: List[XferRecord] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _HR_LINE.match(line)
        if not m:
            # 'total 1234', 디렉토리 헤더, 매칭 안 되는 줄은 스킵
            continue

        ts = m.group("ts")                        # "20260330.134034"
        try:
            dt = datetime.strptime(ts, "%Y%m%d.%H%M%S")
        except ValueError:
            continue                               # 타임스탬프 깨진 줄 방어

        fname = m.group("fname")                   # "IS_DO01.fmb"
        out.append(XferRecord(
            log_month=dt.month,
            log_day=dt.day,
            log_time=dtime(dt.hour, dt.minute, dt.second),
            deploy_time=dt,
            file_name=fname,
            full_path=fname,                        # 경로 정보 없음 → basename 대체
            deployer=m.group("owner"),
        ))
    return out




# ── SR 전용: SFTP 서버 로그 (sftp-server) ─────────────────────
# 형식: "Jan 27 16:40:56 pdssrw01 sftp-server[1209399]: open "/home/ssru/.../file.jsp" flags WRITE,..."
_SR_LINE = re.compile(
    r"^(?P<mon>\w{3})\s+(?P<day>\d+)\s+(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"\S+\s+sftp-server\[\d+\]:\s+open\s+\"(?P<path>[^\"]+)\"\s+flags\s+\S+"
)

def parse_lines_sr(raw: str, default_year: int) -> List[XferRecord]:
    """
    SR SFTP 로그 전용 파서.
    - deploy_time: 로그 시각 (연도 없음 → default_year 사용)
    - full_path  : 따옴표 안의 전체 경로
    - file_name  : basename(full_path) ← SR 매핑 키
    - deployer   : /home/{user}/... 에서 추출한 OS 계정명
    """
    out: List[XferRecord] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SR_LINE.match(line)
        if not m:
            continue
        mon = MONTHS.get(m.group("mon"))
        if not mon:
            continue
        day = int(m.group("day"))
        hh, mm, ss = map(int, m.group("time").split(":"))
        dt = datetime(default_year, mon, day, hh, mm, ss)
        path = m.group("path")

        # deployer: /home/{user}/... 형태에서 OS 계정 추출
        parts = path.lstrip("/").split("/")
        if len(parts) >= 2 and parts[0] == "home":
            deployer = parts[1]
        else:
            deployer = "ssru"

        out.append(XferRecord(
            log_month=mon, log_day=day, log_time=dtime(hh, mm, ss),
            deploy_time=dt, full_path=path,
            file_name=os.path.basename(path),
            deployer=deployer,
        ))
    return out


LEGACY_SYSTEM_CODES = {"HR"}
def run_remote(cfg, command: str, system_code: str = None) -> str:
    """
    SSH 원격 실행 진입점(라우터).
      - 레거시 서버(예: HR/Solaris Sun_SSH): OS ssh로 우회 (SHA-1 ssh-rsa 지원)
      - 그 외 일반 서버: 기존 paramiko 사용

    분기 기준:
      1) system_code 가 LEGACY_SYSTEM_CODES 에 속하면 레거시
      2) (폴백) cfg.legacy_ssh 플래그가 truthy 면 레거시
    """

    # 대소문자/공백 방어 (HR, hr, " HR " 모두 허용)
    code_norm = (system_code or "").strip().upper()

    is_legacy = code_norm in LEGACY_SYSTEM_CODES or bool(getattr(cfg, "legacy_ssh", False))

    log.debug(
        "[FTP서버/SSH라우팅] host=%s port=%s system_code=%r | 경로=%s",
        cfg.ssh_host, cfg.ssh_port, system_code,
        "LEGACY(OS ssh)" if is_legacy else "paramiko",
    )

    if is_legacy:
        return _run_remote_legacy(cfg, command)
    else:
        return _run_remote_paramiko(cfg, command)


def _run_remote_paramiko(cfg, command: str) -> str:
    """
    일반 서버용. 기존 paramiko 로직 그대로 유지.
    """
    import paramiko

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs: dict = {
        "hostname": cfg.ssh_host,
        "port": cfg.ssh_port,
        "username": cfg.ssh_user,
        "timeout": 15,
    }
    if cfg.ssh_key_path:
        connect_kwargs["key_filename"] = cfg.ssh_key_path
    elif getattr(cfg, "ssh_password", None):
        connect_kwargs["password"] = cfg.ssh_password

    log.debug(
        "[FTP서버/paramiko] host=%s port=%s user=%s | 인증방식=%s",
        cfg.ssh_host, cfg.ssh_port, cfg.ssh_user,
        "KEY" if cfg.ssh_key_path else ("PASSWORD" if getattr(cfg, "ssh_password", None) else "없음"),
    )

    cli.connect(**connect_kwargs)
    try:
        stdin, stdout, stderr = cli.exec_command(command, timeout=30)
        stdin.channel.shutdown_write()  # 메뉴 입력 대기 방지
        output = stdout.read().decode("utf-8", errors="replace")
        err_text = stderr.read().decode("utf-8", errors="replace").strip()
        if err_text:
            perm_lines = [l for l in err_text.splitlines()
                          if "permission denied" in l.lower() or "cannot open" in l.lower()]
            if perm_lines:
                log.warning("[FTP서버] 읽기 권한 오류 %d건 (host=%s): %s",
                            len(perm_lines), cfg.ssh_host, "; ".join(perm_lines[:3]))
            else:
                log.debug("[FTP서버] stderr (host=%s): %s", cfg.ssh_host, err_text[:300])
        return output
    finally:
        cli.close()


def _run_remote_legacy(cfg, command: str) -> str:
    """
    레거시 서버용(HR/Solaris Sun_SSH). OS ssh + 비번 자동주입.
      - Linux 운영  : sshpass + ssh
      - Windows 개발: plink
    """
    import subprocess
    import platform
    import os

    use_key = bool(cfg.ssh_key_path)
    has_pw = bool(getattr(cfg, "ssh_password", None))

    if not use_key and not has_pw:
        raise ValueError("레거시 SSH 인증 정보 없음: ssh_key_path 또는 ssh_password 필요.")

    is_windows = platform.system() == "Windows"
    target = f"{cfg.ssh_user}@{cfg.ssh_host}"

    log.debug(
        "[FTP서버/legacy-ssh] host=%s port=%s user=%s | 인증=%s | OS=%s",
        cfg.ssh_host, cfg.ssh_port, cfg.ssh_user,
        "KEY" if use_key else "PASSWORD",
        platform.system(),
    )

    def _run(cmd, run_env):
        try:
            return subprocess.run(
                cmd,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=45, env=run_env,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as e:
            tool = "plink" if is_windows else ("sshpass" if not use_key else "ssh")
            raise RuntimeError(
                f"레거시 SSH 도구 미설치: {tool}. "
                f"(Windows: PuTTY/plink, Linux: apt install sshpass) 원본={e}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"레거시 SSH 타임아웃({e.timeout}s): host={cfg.ssh_host}") from e

    if is_windows:
        cmd = ["plink", "-ssh", "-P", str(cfg.ssh_port), "-batch"]
        if use_key:
            cmd += ["-i", cfg.ssh_key_path]      # plink은 .ppk 필요
        else:
            cmd += ["-pw", cfg.ssh_password]
        cmd += [target, command]
        result = _run(cmd, None)
    else:
        # 대상 서버(HR/Solaris)의 OpenSSH 가 구버전이면 'PubkeyAcceptedAlgorithms'(8.5+)를
        # 모른다 → 'Bad configuration option'. 구·신 모두 인식되는 'PubkeyAcceptedKeyTypes'를
        # 먼저 쓰고, 혹시 거부되면 신규 옵션명으로 1회 폴백한다.
        def _build_cmd(pubkey_opt: str):
            ssh_opts = [
                "-p", str(cfg.ssh_port),
                "-oHostKeyAlgorithms=+ssh-rsa,ssh-dss",
                "-oKexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1",
                f"-o{pubkey_opt}=+ssh-rsa",
                "-oStrictHostKeyChecking=no",
                "-oConnectTimeout=15",
            ]
            if use_key:
                return ["ssh", *ssh_opts, "-i", cfg.ssh_key_path, target, command], None
            env = os.environ.copy()
            env["SSHPASS"] = cfg.ssh_password
            return (["sshpass", "-e", "ssh", *ssh_opts,
                     "-oPubkeyAuthentication=no", target, command], env)

        cmd, run_env = _build_cmd("PubkeyAcceptedKeyTypes")
        result = _run(cmd, run_env)
        if (result.returncode != 0
                and "bad configuration option" in (result.stderr or "").lower()):
            log.warning("[FTP서버/legacy-ssh] 옵션명 폴백 재시도 host=%s (KeyTypes→Algorithms)",
                        cfg.ssh_host)
            cmd, run_env = _build_cmd("PubkeyAcceptedAlgorithms")
            result = _run(cmd, run_env)

    if result.returncode != 0:
        log.error("[FTP서버/legacy-ssh] 실패 host=%s rc=%s stderr=%s",
                  cfg.ssh_host, result.returncode, result.stderr.strip())
        raise RuntimeError(f"레거시 SSH 실패 (rc={result.returncode}): {result.stderr.strip()}")

    return result.stdout