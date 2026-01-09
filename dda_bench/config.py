import os
from pathlib import Path

# === Executable paths ===
ADDA_PATH = "/home/argentic@coria.fr/Bureau/Work/Data_DDA_benchmark_paper/adda/src/seq/adda"
IFDDA_PATH = "/home/argentic@coria.fr/Bureau/Work/Data_DDA_benchmark_paper/if-dda/tests/test_command/ifdda"
os.environ["DDSCAT_PAR"] = (
    "/home/argentic@coria.fr/Bureau/Work/Data_DDA_benchmark_paper/ddscat7.3.4_250505/ddscat.par"
)
os.environ["DDSCAT_EXE"] = (
    "/home/argentic@coria.fr/Bureau/Work/Data_DDA_benchmark_paper/ddscat7.3.4_250505/src/ddscat"
)

# To enable MPI parallel execution with ADDA, replace the ADDA_PATH as follows:
# ADDA_PATH = "mpirun -np <number_of_processes> ./adda/src/mpi/adda_mpi"

# === Output configuration ===
OUTPUT_DIR = "output"
CLEAN_OUTPUT = True  # remove ADDA/IFDDA temp stuff at the end

# === Command files ===
DEFAULT_COMMAND_FILE_SOLVER = "tests/DDA_commands_solverprecision"
DEFAULT_COMMAND_FILE_FULL = "tests/DDA_commands_fullprecision"
DEFAULT_COMMAND_FILE_INTERNALFIELD = "tests/DDA_commands_internalfield"

# === Path ===
REPO_ROOT = Path(__file__).resolve().parent.parent
DDA_CODES_JSON = REPO_ROOT / "dda_codes.json"

# === Environment ===
# Set the number of OpenMP threads for IFDDA and DDSCAT (default: 1)
os.environ["OMP_NUM_THREADS"] = "1"
