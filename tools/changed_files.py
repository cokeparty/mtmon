"""운영 반영용 — 지난 배포 이후 바뀐 파일만 골라 zip 으로 묶는다.

  python tools/changed_files.py                 # 마지막 배포 태그(deploy-*) 이후 변경분
  python tools/changed_files.py deploy-20261121 # 지정 태그 이후
  python tools/changed_files.py --tag           # 묶은 뒤 현재 커밋에 배포 태그(deploy-YYYYMMDD-HHMM) 추가

결과:
  dist/patch-YYYYMMDD-HHMM.zip   바뀐 파일 (서버의 /opt/mtmon 에 그대로 풀면 됨)
  dist/patch-YYYYMMDD-HHMM.txt   바뀐 파일 목록 + 삭제해야 할 파일 목록

  * 커밋된 변경만 대상입니다 (커밋 안 한 수정은 경고만 표시).
  * .env, logs/, venv/, wheelhouse/, _mine/, spec/, tests/ 는 넣지 않습니다.
  * requirements.txt 가 바뀌었으면 wheelhouse 갱신 + pip 설치가 필요하다고 알려줍니다.
"""
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = (".env", "logs/", "venv/", "wheelhouse/", "_mine/", "spec/", "tests/", "dist/", ".git")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def main(argv: list[str]) -> int:
    make_tag = "--tag" in argv
    args = [a for a in argv[1:] if a != "--tag"]
    base = args[0] if args else (git("tag", "--list", "deploy-*", "--sort=-creatordate").split() or [""])[0]
    if not base:
        print("배포 태그(deploy-*)가 없습니다. 기준 커밋/태그를 지정하세요. 예) python tools/changed_files.py HEAD~5")
        return 1

    dirty = git("status", "--porcelain").strip()
    if dirty:
        print("※ 커밋하지 않은 변경이 있습니다 (이번 묶음에는 포함되지 않음):\n" + dirty + "\n")

    changed, deleted = [], []
    for line in git("diff", "--name-status", "--no-renames", f"{base}..HEAD").splitlines():
        status, path = line.split("\t", 1)
        if path.startswith(EXCLUDE):
            continue
        (deleted if status == "D" else changed).append(path)

    if not changed and not deleted:
        print(f"{base} 이후 바뀐 파일이 없습니다.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    zpath, tpath = out / f"patch-{stamp}.zip", out / f"patch-{stamp}.txt"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in changed:
            z.write(ROOT / p, p)

    notes = [f"기준: {base} → {git('rev-parse', '--short', 'HEAD').strip()}", "",
             f"[업로드할 파일 {len(changed)}개]", *changed, ""]
    if deleted:
        notes += [f"[서버에서 삭제할 파일 {len(deleted)}개]", *deleted, ""]
    if "requirements.txt" in changed:
        notes += ["[주의] requirements.txt 변경 → 인터넷 PC에서 wheelhouse 갱신 후 서버에서",
                  "       pip install --no-index --find-links=./wheelhouse -r requirements.txt", ""]
    if any(p.startswith("migrations/") for p in changed):
        notes += ["[알림] DB 구조 변경 포함 → 앱 재시작 시 자동 적용됩니다 (AUTO_MIGRATE=true)", ""]
    notes += ["반영 후: sudo systemctl restart mtmon"]
    tpath.write_text("\n".join(notes), encoding="utf-8")
    print("\n".join(notes))
    print(f"\n→ {zpath}\n→ {tpath}")

    if make_tag:
        tag = f"deploy-{stamp}"
        git("tag", tag)
        print(f"배포 태그 추가: {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
