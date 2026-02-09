import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# === Output configuration ===
OUTPUT_DIR = "outputs"
CLEAN_OUTPUT = True  # remove temp stuff at the end

# === Command files ===
DEFAULT_COMMAND_FILE_SOLVER = "tests/DDA_commands_solverprecision"
DEFAULT_COMMAND_FILE_FULL = "tests/DDA_commands_fullprecision"
DEFAULT_COMMAND_FILE_INTERNALFIELD = "tests/DDA_commands_internalfield"

# === Path ===
REPO_ROOT = Path(__file__).resolve().parent.parent
DDA_CODES_JSON = REPO_ROOT / "dda_codes.json"

# === Environment ===
# Set the number of OpenMP threads (default: 1)
os.environ["OMP_NUM_THREADS"] = "1"
