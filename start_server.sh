#!/bin/bash

# CaptureCare Flask Server Startup Script
# This script ensures dependencies are installed and starts the server properly

set -e  # Exit on any error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🛑 Stopping any existing server on port 5000..."
# Kill any process using port 5000
lsof -ti :5000 | xargs kill -9 2>/dev/null || echo "   No existing server found"

# Wait a moment for the port to be released
sleep 2

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "📦 Running setup script to create virtual environment..."
    bash setup_venv.sh
fi

echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Verify critical dependencies are installed
echo "🔍 Verifying critical dependencies..."
python3 -c "
import sys
missing = []
try:
    import flask
    import flask_sqlalchemy
    import flask_cors
    import sqlalchemy
    import requests
    import stripe
    import openai
    print('✅ All critical dependencies found')
except ImportError as e:
    print(f'❌ Missing dependency: {e.name}')
    print('📦 Installing missing dependencies...')
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
" || {
    echo "📦 Installing/updating dependencies..."
    pip install -r requirements.txt --quiet
}

echo "📦 Setting Flask environment variables..."
export FLASK_APP=capturecare/web_dashboard.py
export FLASK_ENV=development

echo ""
echo "🚀 Starting Flask server on http://0.0.0.0:5000..."
echo "📱 Open http://127.0.0.1:5000 in your browser"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the Flask server
flask run --host=0.0.0.0 --port=5000
