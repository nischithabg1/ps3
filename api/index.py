import sys
import os

# Add the root directory to path so it can find 'backend'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api.server import app

# Vercel needs the Flask 'app' instance
handler = app
