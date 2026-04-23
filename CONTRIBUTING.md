# Contribuir a ViralStack

¡Gracias por querer mejorar ViralStack! Aquí va una guía rápida.

## Setup

```bash
git clone https://github.com/<tu-usuario>/ViralStack.git
cd ViralStack
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                 # rellena al menos la sección "Núcleo"
pytest -q                            # debe pasar
python main.py                       # arranca todo
```

## Estructura

- `config/` — settings + prompts YAML por niche
- `core/` — DB, scheduler, alerts, key rotation, multi-LLM, backups, health, audit
- `pipeline/` — los 8 pasos del pipeline (script → image → tts → subs → composite → quality → drive → publish)
- `bot/` — Discord bot (slash commands)
- `dashboard/` — FastAPI + plantilla HTML
- `email_agent/` — clasificación + auto-respuesta de emails
- `tests/` — pytest

## Reglas

- **NUNCA** commitees `.env`, claves API, `service_account.json`, `*_token.json` ni cookies.
- Mantén la cobertura de `tests/` cuando añadas lógica no trivial.
- Sigue PEP-8 (ruff lo valida en CI).
- Cualquier setting nuevo se añade tanto a `config/settings.py` como a `.env.example`.
- Nuevas features → entrada en `CHANGELOG.md` (sección `Unreleased`).
- Bugs → issue + branch `fix/<descripcion-corta>` → PR con tests si es razonable.

## PR

1. Crea una branch desde `main`.
2. Asegúrate de que `pytest -q` pasa.
3. Abre el PR usando la plantilla.
4. Espera review y CI verde.

## Añadir un nuevo proveedor LLM

`core/llm_providers.py` está pensado para extenderse fácilmente:

1. Crea una clase nueva que herede de `BaseProvider` (o de `OpenAIProvider` si la API es compatible OpenAI).
2. Implementa `is_available()`, `models()`, `generate(...)`.
3. Regístrala en `_registry()`.
4. Añade los settings (`xxx_api_keys`, `xxx_models`, etc.) en `config/settings.py` y en `.env.example`.

## Añadir una cuenta nueva sin tocar código

Crea `config/accounts.json`:

```json
[
  {
    "id": "tech",
    "display_name": "Tech News",
    "voice": "kore",
    "videos_per_day": 2,
    "hashtags_tiktok": ["#tech", "#fyp"],
    "hashtags_youtube": ["#tech", "#shorts"]
  }
]
```

Reinicia y aparecerá en bot, dashboard y scheduler.
