import os
import subprocess
import re
import shutil
import h5py
import argparse
import math
import logging
import sys
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple, List


# === USER CONFIGURATION ===
# Set the paths to the ADDA and IFDDA executables:
ADDA_PATH = "./adda/src/seq/adda"
IFDDA_PATH = "./if-dda/tests/test_command/ifdda"
# To enable MPI parallel execution with ADDA, replace the ADDA_PATH as follows:
# ADDA_PATH = "mpirun -np <number_of_processes> ./../adda/src/mpi/adda_mpi"
# Set the number of OpenMP threads for IFDDA (default: 1)
os.environ["OMP_NUM_THREADS"] = "1"

# === Output configurations ===
OUTPUT_DIR = "output"
CLEAN_OUTPUT = True  # Remove ADDA output folders

# === Table Column Widths ===
COL_WIDTH_LINE = 4
COL_WIDTH_MATCH = 10
COL_WIDTH_FORCE = 11
COL_WIDTH_INT = 14
COL_WIDTH_TIME = 7
COL_WIDTH_MEM = 7


def extract_value_from_ifdda(file_path: str, key: str) -> Optional[float]:
    """Extract the Cext value from IFDDA output."""
    with open(file_path, "r") as f:
        for line in f:
            match = re.search(rf"{key}\s*=\s*([0-9.eE+-]+)\s*m2", line)
            if match:
                return float(match.group(1))
    return None


def extract_last_value_from_adda(file_path: str, key: str) -> Optional[float]:
    """
    Extract the last Cext value from ADDA output as both polarisations can be
    computed.
    """
    matches = []
    with open(file_path, "r") as f:
        for line in f:
            match = re.search(rf"{key}\s*=\s*([0-9.eE+-]+)", line)
            if match:
                matches.append(float(match.group(1)))
    return matches[-1] if matches else None


def extract_cpr_from_adda(
    file_path: str,
) -> Optional[Tuple[float, float, float]]:
    """Extract the Cpr vector (x, y, z) from ADDA output."""
    with open(file_path, "r") as f:
        for line in f:
            match = re.search(
                r"Cpr\s*=\s*\(\s*([0-9eE+.\-]+),\s*([0-9eE+.\-]+),"
                r"\s*([0-9eE+.\-]+)\s*\)",
                line,
            )
            if match:
                x = float(match.group(1))
                y = float(match.group(2))
                z = float(match.group(3))
                return (x, y, z)
    return None


def extract_force_from_ifdda(file_path: str) -> Optional[float]:
    """Extract modulus of the optical force in Newtons from IFDDA output."""
    with open(file_path, "r") as f:
        for line in f:
            match = re.search(
                r"Modulus of the force\s*:\s*([0-9eE+.\-]+)", line
            )
            if match:
                return float(match.group(1))
    return None


def compute_force_from_cpr(
    cpr: Tuple[float, float, float], norm: float
) -> float:
    """Compute force in Newtons from Cpr vector and norm."""
    epsilon_0 = 8.8541878176e-12
    fx, fy, fz = (c * norm**2 * epsilon_0 / 2 for c in cpr)
    return (fx**2 + fy**2 + fz**2) ** 0.5


def clean_output_files():
    """Remove ADDA and IFDDA output files and folders."""
    for path in Path(".").glob("run*"):
        if path.is_dir():
            shutil.rmtree(path)
    for fname in ["ExpCount", "inputmatlab.mat", "filenameh5", "ifdda.h5"]:
        if os.path.exists(fname):
            os.remove(fname)


def run_command_with_stats(
    command: str, output_file: str, with_stats: bool
) -> Tuple[Optional[float], Optional[int]]:
    """
    Run a command with optional /usr/bin/time -v and extract CPU time
    and memory usage.
    """
    if with_stats:
        time_log = output_file + ".time"
        full_cmd = f"/usr/bin/time -v {command}"
        with open(output_file, "w") as out, open(time_log, "w") as err:
            subprocess.run(full_cmd, shell=True, stdout=out, stderr=err)

        cpu_time = None
        max_mem_kb = None
        with open(time_log, "r") as f:
            for line in f:
                if "User time (seconds):" in line:
                    cpu_time = float(line.split(":")[1].strip())
                elif "Maximum resident set size" in line:
                    max_mem_kb = int(line.split(":")[1].strip())
        return cpu_time, max_mem_kb
    else:
        with open(output_file, "w") as out:
            subprocess.run(
                command, shell=True, stdout=out, stderr=subprocess.DEVNULL
            )
        return None, None


