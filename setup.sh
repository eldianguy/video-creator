#!/bin/bash
# Video Copy Tool - Setup Script

set -e

echo "====================================="
echo "  Video Copy Tool - Setup"
echo "====================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    exit 1
fi

echo "[1/4] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "[2/4] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/4] Checking FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "WARNING: FFmpeg is not installed!"
    echo "Install it with:"
    echo "  Ubuntu/Debian: sudo apt install ffmpeg"
    echo "  macOS:         brew install ffmpeg"
    echo "  Windows:       https://ffmpeg.org/download.html"
    echo ""
else
    echo "FFmpeg found: $(ffmpeg -version | head -1)"
fi

echo "[4/4] Creating workspace directory..."
mkdir -p workspace

echo ""
echo "====================================="
echo "  Setup complete!"
echo "====================================="
echo ""
echo "Start the app with:"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "Then open http://localhost:5000 in your browser."
echo ""
