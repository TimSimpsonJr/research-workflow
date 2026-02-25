"""Add project root to sys.path so tests can import scripts from parent directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