def process_pair(
    adda_cmd: str,
    ifdda_cmd: str,
    pair_index: int,
    output_dir: str = "output",
    with_stats: bool = True,
) -> Tuple[
    Optional[int],
    Optional[int],
    Tuple,
    Tuple,
]:
    """
    Execute a pair of command-lines from the input file and extract results
    and resource usage.
    """
    line_number = 12 + 3 * pair_index
    adda_out = os.path.join(output_dir, f"line_{line_number}_adda.txt")
    ifdda_out = os.path.join(output_dir, f"line_{line_number}_ifdda.txt")

    adda_time, adda_mem = run_command_with_stats(
        adda_cmd, adda_out, with_stats
    )
    ifdda_time, ifdda_mem = run_command_with_stats(
        ifdda_cmd, ifdda_out, with_stats
    )

    adda_cext = extract_last_value_from_adda(adda_out, "Cext")
    adda_cabs = extract_last_value_from_adda(adda_out, "Cabs")

    if adda_cext:
        adda_cext = convert_to_SI_units(adda_cext)
    if adda_cabs:
        adda_cabs = convert_to_SI_units(adda_cabs)

    ifdda_cext = extract_value_from_ifdda(ifdda_out, "Cext")
    ifdda_cabs = extract_value_from_ifdda(ifdda_out, "Cabs")

    rel_err_cext = compute_rel_err(adda_cext, ifdda_cext)
    rel_err_cabs = compute_rel_err(adda_cabs, ifdda_cabs)

    digits_cext = matching_digits_from_rel_err(rel_err_cext)
    digits_abs = matching_digits_from_rel_err(rel_err_cabs)

    return (
        digits_cext,
        digits_abs,
        (adda_time, adda_mem),
        (ifdda_time, ifdda_mem),
    )


def convert_to_SI_units(value: float) -> float:
    """Convert ADDA's output to SI units (m²)"""
    return value * 1e-12


def compute_rel_err(
    val1: Optional[float], val2: Optional[float]
) -> Optional[float]:
    if val1 and val2:
        return abs(val1 - val2) / abs(val2)
    else:
        return None


def matching_digits_from_rel_err(rel_err: Optional[float]) -> Optional[int]:
    if rel_err:
        return int(-math.log10(rel_err))
    else:
        return None


def read_command_pairs(command_file: str) -> List[Tuple[Tuple[str, str], int]]:
    """
    Read command-lines from an input file and return them with line number of
    the first command in each pair.
    """
    lines = []
    line_indices = []
    with open(command_file, "r") as f:
        for idx, line in enumerate(f, start=1):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
                line_indices.append(idx)

    if len(lines) % 2 != 0:
        raise ValueError("Command file must have an even number of lines.")
    return [
        ((lines[i], lines[i + 1]), line_indices[i])
        for i in range(0, len(lines), 2)
    ]


def parse_command_lines(line: str, prefixe: str) -> str:
    return line.split(maxsplit=1)[1] if line.startswith(f"{prefixe}") else line


def update_minimum_matching(
    match: Optional[int],
    line_number: int,
    current_min: int,
    lines: List[int],
    errors: List[int],
) -> Tuple[int, List[int], List[int]]:
    if match is not None:
        if match < current_min:
            return match, [line_number], [match]
        elif match == current_min:
            lines.append(line_number)
            errors.append(match)
    return current_min, lines, errors


def find_adda_internal_field(pair_index: int) -> Optional[str]:
    """
    Find the internal field file generated by ADDA (run* folders)
    for a given index.
    """
    pattern = f"run{pair_index:03d}_*/IntField-Y"
    for path in Path(".").glob(pattern):
        if path.exists():
            return str(path)
    return None


def extract_field_norm_from_ifdda(file_path: str) -> Optional[float]:
    """
    Extract the normalization constant from the IFDDA output file.
    Looks for a line like: "Field : (2447309.3783680922,0.0) V/m"
    """
    with open(file_path, "r") as f:
        for line in f:
            match = re.search(r"Field\s*:\s*\(\s*([0-9.eE+-]+)", line)
            if match:
                return float(match.group(1))
    return None


def compute_internal_field_error(
    ifdda_h5_path: str, adda_csv_path: str, norm: float
) -> Optional[float]:
    """
    Compute the mean relative error between the squared magnitude of the
    internal electric field from IFDDA and ADDA.

    The IFDDA internal field is normalized using a reference field
    value (norm) extracted from the IFDDA output. The ADDA field is read from
    a CSV file containing the squared electric field magnitude (|E|^2).
    """
    try:
        with h5py.File(ifdda_h5_path, "r") as f:
            macro_modulus = f["Near Field/Macroscopic field modulus"][:]
        adda_data = pd.read_csv(adda_csv_path, sep=" ")
        valid_ifdda = macro_modulus[macro_modulus != 0] / norm
        relative_error = (
            abs((valid_ifdda**2 - adda_data["|E|^2"]) / adda_data["|E|^2"])
        ).mean()
        return relative_error
    except Exception as e:
        logging.error(f"Internal field comparison failed: {e}")
        return None


