"""
Download background music tracks from YouTube playlists for each niche.
Converts to mp3.
"""
import os
import sys
import io
import subprocess
import re
from pathlib import Path

# Fix Windows console encoding for emoji-heavy YouTube titles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "music" / "royalty_free"

PLAYLISTS = {
    "terror": {
        "url": "https://www.youtube.com/playlist?list=PLXU4rk4JoNOt-FGYEbO5Ul6AOYQor9vE3",
        "max_videos": 10,
    },
    "dinero": {
        "url": "https://www.youtube.com/playlist?list=PLN1aszkXjuppFutgQlJX5obJ4WdSCBuMs",
        "max_videos": 10,
    },
    "historias": {
        "url": "https://www.youtube.com/playlist?list=PL-xVUW9dZgbc30qEMbqKoxsjx6IgY2Ldx",
        "max_videos": 10,
    },
}


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|#\'\u200b]', "", name)
    name = re.sub(r'[^\x00-\x7F]+', '', name)  # strip non-ASCII
    name = re.sub(r'\s+', "_", name.strip())
    name = re.sub(r'_+', '_', name).strip("_")
    return name[:80] if name else "track"


def download_playlist(account: str, playlist_url: str, max_videos: int):
    from pytubefix import Playlist, YouTube

    out_dir = MUSIC_DIR / account
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Downloading: {account.upper()} ({max_videos} tracks)")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    try:
        pl = Playlist(playlist_url)
        video_urls = list(pl.video_urls)[:max_videos]
        print(f"  Found {len(video_urls)} videos in playlist")
    except Exception as e:
        print(f"  ERROR fetching playlist: {e}")
        return 0

    downloaded = 0
    for idx, url in enumerate(video_urls, 1):
        try:
            print(f"\n  [{idx}/{len(video_urls)}] {url}")
            # No progress callback to avoid encoding issues
            yt = YouTube(url)
            title = sanitize_filename(yt.title)
            if not title:
                title = f"track_{idx}"

            final_path = out_dir / f"{title}.mp3"
            if final_path.exists():
                print(f"    Already exists: {final_path.name}")
                downloaded += 1
                continue

            audio_stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
            if not audio_stream:
                print(f"    No audio stream — skipping")
                continue

            safe_title = repr(yt.title)[1:-1][:60]
            print(f"    Title: {safe_title}")
            print(f"    Bitrate: {audio_stream.abr}")

            temp_name = f"_temp_{account}_{idx}"
            temp_file = audio_stream.download(output_path=str(out_dir), filename=temp_name)
            temp_path = Path(temp_file)

            print(f"    Converting to mp3...")
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(temp_path),
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-ab", "192k",
                    "-ar", "44100",
                    str(final_path),
                ],
                capture_output=True, text=True, timeout=120,
            )

            try:
                temp_path.unlink()
            except Exception:
                pass

            if result.returncode != 0:
                print(f"    FFmpeg error: {result.stderr[:300]}")
                continue

            size_mb = final_path.stat().st_size / (1024 * 1024)
            downloaded += 1
            print(f"    OK: {final_path.name} ({size_mb:.1f} MB)")

        except Exception as e:
            err_msg = str(e).encode("ascii", errors="replace").decode()
            print(f"    ERROR: {err_msg}")
            continue

    print(f"\n  {account.upper()}: {downloaded}/{len(video_urls)} tracks downloaded")
    return downloaded


def main():
    total = 0
    for account, cfg in PLAYLISTS.items():
        try:
            count = download_playlist(account, cfg["url"], cfg["max_videos"])
            total += count
        except Exception as e:
            err_msg = str(e).encode("ascii", errors="replace").decode()
            print(f"  FATAL ERROR for {account}: {err_msg}")

    print(f"\n{'='*60}")
    print(f"  DONE - {total} total tracks downloaded")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
