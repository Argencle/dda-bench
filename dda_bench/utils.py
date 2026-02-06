import os
import math
import shutil
import re
from pathlib import Path
from typing import Optional


def compute_rel_err(
    val1: Optional[float], val2: Optional[float]
) -> Optional[float]:
    if val1 is None or val2 is None:
        return None
    if val2 == 0:
        return None
    return abs(val1 - val2) / abs(val2)


def matching_digits_from_rel_err(
    rel_err: Optional[float],
) -> Optional[int]:
    if rel_err is None or rel_err <= 0:
        return None
    return int(-math.log10(rel_err))  # int guarante at least this many digits


def extract_eps_from_adda(cmd: str) -> Optional[int]:
    """
    Extract -eps N from an ADDA command line string.
    Returns None if not found.
    """
    m = re.search(r"-eps\s+(\d+)", cmd)
    if not m:
        return None
    return int(m.group(1))


def clean_output_files() -> None:
    """Remove ADDA and IFDDA output files and folders."""
    for path in Path(".").glob("run*"):
        if path.is_dir():
            shutil.rmtree(path)
    for fname in [
        "ExpCount",
        "inputmatlab.mat",
        "filenameh5",
        "ifdda.h5",
    ]:
        if os.path.exists(fname):
            os.remove(fname)

    for pattern in ["ddscat.par.bak*"]:
        for path in Path(".").glob(pattern):
            if path.is_file():
                path.unlink()

    bin_patterns = [
        "ddscat.log_*",
        "mtable",
        "qtable",
        "qtable2",
        "w*.avg",
        "target.out",
        "ExpCount",
        "ddscat.par.bak*",
    ]
    for pattern in bin_patterns:
        for path in Path("bin").glob(pattern):
            if path.is_file():
                path.unlink()
