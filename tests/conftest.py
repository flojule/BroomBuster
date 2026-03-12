import os
import sys

# Make src/ importable without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
