import os

# === Executable paths ===
ADDA_PATH = "./adda/src/seq/adda"
IFDDA_PATH = "./if-dda/tests/test_command/ifdda"
# To enable MPI parallel execution with ADDA, replace the ADDA_PATH as follows:
# ADDA_PATH = "mpirun -np <number_of_processes> ./adda/src/mpi/adda_mpi"

# === Output configuration ===
OUTPUT_DIR = "output"
CLEAN_OUTPUT = True  # remove ADDA/IFDDA temp stuff at the end

# === Command files ===
DEFAULT_COMMAND_FILE_SOLVER = "tests/DDA_commands_solverprecision"
DEFAULT_COMMAND_FILE_FULL = "tests/DDA_commands_fullprecision"

# === Table column widths ===
COL_WIDTH_LINE = 4
COL_WIDTH_MATCH = 10
COL_WIDTH_FORCE = 11
COL_WIDTH_INT = 14
COL_WIDTH_TIME = 7
COL_WIDTH_MEM = 7

# === Environment ===
# Set the number of OpenMP threads for IFDDA (default: 1)
os.environ["OMP_NUM_THREADS"] = "1"
