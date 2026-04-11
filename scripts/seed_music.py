"""
Download royalty-free background music for videos.
Run: python scripts/seed_music.py

This creates placeholder directories and provides instructions
for adding royalty-free music tracks.
"""
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parent.parent / "music" / "royalty_free"

CATEGORIES = {
    "terror": {
        "description": "Dark ambient, eerie, horror soundscapes",
        "suggestions": [
            "Dark ambient drone",
            "Eerie piano melody",
            "Horror suspense strings",
            "Creepy music box",
            "Tension buildup",
        ],
    },
    "historias": {
        "description": "Emotional ambient, storytelling background",
        "suggestions": [
            "Soft piano emotional",
            "Cinematic storytelling",
            "Gentle acoustic guitar",
            "Dramatic orchestral light",
            "Inspirational ambient",
        ],
    },
    "dinero": {
        "description": "Motivational, upbeat, business/finance vibes",
        "suggestions": [
            "Motivational corporate",
            "Upbeat success music",
            "Modern business background",
            "Tech startup vibes",
            "Confident hip-hop beat",
        ],
    },
}


def setup_music():
    print("=" * 50)
    print("Music Library Setup")
    print("=" * 50)

    for category, info in CATEGORIES.items():
        cat_dir = MUSIC_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        existing = list(cat_dir.glob("*.mp3")) + list(cat_dir.glob("*.wav"))

        print(f"\n--- {category.upper()} ---")
        print(f"Directory: {cat_dir}")
        print(f"Description: {info['description']}")
        print(f"Existing tracks: {len(existing)}")

        if not existing:
            print("No tracks found. Add .mp3 or .wav files to this directory.")
            print("Suggested search terms for royalty-free music:")
            for s in info["suggestions"]:
                print(f"  - {s}")

    print("\n" + "=" * 50)
    print("Where to find royalty-free music:")
    print("  - https://pixabay.com/music/ (Free, no attribution)")
    print("  - https://www.chosic.com/free-music/all/ (Various licenses)")
    print("  - https://freemusicarchive.org/ (Creative Commons)")
    print("  - https://incompetech.com/ (Kevin MacLeod, CC)")
    print("  - YouTube Audio Library (free for YouTube/TikTok)")
    print("\nAdd at least 5 tracks per category for variety.")
    print("Files should be .mp3 or .wav format.")
    print("=" * 50)


if __name__ == "__main__":
    setup_music()
