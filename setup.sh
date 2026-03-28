#!/usr/bin/env bash
set -euo pipefail

echo "=== Buddy AI Desk Pet - Pi Setup ==="

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install PortAudio for sounddevice (needed on Pi)
if command -v apt-get &> /dev/null; then
    echo "Installing system audio dependencies..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq portaudio19-dev libsndfile1
fi

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from .env.example - please fill in your API keys!"
fi

# Create data directory for persistent state
mkdir -p data assets/audio

echo ""
echo "=== Setup complete! ==="
echo "1. Edit .env with your API keys"
echo "2. Connect Arduino via USB"
echo "3. Run: source venv/bin/activate && python src/main.py"
