"""Main entry point for the Hedge Fund Platform"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api.server import socketio, app

# Export app for gunicorn
application = app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  Hedge Fund Risk & Trading Platform")
    print(f"  External/LAN API: http://0.0.0.0:{port}/api/")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
