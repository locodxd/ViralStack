#!/usr/bin/env python3
"""
Setup YouTube OAuth2 credentials for a specific account.

Usage:
    python scripts/setup_youtube.py terror
    python scripts/setup_youtube.py historias
    python scripts/setup_youtube.py dinero

This will open a browser for Google OAuth consent flow.
Log in with the Google account for that specific channel.
The token will be saved to config/youtube_{account}_token.json.

Prerequisites:
1. Create a project in Google Cloud Console
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop App type)
4. Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env
"""
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
VALID_ACCOUNTS = ["terror", "historias", "dinero"]


def setup_youtube(account: str):
    """Run the OAuth flow for a YouTube account."""
    if account not in VALID_ACCOUNTS:
        print(f"Error: cuenta invalida '{account}'")
        print(f"Cuentas validas: {', '.join(VALID_ACCOUNTS)}")
        sys.exit(1)

    client_id = settings.youtube_client_id
    client_secret = settings.youtube_client_secret

    if not client_id or not client_secret:
        print("Error: YOUTUBE_CLIENT_ID y YOUTUBE_CLIENT_SECRET deben estar configurados en .env")
        print("\nPasos:")
        print("1. Ve a https://console.cloud.google.com/")
        print("2. Crea un proyecto (o selecciona uno existente)")
        print("3. Habilita 'YouTube Data API v3'")
        print("4. Ve a Credenciales > Crear credenciales > ID de cliente OAuth 2.0")
        print("5. Tipo de aplicacion: Aplicacion de escritorio")
        print("6. Copia el Client ID y Client Secret al .env")
        sys.exit(1)

    token_path = Path(settings.get_youtube_token_path(account))

    # Build client config
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    from google_auth_oauthlib.flow import InstalledAppFlow

    print(f"\n{'='*60}")
    print(f"Configurando YouTube para cuenta: {account.upper()}")
    print(f"{'='*60}")
    print(f"\nSe abrira el navegador. Inicia sesion con la cuenta de Google")
    print(f"asociada al canal de YouTube para '{account}'.")
    print(f"\nEl token se guardara en: {token_path}")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save token
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    print(f"\n{'='*60}")
    print(f"YouTube OAuth configurado para '{account}'")
    print(f"Token guardado en: {token_path}")
    print(f"{'='*60}")

    # Verify by fetching channel info
    try:
        from googleapiclient.discovery import build
        service = build("youtube", "v3", credentials=creds)
        response = service.channels().list(part="snippet", mine=True).execute()
        items = response.get("items", [])
        if items:
            channel = items[0]["snippet"]
            print(f"\nCanal verificado: {channel['title']}")
            print(f"ID: {items[0]['id']}")
        else:
            print("\nAdvertencia: no se encontro canal asociado a esta cuenta.")
            print("Asegurate de que la cuenta tiene un canal de YouTube.")
    except Exception as e:
        print(f"\nAdvertencia al verificar canal: {e}")
        print("El token se guardo correctamente de todos modos.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python scripts/setup_youtube.py <cuenta>")
        print(f"Cuentas validas: {', '.join(VALID_ACCOUNTS)}")
        print("\nEjemplo:")
        print("  python scripts/setup_youtube.py terror")
        print("  python scripts/setup_youtube.py historias")
        print("  python scripts/setup_youtube.py dinero")
        sys.exit(1)

    setup_youtube(sys.argv[1])
