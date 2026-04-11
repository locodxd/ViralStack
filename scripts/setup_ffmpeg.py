"""
Download and setup FFmpeg for Windows.
Run this once: python scripts/setup_ffmpeg.py
"""
import os
import sys
import zipfile
import urllib.request
import shutil
from pathlib import Path

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
FFMPEG_DIR = TOOLS_DIR / "ffmpeg"


def download_ffmpeg():
    print("=" * 50)
    print("FFmpeg Setup for TikTok Automation")
    print("=" * 50)

    if (FFMPEG_DIR / "bin" / "ffmpeg.exe").exists():
        print("FFmpeg already installed at:", FFMPEG_DIR / "bin" / "ffmpeg.exe")
        return

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = TOOLS_DIR / "ffmpeg.zip"

    print(f"Downloading FFmpeg from GitHub...")
    print(f"URL: {FFMPEG_URL}")
    print("This may take a few minutes...")

    urllib.request.urlretrieve(FFMPEG_URL, str(zip_path))
    print(f"Downloaded: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")

    print("Extracting...")
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        zf.extractall(str(TOOLS_DIR))

    # Find the extracted directory (name varies)
    extracted = None
    for item in TOOLS_DIR.iterdir():
        if item.is_dir() and "ffmpeg" in item.name.lower() and item != FFMPEG_DIR:
            extracted = item
            break

    if extracted:
        if FFMPEG_DIR.exists():
            shutil.rmtree(str(FFMPEG_DIR))
        extracted.rename(FFMPEG_DIR)

    # Cleanup zip
    zip_path.unlink()

    # Verify
    ffmpeg_exe = FFMPEG_DIR / "bin" / "ffmpeg.exe"
    if ffmpeg_exe.exists():
        print(f"\nFFmpeg installed successfully!")
        print(f"Path: {ffmpeg_exe}")
        os.system(f'"{ffmpeg_exe}" -version')
    else:
        print("ERROR: FFmpeg binary not found after extraction.")
        print("Please download manually from https://ffmpeg.org/download.html")
        print(f"Extract to: {FFMPEG_DIR / 'bin'}")
        sys.exit(1)


if __name__ == "__main__":
    download_ffmpeg()
