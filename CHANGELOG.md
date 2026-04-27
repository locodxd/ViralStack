# Changelog

## v1.2.0 - 2026-04-27

### New features

- **Platform registry**: `config/platform_registry.json` defines publish targets. TikTok and YouTube remain built-in; Instagram Reels is registered as a webhook/manual platform and disabled by default.
- **Generic platform publishing**: new dispatcher in `pipeline/platform_publishers.py` stores per-platform results, errors, URLs, and skipped states without adding new columns for every platform.
- **Dashboard platform controls**: new Platforms tab to enable/disable any registered platform per account.
- **Custom-account template**: `config/accounts.example.json` documents per-account voice, prompt, thresholds, hashtags, image style, paths, and platform toggles.
- **Generic platform stats**: dashboard, health, audit payloads, and Discord stats now include dynamic platform data.

### Bug fixes

- Fixed custom YouTube/Gmail token resolution; setup scripts now accept any registered account.
- Fixed Gmail polling and Discord stats loops that still only handled `terror`, `historias`, and `dinero`.
- Fixed per-account quality thresholds so lower custom thresholds are honored after quality review.
- Removed duplicate DB backup scheduler registration in `main.py`.
- Replaced hardcoded Drive root folder (`TikTok Videos`) with `DRIVE_ROOT_FOLDER` and optional dedupe.
- Honored configured Whisper device/compute type, subtitle colors, music/narration volume, crossfade duration, Ken Burns zoom/pan/fps, TTS voices, and account image styles.
- Added SQLite auto-migration for v1.2 platform JSON columns.

### Compatibility

- Existing `tiktok_*` and `youtube_*` DB columns are preserved for old dashboards/scripts.
- Existing `config/platforms.json` is normalized to include new registered platforms with safe defaults.
- `publisher: "webhook"` platforms can be added without changing the scheduler or orchestrator.

## v1.1.0 â€” 2026-04-23

### ðŸŽ‰ New features

- **Multi-LLM script generation** (`core/llm_providers.py`): los guiones se pueden generar con **Gemini, OpenAI (GPT-4o, o1...), Anthropic Claude, OpenRouter, Groq, DeepSeek, Together AI, Mistral u Ollama local**, en una cadena de fallback configurable (`SCRIPT_PROVIDER_CHAIN`). Si Gemini falla por rate-limit, automÃ¡ticamente cae a OpenAI, luego a Claude, etc. Cada proveedor soporta mÃºltiples claves API y rotaciÃ³n.
- **Modelos Gemini por defecto actualizados** a `gemini-3-flash-preview, gemini-3.1-flash-lite-preview, gemini-2.5-flash, gemini-3.1-pro-preview, gemini-2.5-pro`.
- **Dashboard tabbed UI**: pestaÃ±as Overview / Videos / LLM Providers / API Keys / Emails / Analytics / Audit. Botones de retry/delete por video. Mini-chart de publicaciones por cuenta. Endpoint nuevo `GET /api/llm/providers` con health de cada proveedor.
- **Configurabilidad masiva**: ~60 nuevos ajustes vÃ­a `.env` (umbrales, volÃºmenes, ventanas de scheduler, colores de subtÃ­tulos, paginaciÃ³n, etc.). Todos los magic-numbers se han movido a `config/settings.py`.
- **Cuentas ilimitadas**: aÃ±ade niches custom soltando un fichero `config/accounts.json` (sin tocar cÃ³digo).
- **Dashboard v2**: 
  - AutenticaciÃ³n opcional vÃ­a `X-API-Key` (cabecera) â€” input persistente en localStorage.
  - CORS configurable + GZip.
  - Endpoints nuevos: `/health`, `/version`, `/api/audit`, `/api/calendar`, `/api/blackout`, `/api/prompts/{account}` (GET/PUT), `/api/backup`, `/api/analytics/timeseries`, `/api/accounts`, `/api/settings`, `/api/llm/providers`.
  - Acciones: `POST /api/videos/{id}/retry`, `DELETE /api/videos/{id}`, `POST /api/publish/{account}`, `POST /api/platforms/{account}/{platform}`.
  - `/api/videos` paginado (`?limit=&offset=&account=&status=`).
- **Bot Discord v2**: nuevos slash commands `/retry`, `/pause`, `/resume`, `/backup`, `/blackout`, `/health`, `/version`. ACCOUNT_CHOICES ahora se construye dinÃ¡micamente.
- **Notificaciones multi-canal**: ademÃ¡s de Discord, fan-out automÃ¡tico a Slack, Telegram y/o un webhook genÃ©rico.
- **Backups automÃ¡ticos** diarios de SQLite con retenciÃ³n configurable.
- **Audit log** + tabla `VideoMetrics`.
- **Blackout dates** + skip-weekends.
- **Per-account quality threshold**.
- **Health endpoint** `/health` con probes de DB/FFmpeg/secretos/disco.
- **GitHub-ready**: workflow CI (`.github/workflows/ci.yml`), bug-report + feature-request templates, PR template, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `.gitignore` reforzado.

### ðŸ› Bug fixes

- **`step_start` NameError**: en `pipeline/orchestrator.py`, si el primer paso fallaba, el `except` lanzaba `NameError`. Ahora se inicializa al inicio del retry-loop.
- **Hard-timeout de pipeline**: `asyncio.wait_for(...)` corta a `PIPELINE_TIMEOUT_SECONDS`.
- **Publish results indexing**: refactorizado a una lista `platform_order`.
- **Escrituras no-atÃ³micas**: `platforms.json`, `blackout.json` y `accounts.json` ahora se escriben con tmp+rename.
- **SQLite concurrencia**: WAL + `busy_timeout=30000` + `pool_pre_ping`.
- **Discord rate-limit / spam**: rate-limiter local (30/min) + enmascarado regex de tokens.
- **Tracebacks completos** se loguean siempre localmente; envÃ­o a Discord es opt-in.
- **Hardcoded account loops** eliminados â€” usan `list_account_ids()`.
- **Ãndices de DB**: aÃ±adidos Ã­ndices compuestos para acelerar dashboard.
- **Defensa anti-leak**: `.gitignore` ahora bloquea `*.pem`, `*.key`, `*.p12`, `secrets/`, `accounts.json`, `blackout_dates.json`, `platforms.json`, backups, WAL/SHM files.

### ðŸ”§ Internals / refactors

- Nuevos mÃ³dulos: `core/llm_providers.py`, `core/logging_config.py`, `core/notifications.py`, `core/security.py`, `core/backup.py`, `core/health.py`, `core/audit.py`.
- `_DEFAULT_PLATFORMS` estÃ¡tico eliminado â€” ahora se construye dinÃ¡micamente.

### ðŸ“¦ Compatibilidad

- Python 3.11 / 3.12 âœ“
- Sin nuevas dependencias obligatorias (todos los proveedores LLM nuevos usan `httpx`, ya presente).
- La DB existente se migra de forma transparente.

---

## v1.0.0 â€” Lanzamiento inicial

- Pipeline 8 pasos (script â†’ image â†’ TTS â†’ subs â†’ composite â†’ quality â†’ drive â†’ publish).
- 3 cuentas: terror, historias, dinero.
- Dashboard FastAPI + bot Discord bÃ¡sicos.
- Scheduler APScheduler con SQLAlchemy job store.
- Email agent con clasificaciÃ³n + auto-respuesta.
