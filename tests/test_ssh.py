# test_ssh.py
import sys
import os
import shlex


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import paramiko


# ============================================================
# 공통 함수
# ============================================================
def connect_ssh(host, port, user, key_path=None, password=None, timeout=8):
    """
    SSH 접속 공통 함수.
    - key_path 우선, 없으면 password 사용
    - 명세서 8: AutoAddPolicy 운영환경 검토 (테스트용이라 우선 적용)
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": host,
        "port": int(port),
        "username": user,
        "timeout": timeout,
        "banner_timeout": timeout,
        "auth_timeout": timeout,
    }

    if key_path:
        if not os.path.exists(key_path):
            raise FileNotFoundError(f"SSH 키 파일을 찾을 수 없습니다: {key_path}")
        connect_kwargs["key_filename"] = key_path
    elif password:
        connect_kwargs["password"] = password
    else:
        raise ValueError("key_path 또는 password 중 하나는 반드시 필요합니다.")

    client.connect(**connect_kwargs)
    return client


def run_remote(client, command, encoding="utf-8"):
    """
    원격 명령 실행 → (exit_code, stdout, stderr) 반환
    - encoding: 서버 파일명이 EUC-KR이면 "cp949"로 지정
    - 깨짐 방지를 위해 errors='replace'
    """
    stdin, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode(encoding, errors="replace")
    err = stderr.read().decode(encoding, errors="replace")
    return exit_code, out, err


def run_remote_bytes(client, command):
    """
    원격 명령 실행 → (exit_code, raw_stdout_bytes, raw_stderr_bytes) 반환
    - 인코딩이 섞여있어 디코딩이 애매할 때, 바이트 그대로 받아 직접 처리
    """
    stdin, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read()
    err = stderr.read()
    return exit_code, out, err


def decode_path_line(raw_bytes):
    """
    경로 한 줄(bytes)을 사람이 읽을 수 있게 best-effort 디코딩.
    UTF-8 → CP949 순으로 시도, 둘 다 실패하면 repr로 표시.
    """
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return repr(raw_bytes)


# ============================================================
# [1] A서버 (xferlog 로그서버) 테스트
# ============================================================
def test_server_a(cfg):
    print("\n" + "=" * 60)
    print(" [A서버] xferlog 로그서버 SSH 접속 테스트")
    print("=" * 60)
    print(f"▶ Host: {cfg['host']}:{cfg['port']} (user: {cfg['user']})")

    client = None
    try:
        client = connect_ssh(
            cfg["host"], cfg["port"], cfg["user"],
            key_path=cfg.get("key_path"), password=cfg.get("password")
        )
        print("✅ [1단계] SSH 연결 성공")

        code, out, err = run_remote(client, "whoami")
        print(f"   - 접속 계정 확인(whoami): {out.strip()}")

        log_dir = cfg["log_dir"]
        code, out, err = run_remote(
            client, f"test -d {shlex.quote(log_dir)} && echo OK || echo NO"
        )
        if "OK" in out:
            print(f"✅ [2단계] 로그 디렉토리 존재 확인: {log_dir}")
        else:
            print(f"⚠️ [2단계] 로그 디렉토리 없음/접근불가: {log_dir}")
            print(f"   - stderr: {err.strip()[:200]}")
            return

        ym = cfg["ym"]
        pattern = cfg["log_pattern"].replace("{ym}", ym)
        include_path = cfg["include_path"]
        include_flag = cfg["include_flag"]

        # ⚠️ 명령 인젝션 방지: 설정값 shlex.quote 처리 (명세서 8)
        cmd = (
            f"cd {shlex.quote(log_dir)} && "
            f"cat {pattern} | "                      # glob(*)이라 quote 안 함
            f"grep {shlex.quote(include_path)} | "
            f"grep {shlex.quote(include_flag)} | "
            f"head -n 5"
        )
        print(f"\n▶ 실행 명령(테스트, head 5줄):\n   {cmd}")

        code, out, err = run_remote(client, cmd)
        lines = [l for l in out.splitlines() if l.strip()]

        if lines:
            print(f"\n✅ [3단계] xferlog 수집 성공! (샘플 {len(lines)}줄)")
            for i, l in enumerate(lines, 1):
                print(f"   [{i}] {l[:120]}")
        else:
            print("\n⚠️ [3단계] 명령은 실행됐으나 매칭 결과가 0줄입니다.")
            # 권한 문제 vs 조건 문제 구분
            if err and ("Permission denied" in err or "cannot open" in err):
                print("   ⚠️ 권한 문제로 보입니다 (root 소유 파일). ACL/그룹/sudo 확인 필요.")
                print(f"   - stderr: {err.strip()[:200]}")
            else:
                print(f"   - ym({ym}), pattern({pattern}) 또는 grep 조건 확인 필요.")
                if err:
                    print(f"   - stderr: {err.strip()[:200]}")

    except Exception as e:
        print(f"\n❌ [실패] A서버 접속/실행 에러")
        print(f"   - 유형: {type(e).__name__}")
        print(f"   - 내용: {str(e)[:200]}")
    finally:
        if client:
            client.close()


# ============================================================
# [2] B서버 (NFS, EUC-KR 한글 폴더) 테스트
# ============================================================
def test_server_b(cfg):
    """
    핵심 전략:
      - 한글 경로를 Python str로 재조립해 셸에 재투입하지 않는다.
      - nfs_root(ASCII) + glob 패턴(ASCII)만 셸에 넘기고,
        실제 한글 폴더명은 원격 셸이 glob(*)으로 직접 전개한다.
      - 결과 bytes는 '표시용'으로만 디코딩한다.
    """
    print("\n" + "=" * 60)
    print(" [B서버] NFS(한글 폴더, EUC-KR) SSH 접속 테스트")
    print("=" * 60)
    print(f"▶ Host: {cfg['host']}:{cfg['port']} (user: {cfg['user']})")

    client = None
    try:
        # ── 1) 접속 ──────────────────────────────────────────
        client = connect_ssh(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            key_path=cfg.get("key_path"),
            password=cfg.get("password"),
        )
        print("✅ [1단계] SSH 접속 성공")

        nfs_root = cfg["nfs_root"]            # ASCII 경로
        path_globs = cfg["path_globs"]        # ASCII glob 리스트
        encoding = cfg.get("encoding", "cp949")

        # ── 2) 루트 접근 가능 여부 확인 ──────────────────────
        chk_cmd = f"test -d {shlex.quote(nfs_root)} && echo OK || echo NO"
        code, out, err = run_remote_bytes(client, chk_cmd)
        if out.strip() != b"OK":
            print(f"❌ [2단계] nfs_root 접근 불가: {nfs_root}")
            if err:
                print(f"   stderr: {decode_path_line(err)[:200]}")
            return
        print(f"✅ [2단계] nfs_root 확인: {nfs_root}")

        # ── 3) 누적 glob 단계별 탐색 (한글은 셸이 전개) ──────
        print("\n✅ [3단계] 한글 경로 단계별 탐색 (셸 glob 전개 방식):")

        accumulated = nfs_root               # 누적 경로 (한글은 *로만 표현)
        matches = []                         # 마지막 단계 매칭 결과(bytes 리스트)

        for i, g in enumerate(path_globs, start=1):
            accumulated = f"{accumulated}/{g}"

            # 셸이 glob을 전개 → 디렉토리만 NUL 구분으로 출력
            # (accumulated 는 ASCII만 포함하므로 인코딩 깨질 일 없음)
            cmd = (
                f"for d in {accumulated}/; do "
                f'[ -d "$d" ] && printf "%s\\0" "$d"; '
                f"done"
            )
            code, raw_out, raw_err = run_remote_bytes(client, cmd)
            matches = [m.rstrip(b"/") for m in raw_out.split(b"\x00") if m]

            if not matches:
                print(f"   [{i}] 패턴 '{g}' 매칭 없음 (누적: {accumulated})")
                # ── 디버깅: 직전 단계까지의 실제 폴더 덤프 ──
                parent = accumulated.rsplit("/", 1)[0]
                dbg = (
                    f"for d in {parent}/*/; do "
                    f'[ -d "$d" ] && printf "%s\\0" "$d"; done'
                )
                _, dbg_out, dbg_err = run_remote_bytes(client, dbg)
                cands = [m.rstrip(b"/") for m in dbg_out.split(b"\x00") if m]
                if not cands:
                    print(f"       (후보 0개 — 권한 문제 또는 경로 오류)")
                    if dbg_err:
                        print(f"       stderr: {decode_path_line(dbg_err)[:200]}")
                else:
                    print(f"       🔍 '{parent}' 하위 실제 폴더:")
                    for d in cands[:20]:
                        print(f"         - {decode_path_line(d)}")
                        print(f"           바이트: {d!r}")
                return

            print(f"   [{i}] 패턴 '{g}' → {len(matches)}개 매칭")
            for m in matches[:3]:
                print(f"       → {decode_path_line(m)}")
            if len(matches) > 3:
                print(f"       ... 외 {len(matches) - 3}개")

        # ── 4) 최종 월 폴더 아래 SR(하위) 폴더 목록 ──────────
        # 마지막 glob까지 통과한 경로 아래의 디렉토리들을 한 번에 수집
        full_glob = "/".join([nfs_root] + path_globs)
        sr_cmd = (
            f"for d in {full_glob}/*/; do "
            f'[ -d "$d" ] && printf "%s\\0" "$d"; done'
        )
        code, raw_out, raw_err = run_remote_bytes(client, sr_cmd)
        sr_dirs = [m.rstrip(b"/") for m in raw_out.split(b"\x00") if m]

        print(f"\n✅ [4단계] 최종 경로 하위 폴더: {len(sr_dirs)}개")
        if not sr_dirs:
            print("   (하위 폴더 없음 — 월 폴더가 비었거나 권한 문제)")
            if raw_err:
                print(f"   stderr: {decode_path_line(raw_err)[:200]}")
        else:
            for d in sr_dirs[:10]:
                print(f"   - {decode_path_line(d)}")
            if len(sr_dirs) > 10:
                print(f"   ... 외 {len(sr_dirs) - 10}개")

        # ── 5) (선택) 각 SR 폴더 안 파일 개수 요약 ──────────
        if sr_dirs:
            print(f"\n✅ [5단계] SR 폴더별 파일 개수:")
            # 파일 개수도 셸에서 집계 → 한글 경로를 클라이언트가 안 만짐
            cnt_cmd = (
                f"for d in {full_glob}/*/; do "
                f'[ -d "$d" ] || continue; '
                f'n=$(find "$d" -maxdepth 1 -type f | wc -l); '
                f'printf "%s\\t%s\\0" "$n" "$d"; '
                f"done"
            )
            code, cnt_out, cnt_err = run_remote_bytes(client, cnt_cmd)
            recs = [r for r in cnt_out.split(b"\x00") if r]
            for r in recs[:10]:
                # "개수<TAB>경로bytes" 구조
                try:
                    n_b, path_b = r.split(b"\t", 1)
                    n = n_b.decode("ascii", errors="replace")
                    print(f"   - [{n:>4} files] {decode_path_line(path_b)}")
                except ValueError:
                    print(f"   - (파싱 실패) {r!r}")

        print("\n✅ [완료] B서버 탐색 정상 종료")

    except ValueError as ve:
        print("\n❌ [실패] B서버 접속/실행 에러")
        print(f"   - 유형: ValueError")
        print(f"   - 내용: {ve}")
    except paramiko.AuthenticationException:
        print("\n❌ [실패] 인증 실패 (계정/비밀번호 확인)")
    except paramiko.SSHException as se:
        print(f"\n❌ [실패] SSH 오류: {se}")
    except Exception as e:
        print(f"\n❌ [실패] 예기치 못한 오류")
        print(f"   - 유형: {type(e).__name__}")
        print(f"   - 내용: {e}")
    finally:
        if client:
            client.close()
            print("🔌 B서버 연결 종료")

# ============================================================
# 실행부
# ============================================================
if __name__ == "__main__":
    print("🔍 SSH 접속 테스트 (A서버 xferlog / B서버 NFS)")

    server_a = {
        "host": "203.238.192.183",
        "port": 22,
        "user": "bpmu",
        "key_path": None,
        # ⚠️ 비밀번호 하드코딩 금지 권장: 환경변수로 분리
        "password": os.getenv("SERVER_A_PASS", "!0Ubpmbpm@@"),
        "log_dir": "/data/sftp_log_backup",
        "log_pattern": "*{ym}*",
        "ym": "202604",
        "include_path": "/tomcat8/webapps/ROOT",
        "include_flag": " _ i ",
    }

    server_b = {
        "host": "10.100.1.52",
        "port": 22,
        "user": "taksi",
        "key_path": None,
        "password": os.getenv("SERVER_B_PASS", "!0ehdak@"),
        # NFS 마운트 루트 (ASCII 구간까지)
        "nfs_root": "/doc_nfs/infosystem/Document",           # ← 실제 마운트 경로로 수정
        # 한글 폴더를 ASCII prefix + * 로 단계별 우회
        #   00. 프로그램이관 / PMS / 2026년 / 06월
        "path_globs": [
            "00.*",        # 00. 프로그램이관
            "PMS",         # PMS
            "2026*",       # 2026년
            "06*",         # 06월
        ],
        "encoding": "cp949",                # 서버 파일명 인코딩 (EUC-KR)
    }

    test_server_a(server_a)
    test_server_b(server_b)

    print("\n" + "=" * 60)
    print(" SSH 테스트 종료")
    print("=" * 60)