def build_header(
    logger: logging.Logger, with_stats: bool, force: bool, int_field: bool
) -> None:
    columns = [
        ("Line", COL_WIDTH_LINE),
        ("Cext Match", COL_WIDTH_MATCH),
        ("Cabs Match", COL_WIDTH_MATCH),
    ]
    if force:
        columns.append(("Force Match", COL_WIDTH_FORCE))
    if int_field:
        columns.append(("IntField Match", COL_WIDTH_INT))
    if with_stats:
        columns.extend(
            [
                ("A_CPU", COL_WIDTH_TIME),
                ("A_MEM", COL_WIDTH_MEM),
                ("I_CPU", COL_WIDTH_TIME),
                ("I_MEM", COL_WIDTH_MEM),
            ]
        )

    header = " | ".join([f"{name:>{width}}" for name, width in columns])
    separator = "-" * len(header)
    logger.info(header)
    logger.info(separator)


def compute_force_digits(
    adda_out_path: str, ifdda_out_path: str, line_parts: List[str]
) -> Optional[int]:
    force_match_str = "N/A"
    digits_force = None
    adda_cpr = extract_cpr_from_adda(adda_out_path)
    if adda_cpr:
        ifdda_force = extract_force_from_ifdda(ifdda_out_path)
        norm = extract_field_norm_from_ifdda(ifdda_out_path)
        if norm and ifdda_force:
            adda_force = compute_force_from_cpr(adda_cpr, norm)
            adda_force = convert_to_SI_units(adda_force)
            force_rel_err = compute_rel_err(ifdda_force, adda_force)
            digits_force = matching_digits_from_rel_err(force_rel_err)
            force_match_str = f"{digits_force}"
    line_parts.append(f"{force_match_str:>{COL_WIDTH_FORCE}}")
    return digits_force


def compute_internal_field_digits(
    index: int, ifdda_out_path: str, ifdda_h5_path: str, line_parts: List[str]
) -> Optional[int]:
    int_field_err_str = "N/A"
    digits_int = None
    adda_field_path = find_adda_internal_field(index)
    if adda_field_path:
        norm = extract_field_norm_from_ifdda(ifdda_out_path)
        if norm:
            int_field_error = compute_internal_field_error(
                ifdda_h5_path, adda_field_path, norm
            )
            digits_int = matching_digits_from_rel_err(int_field_error)
            int_field_err_str = f"{digits_int}"
    line_parts.append(f"{int_field_err_str:>{COL_WIDTH_INT}}")
    return digits_int


def extract_eps_from_adda(
    line: str, line_id: int, logger: logging.Logger
) -> int:
    """Extract the -eps value from an ADDA command line. Exit if not found."""
    match = re.search(r"-eps\s+(\d+)", line)
    if not match:
        logger.error(f"Missing -eps argument in ADDA command line: {line_id}")
        sys.exit(1)
    return int(match.group(1))


