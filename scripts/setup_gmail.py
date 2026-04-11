#!/usr/bin/env python3
"""
Setup Gmail OAuth2 for a specific account's Email Agent.

Usage:
    python scripts/setup_gmail.py terror
    python scripts/setup_gmail.py historias
    python scripts/setup_gmail.py dinero

This will open a browser for Google OAuth consent flow.
Log in with the Google account for that specific channel.
The token will be saved to config/gmail_{account}_token.json.

Prerequisites:
1. Go to https://console.cloud.google.com/
2. Create a project (or use existing)
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop App type)
5. Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env
"""
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

VALID_ACCOUNTS = ["terror", "historias", "dinero"]


def setup(account: str):
    """Run Gmail OAuth flow for a specific account."""
    if account not in VALID_ACCOUNTS:
        print(f"Error: cuenta invalida '{account}'")
        print(f"Cuentas validas: {', '.join(VALID_ACCOUNTS)}")
        sys.exit(1)

    client_id = settings.gmail_client_id
    client_secret = settings.gmail_client_secret

    if not client_id or not client_secret:
        print("Error: GMAIL_CLIENT_ID y GMAIL_CLIENT_SECRET deben estar configurados en .env")
        print("\nPasos:")
        print("1. Ve a https://console.cloud.google.com/")
        print("2. Crea un proyecto (o selecciona uno existente)")
        print("3. Habilita 'Gmail API'")
        print("4. Ve a Credenciales > Crear credenciales > ID de cliente OAuth 2.0")
        print("5. Tipo de aplicacion: Aplicacion de escritorio")
        print("6. Copia el Client ID y Client Secret al .env")
        sys.exit(1)

    token_path = Path(settings.get_gmail_token_path(account))

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
    print(f"Configurando Gmail para cuenta: {account.upper()}")
    print(f"{'='*60}")
    print(f"\nSe abrira el navegador. Inicia sesion con la cuenta de Google")
    print(f"asociada al canal de '{account}'.")
    print(f"\nEl token se guardara en: {token_path}")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    print(f"\n{'='*60}")
    print(f"Gmail OAuth configurado para '{account}'")
    print(f"Token guardado en: {token_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python scripts/setup_gmail.py <cuenta>")
        print(f"Cuentas validas: {', '.join(VALID_ACCOUNTS)}")
        print("\nEjemplo:")
        print("  python scripts/setup_gmail.py terror")
        print("  python scripts/setup_gmail.py historias")
        print("  python scripts/setup_gmail.py dinero")
        sys.exit(1)

    setup(sys.argv[1])
