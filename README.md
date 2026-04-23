# ViralStack

> **v1.1** — see [CHANGELOG.md](CHANGELOG.md) for the full changelog. Highlights: **multi-LLM script generation** (Gemini · OpenAI · Claude · OpenRouter · Groq · DeepSeek · Together · Mistral · Ollama), tabbed dashboard with `/api/llm/providers` health view, dynamic accounts via `config/accounts.json`, optional API-key auth, multi-channel notifications (Slack/Telegram/webhook), automatic SQLite backups, audit log, hard pipeline timeouts, per-account quality thresholds, blackout dates, weekend skip, `/health` endpoint, ~60 new env-tunable settings, GitHub-ready (CI, issue/PR templates, SECURITY/CONTRIBUTING/COC), and many bug fixes.

An open-source AI-powered system that automates the creation and publishing of short-form content for TikTok and YouTube. From idea generation to video production and upload — fully autonomous, scalable, and customizable.

The system manages **3 independent accounts** (or as many as you configure), generates scripts with the LLM provider of your choice, creates images with Imagen 4.0, narrates with TTS, adds subtitles, composes the final video, and publishes to both platforms simultaneously.

---

## 🤖 Multi-LLM Script Generation (NEW in v1.1)

Configure a **fallback chain** in `.env` and ViralStack will try each provider in order until one returns a valid script:

```env
SCRIPT_PROVIDER_CHAIN=gemini,openai,anthropic,openrouter,groq
```

| Provider | Free tier | Speed | Quality | Setup |
|---|---|---|---|---|
| **gemini** | ✅ | medium | high | `VERTEX_AI_API_KEY` o `GEMINI_API_KEYS` |
| **openai** | ❌ | medium | very high | `OPENAI_API_KEYS` |
| **anthropic** | ❌ | medium | very high | `ANTHROPIC_API_KEYS` |
| **openrouter** | partial | varies | varies | `OPENROUTER_API_KEYS` (acceso a 100+ modelos) |
| **groq** | ✅ | ⚡ very fast | high | `GROQ_API_KEYS` |
| **deepseek** | ❌ | medium | high | `DEEPSEEK_API_KEYS` |
| **together** | partial | medium | high | `TOGETHER_API_KEYS` |
| **mistral** | partial | medium | high | `MISTRAL_API_KEYS` |
| **ollama** | ✅ local | depends on hw | depends on model | `OLLAMA_ENABLED=true` |

Each provider supports **multiple keys separated by commas** for automatic rotation, and **multiple models** that get tried in order. View live status of every provider at the **LLM Providers** tab of the dashboard or via `GET /api/llm/providers`.

---


## What It Does

1. **Generates a script** using Google Gemini (with anti-repetition — it remembers the last 50 topics)
2. **Creates images** with Imagen 4.0 / Gemini Flash Image based on the script's visual descriptions
3. **Narrates the script** with Gemini TTS (or Microsoft Edge TTS as a free fallback)
4. **Adds subtitles** automatically using Whisper (local, no API cost)
5. **Composes the video** with FFmpeg (Ken Burns effect, crossfades, background music, burned subtitles)
6. **Quality-checks the video** with Gemini (optional, requires `GOOGLE_AI_API_KEY`) — if it scores below threshold, it retries from step 1
7. **Backs up to Google Drive** automatically
8. **Publishes to TikTok and YouTube Shorts** in parallel

> Videos are scheduled at random times (e.g. 11:38, 19:27) to avoid bot detection.

---

## Requirements

