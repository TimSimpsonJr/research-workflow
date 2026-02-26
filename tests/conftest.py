"""Add scripts directory to sys.path so tests can import modules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
