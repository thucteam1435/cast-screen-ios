import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist", "CastScreenAirPlayAgent")


def main():
    if not shutil.which("pyinstaller"):
        raise SystemExit("PyInstaller is required. Install with: python -m pip install pyinstaller")

    os.makedirs(os.path.dirname(DIST), exist_ok=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "CastScreenAirPlayAgent",
        "--hidden-import=psutil",
        "--hidden-import=zeroconf",
        os.path.join(ROOT, "web", "airplay_agent.py"),
    ]
    print("Building CastScreenAirPlayAgent...")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    dst_engine = os.path.join(DIST, "engine")
    src_engine = os.path.join(ROOT, "engine")
    if os.path.exists(dst_engine):
        shutil.rmtree(dst_engine)
    shutil.copytree(src_engine, dst_engine)

    docs = [
        os.path.join(ROOT, "web", "AIRPLAY_AGENT_GUIDE.md"),
        os.path.join(ROOT, "web", "AIRPLAY_AGENT_PRIVACY.md"),
    ]
    for doc in docs:
        if os.path.exists(doc):
            shutil.copy2(doc, os.path.join(DIST, os.path.basename(doc)))

    print(f"Output: {DIST}")


if __name__ == "__main__":
    main()
