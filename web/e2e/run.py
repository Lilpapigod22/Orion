"""Browser checks of the built window (ui/): python web/e2e/run.py — PASS/FAIL lines, exit code 1 on failure."""
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
HERE = Path(__file__).resolve().parent


def main() -> int:
    with tempfile.TemporaryDirectory() as profile:
        dom = subprocess.run(
            [str(EDGE), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
             "--allow-file-access-from-files", "--window-size=1180,760", "--virtual-time-budget=15000",
             "--dump-dom", (HERE / "interact.html").as_uri()],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180).stdout
    found = re.search(r'<pre id="result">(.*?)</pre>', dom, re.S)
    if not found:
        print("no result — the page did not finish")
        return 1
    lines = html.unescape(found[1]).splitlines()
    print("\n".join(lines))
    failed = [line for line in lines if line.startswith("FAIL")]
    print(f"passed {len(lines) - len(failed)}, failed {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
