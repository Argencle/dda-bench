import re
import h5py
import logging
import pandas as pd
from typing import Optional, Tuple


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


def compute_force_from_cpr(
    cpr: Tuple[float, float, float], norm: float
) -> float:
    """Compute force in Newtons from Cpr vector and norm."""
    epsilon_0 = 8.8541878176e-12
    fx, fy, fz = (c * norm**2 * epsilon_0 / 2 for c in cpr)
    return (fx**2 + fy**2 + fz**2) ** 0.5


def compute_internal_field_error(
    ifdda_h5_path: str, adda_csv_path: str, norm: float
) -> Optional[float]:
    """
    Compute the mean relative error between the squared magnitude of the
    internal electric field from IFDDA and ADDA.
    This is literally your function.
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
