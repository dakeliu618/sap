"""Tests-level conftest — ensures app/ is on sys.path for all tests in this folder."""
import sys
from pathlib import Path

# Add app/ to sys.path so tools, agent, etc. can be imported directly
_app_dir = str(Path(__file__).parent.parent / "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
