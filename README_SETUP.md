# CaptureCare Setup & Startup Guide

## Quick Start

### First Time Setup
```bash
# 1. Create and setup virtual environment
./setup_venv.sh

# 2. Start the server
./start_server.sh
```

### Daily Startup
```bash
./start_server.sh
```

The startup script will:
- ✅ Kill any existing server on port 5000
- ✅ Check/create virtual environment if needed
- ✅ Verify all dependencies are installed
- ✅ Start Flask server on http://127.0.0.1:5000

## Manual Setup (if scripts don't work)

```bash
# Navigate to project directory
cd "/Users/timhook/Library/Mobile Documents/com~apple~CloudDocs/GitCode/Capture Care Replit Version"

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Set Flask environment
export FLASK_APP=capturecare/web_dashboard.py
export FLASK_ENV=development

# Start server
flask run --host=0.0.0.0 --port=5000
```

## Troubleshooting

### Port 5000 Already in Use
```bash
# Kill process on port 5000
lsof -ti :5000 | xargs kill -9
```

### Dependencies Missing
```bash
# Activate venv and reinstall
source venv/bin/activate
pip install -r requirements.txt
```

### Virtual Environment Issues
```bash
# Remove and recreate venv
rm -rf venv
./setup_venv.sh
```

## Project Structure

```
Capture Care Replit Version/
├── capturecare/          # Main application code
│   ├── web_dashboard.py  # Flask app entry point
│   ├── models.py         # Database models
│   ├── templates/        # HTML templates
│   └── instance/         # Database files
├── scripts/              # Utility scripts
├── requirements.txt      # Python dependencies
├── setup_venv.sh         # Virtual environment setup
└── start_server.sh       # Server startup script
```

## Key Files

- **requirements.txt**: All Python dependencies (properly organized)
- **start_server.sh**: Automated server startup with dependency checking
- **setup_venv.sh**: Virtual environment setup script
- **capturecare/web_dashboard.py**: Main Flask application

## Notes

- Always use the virtual environment (`source venv/bin/activate`)
- Never install packages with `--target` flag (use venv's pip directly)
- Database is located at: `capturecare/instance/capturecare.db`
- Environment variables are in: `capturecare/capturecare.env`


