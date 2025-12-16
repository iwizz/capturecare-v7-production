#!/usr/bin/env python3
"""
WSGI entry point for Gunicorn
"""
import sys
import os

# Add the current directory and parent directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)

# Import the app
from web_dashboard import app

if __name__ == "__main__":
    app.run()
