#!/bin/bash
# ============================================================
# ViralStack — VPS Deploy Script
# Run: bash deploy.sh
# ============================================================
set -e

echo "=========================================="
echo "  ViralStack — VPS Setup"
echo "=========================================="

# --- 1. System dependencies ---
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv ffmpeg git curl

# --- 2. Python venv ---
echo "[2/6] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
# Install playwright browsers for tiktok-uploader
playwright install chromium --with-deps 2>/dev/null || true

echo "[3/6] Checking .env file..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "  !! IMPORTANT: Edit .env with your API keys !!"
    echo "  nano .env"
    echo ""
fi

# --- 4. Create directories ---
echo "[4/6] Creating directories..."
mkdir -p storage/cookies storage/output/{terror,historias,dinero}
mkdir -p music/royalty_free/{terror,historias,dinero}

# --- 5. Initialize database ---
echo "[5/6] Initializing database..."
python3 -c "
import sys; sys.path.insert(0, '.')
from core.db import init_db
from core.key_rotation import seed_keys_from_settings
init_db()
seed_keys_from_settings()
print('  Database initialized.')
"

# --- 6. Systemd service ---
echo "[6/6] Setting up systemd service..."
SERVICE_FILE="/etc/systemd/system/viralstack.service"
WORK_DIR="$(pwd)"
PYTHON_PATH="$WORK_DIR/.venv/bin/python3"

sudo tee $SERVICE_FILE > /dev/null << EOF
[Unit]
Description=ViralStack — TikTok + YouTube Shorts Automation
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$WORK_DIR
ExecStart=$PYTHON_PATH main.py
Restart=always
RestartSec=30
StandardOutput=append:$WORK_DIR/storage/viralstack.log
StandardError=append:$WORK_DIR/storage/viralstack.log
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable viralstack

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "  NEXT STEPS:"
echo ""
echo "  1. Edit your config:"
echo "     nano .env"
echo ""
echo "  2. Add your API keys to .env:"
echo "     - VERTEX_AI_API_KEY=your_key"
echo "     - DISCORD_BOT_TOKEN=your_token (optional)"
echo "     - GOOGLE_AI_API_KEY=your_key (optional, for quality check)"
echo ""
echo "  3. Set language (default=es):"
echo "     LANGUAGE=en   (English)"
echo "     LANGUAGE=es   (Spanish)"
echo ""
echo "  4. Setup YouTube OAuth (per account):"
echo "     python3 scripts/setup_youtube.py terror"
echo "     python3 scripts/setup_youtube.py historias"
echo "     python3 scripts/setup_youtube.py dinero"
echo ""
echo "  5. Export TikTok cookies:"
echo "     python3 scripts/export_cookies.py"
echo ""
echo "  6. Add music to music/royalty_free/{terror,historias,dinero}/"
echo ""
echo "  7. Setup Google Drive service account (optional):"
echo "     Place service_account.json in config/"
echo ""
echo "  8. Setup Gmail auto-replies (optional):"
echo "     python3 scripts/setup_gmail.py terror"
echo ""
echo "  9. Start the service:"
echo "     sudo systemctl start viralstack"
echo ""
echo "  10. Check status:"
echo "      sudo systemctl status viralstack"
echo "      journalctl -u viralstack -f"
echo ""
echo "  Dashboard: http://YOUR_VPS_IP:8000"
echo ""