def process_all_pairs(
    command_pairs: List[Tuple[Tuple[str, str], int]],
    output_dir: str,
    logger: logging.Logger,
    with_stats: bool = True,
    force: bool = True,
    int_field: bool = True,
    full_precision: bool = False,
    check: bool = True,
) -> None:
    """
    Run all command pairs and print a formatted summary of Cext and Cabs values
    and performance metrics. And also the minimum number of matching digits
    and the list of line numbers where this minimum occurs.
    """
    min_match_cext = 999
    min_lines: List[int] = []
    min_rel_errors: List[int] = []

    failed_lines: List[int] = []

    for i, ((adda_line, ifdda_line), line_number) in enumerate(command_pairs):
        adda_args = parse_command_lines(adda_line, "adda")
        ifdda_args = parse_command_lines(ifdda_line, "ifdda")

        adda_cmd = f"{ADDA_PATH} {adda_args}"
        ifdda_cmd = f"{IFDDA_PATH} {ifdda_args}"

        (
            match_cext,
            match_cabs,
            (adda_time, adda_mem),
            (ifdda_time, ifdda_mem),
        ) = process_pair(adda_cmd, ifdda_cmd, i, output_dir, with_stats)

        min_match_cext, min_lines, min_rel_errors = update_minimum_matching(
            match_cext, line_number, min_match_cext, min_lines, min_rel_errors
        )

        match_cext_str = (
            f"{match_cext}" if match_cext is not None else f"{'N/A':>11}"
        )
        match_cabs_str = (
            f"{match_cabs}" if match_cabs is not None else f"{'N/A':>11}"
        )

        # Build the line in parts
        line_parts = [
            f"{line_number:>{COL_WIDTH_LINE}}",
            f"{match_cext_str:>{COL_WIDTH_MATCH}}",
            f"{match_cabs_str:>{COL_WIDTH_MATCH}}",
        ]

        line_id = 12 + 3 * i
        adda_out_path = os.path.join(output_dir, f"line_{line_id}_adda.txt")
        ifdda_out_path = os.path.join(output_dir, f"line_{line_id}_ifdda.txt")
        ifdda_h5_path = "ifdda.h5"

        if force:
            match_force = compute_force_digits(
                adda_out_path, ifdda_out_path, line_parts
            )

        if int_field:
            match_int_field = compute_internal_field_digits(
                i, ifdda_out_path, ifdda_h5_path, line_parts
            )

        if with_stats:
            line_parts.extend(
                [
                    f"{(adda_time or 0):>{COL_WIDTH_TIME}.2f}",
                    f"{(adda_mem or 0) / 1024:>{COL_WIDTH_MEM}.2f}",
                    f"{(ifdda_time or 0):>{COL_WIDTH_TIME}.2f}",
                    f"{(ifdda_mem or 0) / 1024:>{COL_WIDTH_MEM}.2f}",
                ]
            )

        # Join line
        line_str = " | ".join(line_parts)

        if full_precision:
            min_digits = 11
            max_digits = 16
        else:
            eps = extract_eps_from_adda(adda_args, line_id, logger)
            min_digits = eps - 1
            max_digits = eps + 2

        # Decide if this line fails
        should_highlight = (
            (
                match_cext is not None
                and not (min_digits <= match_cext <= max_digits)
            )
            or (
                force
                and match_force
                and not (min_digits <= match_force <= max_digits)
            )
            or (
                int_field
                and match_int_field
                and not (min_digits <= match_int_field <= max_digits)
            )
        )

        if should_highlight:
            if check:
                failed_lines.append(line_number)
            logger.error(line_str)
        else:
            logger.info(line_str)

    if check:
        if failed_lines:
            logger.error(
                f"{len(failed_lines)} test(s) failed at lines: "
                f"{', '.join(map(str, failed_lines))}"
            )
            clean_output_files()
            sys.exit(1)
        else:
            logger.info("All tests passed.")
    else:
        logger.info(
            f"Minimum number of matching digits for Cext: {min_match_cext}"
        )
        logger.info(f"Occurred at line(s): {', '.join(map(str, min_lines))}")


def build_logger(check: bool) -> logging.Logger:
    logger = logging.getLogger("compare_digits")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(levelname)s | %(message)s")

    logfile_handler = logging.FileHandler("compare_digits.log")
    logfile_handler.setLevel(logging.INFO)
    logfile_handler.setFormatter(formatter)
    logger.addHandler(logfile_handler)

    errorfile_handler = logging.FileHandler("compare_digits.errors.log")
    errorfile_handler.setLevel(logging.ERROR)
    errorfile_handler.setFormatter(formatter)
    logger.addHandler(errorfile_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR if check else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def main():
    parser = argparse.ArgumentParser(
        description="Compare ADDA and IFDDA Cext and Cabs results."
    )
    parser.add_argument(
        "--with-stats",
        action="store_true",
        help="Enable /usr/bin/time measurements",
    )
    parser.add_argument(
        "-fp",
        "--full",
        action="store_true",
        help="Use the full-precision command file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Compute the Force.",
    )
    parser.add_argument(
        "--int",
        dest="int_field",
        action="store_true",
        help="Compute the Internal Field.",
    )
    parser.add_argument(
        "-ci",
        "--check",
        action="store_true",
        help="CI/CD mode: minimal output, fails on mismatch",
    )

    args = parser.parse_args()

    COMMAND_FILE = (
        "tests/DDA_commands_fullprecision"
        if args.full
        else "tests/DDA_commands_solverprecision"
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    command_pairs = read_command_pairs(COMMAND_FILE)

    logger = build_logger(args.check)
    build_header(logger, args.with_stats, args.force, args.int_field)

    process_all_pairs(
        command_pairs,
        OUTPUT_DIR,
        logger=logger,
        with_stats=args.with_stats,
        force=args.force,
        int_field=args.int_field,
        full_precision=args.full,
        check=args.check,
    )

    if CLEAN_OUTPUT:
        clean_output_files()


if __name__ == "__main__":
    main()
