import os
import subprocess
from typing import Optional, Tuple
from .config import OUTPUT_DIR
from .extractors import (
    extract_value_from_ifdda,
    extract_last_value_from_adda,
)
from .utils import (
    convert_to_SI_units,
    compute_rel_err,
    matching_digits_from_rel_err,
)


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
    output_dir: str = OUTPUT_DIR,
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

    # ADDA
    adda_cext = extract_last_value_from_adda(adda_out, "Cext")
    adda_cabs = extract_last_value_from_adda(adda_out, "Cabs")
    if adda_cext:
        adda_cext = convert_to_SI_units(adda_cext)
    if adda_cabs:
        adda_cabs = convert_to_SI_units(adda_cabs)

    # IFDDA
    ifdda_cext = extract_value_from_ifdda(ifdda_out, "Cext")
    ifdda_cabs = extract_value_from_ifdda(ifdda_out, "Cabs")

    # errors
    rel_err_cext = compute_rel_err(adda_cext, ifdda_cext)
    rel_err_cabs = compute_rel_err(adda_cabs, ifdda_cabs)

    digits_cext = matching_digits_from_rel_err(rel_err_cext)
    digits_cabs = matching_digits_from_rel_err(rel_err_cabs)

    return (
        digits_cext,
        digits_cabs,
        (adda_time, adda_mem),
        (ifdda_time, ifdda_mem),
    )
