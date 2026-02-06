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


def clean_output_files(output_dir: str) -> None:
    """
    Clean only the files inside output_dir.
    """
    out = Path(output_dir)
    if not out.exists():
        return

    # Remove by exact name anywhere under outputs/
    remove_names = {
        "diel",
        "shape.dat",
        "shape_ifdda.dat",
        "ExpCount",
        "inputmatlab.mat",
        "filenameh5",
        "ifdda.h5",
        "mtable",
        "qtable",
        "qtable2",
        "target.out",
    }

    # Remove by glob patterns anywhere under outputs/
    remove_globs = [
        "run*",  # ADDA run directories
        "ddscat.par.bak*",
        "w*.avg",
    ]

    # 1) exact names
    for p in sorted(out.rglob("*"), reverse=True):
        if p.name not in remove_names:
            continue
        try:
            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
        except Exception:
            pass

    # 2) glob patterns
    for pattern in remove_globs:
        for p in sorted(out.rglob(pattern), reverse=True):
            try:
                if p.is_symlink() or p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p)
            except Exception:
                pass