Before starting, make sure you have:

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **FFmpeg** — [ffmpeg.org](https://ffmpeg.org/download.html) or run `python scripts/setup_ffmpeg.py`
- **Google Cloud account** (free tier works, $300 credit for new accounts) — [console.cloud.google.com](https://console.cloud.google.com)
- A **TikTok account** (one per niche you want to automate)
- A **YouTube channel** (one per niche you want to automate)
- A **Discord server** (optional, for remote control and alerts)

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/viralstack.git
cd viralstack
pip install -r requirements.txt
```

### 2. Configure your environment

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in your credentials.
The file has detailed comments explaining **where to get each value**.

> **Minimum required**: `VERTEX_AI_API_KEY` — everything else is optional.

### 3. Set up FFmpeg

```bash
python scripts/setup_ffmpeg.py
```

Or install it manually and set the path in `.env` under `FFMPEG_PATH`.

### 4. Add background music

Place royalty-free `.mp3` files in the appropriate folders:

```
music/royalty_free/
├── terror/      ← Dark ambient, suspense tracks
├── historias/   ← Cinematic, documentary tracks
└── dinero/      ← Inspirational, motivational tracks
```

Or run `python scripts/download_music.py` to download from YouTube playlists (you'll need to add playlist URLs to the script first).

### 5. Set up TikTok cookies (to publish to TikTok)

1. Install the **"Get cookies.txt LOCALLY"** browser extension (Chrome/Firefox)
2. Log in to TikTok in your browser
3. Go to `tiktok.com`, click the extension → Export as Netscape format
4. Save to `storage/cookies/terror_cookies.txt` (or `historias_`, `dinero_`)

Or run `python scripts/export_cookies.py` for automated extraction.

### 6. Set up YouTube OAuth (to publish YouTube Shorts)

First, create OAuth credentials in Google Cloud Console (see `.env.example` for instructions), then:

```bash
python scripts/setup_youtube.py terror
python scripts/setup_youtube.py historias
python scripts/setup_youtube.py dinero
```

A browser window will open — log in with the corresponding Google account.

### 7. Set up Gmail auto-replies (optional)

```bash
python scripts/setup_gmail.py terror
python scripts/setup_gmail.py historias
python scripts/setup_gmail.py dinero
```

### 8. Run the bot manually (to test)

```bash
python easyrun.py
```

This opens a simple GUI with buttons for each account. Click a button to generate and publish one video immediately.

### 9. Run in production (scheduled)

```bash
python main.py
```

This runs continuously, publishing videos at scheduled random times throughout the day.

---

## Account Configuration

By default the project is set up for 3 content niches. You can rename them, remove some, or add more by editing `config/platforms.json` and the prompts in `config/prompts/`.

| Account | Niche | Default content style |
|---------|-------|----------------------|
| `terror` | Horror / Suspense | Psychological horror, first-person confessions, suspenseful stories with a twist |
| `historias` | Real curiosities | Bizarre real events that sound impossible (not horror, not paranormal) |
| `dinero` | Finance | Investment tips with concrete numbers, financial mistakes, actionable strategies |

You can customize the style and tone of each niche by editing:
- `config/prompts/terror.yaml`
- `config/prompts/historias.yaml`
- `config/prompts/dinero.yaml`

---

## Dashboard

Once running, open `http://localhost:8000` to see:
- All videos with their status, quality score, TikTok URL, YouTube URL
- Stats per account and platform
- Email activity
- Step-by-step pipeline logs per video

---

## Discord Bot (optional but recommended)

The Discord bot lets you control the system remotely from your phone.

### Commands

| Command | Description |
|---------|-------------|
| `/status` | System overview — videos published, accounts, platform status |
| `/publish <account> [platform]` | Force publish a video right now |
| `/toggle <account> <platform>` | Enable/disable TikTok or YouTube for an account |
| `/config` | View current configuration |
| `/schedule` | View upcoming scheduled videos |
| `/emails [account]` | View recent email activity |

### Automatic alerts

The bot sends alerts to your configured channel:
- **Blue** (Info): Video published successfully
- **Orange** (Warning): Quality check failed, retrying
- **Red** (Error): Pipeline step failed
- **Red + mention** (Urgent): Legal email received, all API keys down

### Setup

1. Create an app at [discord.com/developers/applications](https://discord.com/developers/applications)
2. Go to "Bot" → Reset Token → copy it → paste in `.env` as `DISCORD_BOT_TOKEN`
3. Go to OAuth2 → URL Generator → check "bot" + "applications.commands" → invite to your server
4. Enable Developer Mode in Discord (Settings → Advanced), then right-click to copy IDs
5. Fill in `DISCORD_GUILD_ID`, `DISCORD_OWNER_ID`, `DISCORD_ALERTS_CHANNEL_ID`, `DISCORD_STATS_CHANNEL_ID` in `.env`

---

## Deployment on a VPS

### Option A: Docker (recommended)

```bash
cp .env.example .env
nano .env                    # Fill in your credentials
docker compose up -d         # Start
docker compose logs -f       # View logs
```

### Option B: Bare metal (Ubuntu/Debian)

```bash
bash deploy.sh               # Full server setup
nano .env                    # Fill in your credentials
sudo systemctl start viralstack
sudo systemctl status viralstack
```

### Post-deploy checklist

- [ ] `VERTEX_AI_API_KEY` set in `.env` (required)
- [ ] YouTube OAuth: `python scripts/setup_youtube.py {terror,historias,dinero}`
- [ ] TikTok cookies: `python scripts/export_cookies.py` or export manually
- [ ] Gmail OAuth: `python scripts/setup_gmail.py {terror,historias,dinero}` (optional)
- [ ] Google Drive: `config/service_account.json` placed (optional)
- [ ] Music files: added to `music/royalty_free/{terror,historias,dinero}/`
- [ ] Test manually: `python easyrun.py`
- [ ] Check dashboard: `http://YOUR_VPS_IP:8000`
- [ ] Check Discord: `/status`

---

## Project Structure

```
├── main.py                     # Production entry point (scheduler)
├── easyrun.py                  # GUI launcher for manual testing
├── config/
│   ├── settings.py             # All configuration (reads from .env)
│   ├── platforms.json          # Enable/disable TikTok & YouTube per account
│   └── prompts/
│       ├── terror.yaml         # Horror niche prompts (EN + ES)
│       ├── historias.yaml      # Real stories niche prompts (EN + ES)
│       └── dinero.yaml         # Finance niche prompts (EN + ES)
├── core/
│   ├── db.py                   # SQLite database
│   ├── models.py               # Data models
│   ├── vertex_client.py        # Central Vertex AI client
│   ├── scheduler.py            # Video scheduling
│   ├── key_rotation.py         # Gemini model rotation
│   └── discord_alerts.py       # Discord notifications
├── pipeline/
│   ├── orchestrator.py         # 8-step pipeline coordinator
│   ├── script_gen.py           # Script generation + deduplication
│   ├── video_gen.py            # Image generation (Imagen 4.0)
│   ├── tts.py                  # Text-to-speech
│   ├── subtitles.py            # Whisper subtitles
│   ├── compositor.py           # FFmpeg video composition
│   ├── quality_check.py        # Gemini quality scoring
│   ├── drive_upload.py         # Google Drive backup
│   ├── tiktok_publish.py       # TikTok upload
│   └── youtube_publish.py      # YouTube upload
├── bot/                        # Discord bot
├── email_agent/                # Gmail auto-reply agent
├── dashboard/                  # FastAPI web dashboard
├── scripts/                    # Setup utilities
├── music/royalty_free/         # Background music (add your own MP3s here)
├── storage/
│   ├── cookies/                # TikTok session cookies (gitignored)
│   └── output/                 # Generated videos (gitignored)
├── .env.example                # Configuration template — copy to .env
├── requirements.txt
├── Dockerfile
└── docker-compose.yaml
```

---

## Tech Stack & Costs

| Component | Technology | Cost |
|-----------|-----------|------|
| Script generation | Gemini 2.5 Flash (Vertex AI) | Pay-as-you-go |
| Image generation | Imagen 4.0 Fast (Vertex AI) | Pay-as-you-go |
| Text-to-speech | Gemini TTS (Vertex AI) / Edge TTS | Pay-as-you-go / Free |
| Quality check | Gemini (Google AI) | Free tier |
| Subtitles | faster-whisper (local) | Free |
| Video processing | FFmpeg | Free |
| Cloud backup | Google Drive API | Free (15GB/account) |
| TikTok publishing | tiktok-uploader + Playwright | Free |
| YouTube publishing | YouTube Data API v3 | Free (6 uploads/account/day) |
| Scheduling | APScheduler | Free |
| Database | SQLite | Free |
| Dashboard | FastAPI | Free |
| Discord bot | discord.py | Free |
| Email agent | Gmail API | Free |

> Typical cost for 6 videos/day: ~$0.50–$3.00 USD per day depending on video length and model usage.
> Google Cloud gives **$300 free credit** to new accounts.

---

## Troubleshooting

**Videos are not publishing to TikTok**
- Your cookies have likely expired (they last ~2 months). Re-export them using the browser extension.

**Quality check always fails**
- Lower `QUALITY_THRESHOLD` in `.env` (e.g., `5.0` instead of `6.0`)
- Or increase `MAX_RETRIES_PER_VIDEO`

**Image generation fails**
- Check that Vertex AI API is enabled and your `VERTEX_AI_API_KEY` is correct
- The system will automatically fall back to Gemini Flash Image if Imagen quota is exhausted

**FFmpeg not found**
- Run `python scripts/setup_ffmpeg.py` or set the full path in `FFMPEG_PATH`

**YouTube upload fails**
- OAuth tokens expire. Re-run `python scripts/setup_youtube.py <account>`

**Discord bot doesn't respond**
- Make sure `DISCORD_GUILD_ID` and `DISCORD_OWNER_ID` match your actual server and user IDs
- Only the owner (set in `DISCORD_OWNER_ID`) can execute slash commands

---

## Publishing to GitHub

The repository is GitHub-ready: includes CI workflow (lint + tests + Docker build), bug-report and feature-request templates, a PR template, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and a strengthened `.gitignore` that blocks `.env`, OAuth tokens, cookies, service-account JSONs, `.pem`/`.key` files, SQLite backups, and music files.

```bash
# 1. Make absolutely sure no secrets are tracked
git status
git ls-files | grep -E '\.env$|service_account|cookies\.txt|token\.json' && echo "STOP - secrets tracked!"

# 2. Initialize and push
git init
git add .
git commit -m "ViralStack v1.1.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/viralstack.git
git push -u origin main
```

Open a Security Advisory via the **Security → Advisories** tab if you ever discover a vulnerability — see [SECURITY.md](SECURITY.md).

---

## License

MIT License — use freely, attribution appreciated.
