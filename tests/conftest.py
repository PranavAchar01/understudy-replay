import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# addopts sets --basetemp=data/work/pytest, and pytest does not create the parent of a basetemp (a fresh clone has no data/work)
(Path(__file__).resolve().parents[1] / "data" / "work").mkdir(parents=True, exist_ok=True)
