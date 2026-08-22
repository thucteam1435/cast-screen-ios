import os
import sys
import shutil
import subprocess

try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import customtkinter

def build():
    print("=" * 60)
    print("BAT DAU DONG GOI CAST SCREEN PRO THANH FILE .EXE")
    print("=" * 60)

    project_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(project_dir, "dist")
    build_dir = os.path.join(project_dir, "build")
    output_app_dir = os.path.join(dist_dir, "CastScreenPro")

    # Get CustomTkinter path
    ctk_path = os.path.dirname(customtkinter.__file__)
    print(f"[*] CustomTkinter package path: {ctk_path}")

    # PyInstaller arguments
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name", "CastScreenPro",
        f"--add-data={ctk_path}{os.pathsep}customtkinter",
        "--hidden-import=customtkinter",
        "--hidden-import=win32gui",
        "--hidden-import=win32con",
        "--hidden-import=win32api",
        "--hidden-import=win32process",
        "--hidden-import=psutil",
        "--hidden-import=PIL",
        "--hidden-import=PIL._tkinter_finder",
        "app.py"
    ]

    print("[*] Dang bien dich voi PyInstaller...")
    print("Command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=project_dir)
    if res.returncode != 0:
        print("[!] LOI: Bien dich PyInstaller that bai!")
        return False

    print("\n[*] Dang sao chep cac tep engine va tai nguyen can thiet vao thu muc dist...")

    # Copy engine directory
    src_engine = os.path.join(project_dir, "engine")
    dst_engine = os.path.join(output_app_dir, "engine")
    if os.path.exists(dst_engine):
        shutil.rmtree(dst_engine)
    shutil.copytree(src_engine, dst_engine)
    print("  [OK] Da sao chep thu muc engine/ (GStreamer & UxPlay Binaries)")

    # Ensure C++ Runtime DLLs are present in engine/bin
    system32 = r"C:\Windows\System32"
    essential_dlls = [
        "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_codecvt_ids.dll",
        "msvcp140_atomic_wait.dll", "vcomp140.dll", "vcruntime140.dll", "vcruntime140_1.dll",
        "d3dcompiler_47.dll"
    ]
    dst_bin = os.path.join(dst_engine, "bin")
    for d in essential_dlls:
        src_dll = os.path.join(system32, d)
        if os.path.exists(src_dll):
            shutil.copy2(src_dll, os.path.join(dst_bin, d))
            # Also copy to root of dist for complete safety
            shutil.copy2(src_dll, os.path.join(output_app_dir, d))
    print("  [OK] Da dong goi day du bo thu vien C++ Runtime (msvcp140 & d3dcompiler)")

    # Copy helper files
    helper_files = ["settings.json", "fix_hotspot_firewall.bat", "optimize_latency.bat", "README.md"]
    for f in helper_files:
        src_f = os.path.join(project_dir, f)
        if os.path.exists(src_f):
            shutil.copy2(src_f, os.path.join(output_app_dir, f))
            print(f"  [OK] Da sao chep {f}")

    print("\n" + "=" * 60)
    print("DONG GOI THANH CONG 100%!")
    print(f"Thu muc ung dung hoan chinh: {output_app_dir}")
    print(f"File thuc thi chinh: {os.path.join(output_app_dir, 'CastScreenPro.exe')}")
    print("=" * 60)
    return True

if __name__ == "__main__":
    build()
