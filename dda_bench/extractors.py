import json
import re
import logging
import h5py
import pandas as pd
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List


def load_engine_config(path: Path) -> Dict[str, Any]:
    """
    Load dda_codes.json.
    """
    with path.open("r") as f:
        return json.load(f)


def detect_engine_from_cmd(cmd: str, engines_cfg: Dict[str, Any]) -> str:
    """
    Look for any of the 'detect_substrings' of each engine.
    """
    for name, cfg in engines_cfg.items():
        for sub in cfg.get("detect_substrings", []):
            if sub in cmd:
                return name
    raise ValueError(f"Cannot detect engine for command: {cmd}")


def read_quantity_from_text_file(
    output_path: Path,
    pattern: str,
    unit_factor: float = 1.0,
    take_last: bool = False,
) -> Optional[float]:
    if not output_path.exists():
        return None

    text = output_path.read_text()

    match: Optional[re.Match[str]]

    if take_last:
        matches = list(re.finditer(pattern, text))
        if not matches:
            return None
        match = matches[-1]
    else:
        match = re.search(pattern, text)

    if match is None:
        return None

    value = float(match.group("value"))
    return value * unit_factor


def read_quantity_from_hdf5(
    output_path: Path, dataset: str, index: Optional[int] = None
) -> Optional[float]:
    if not output_path.exists():
        return None
    with h5py.File(output_path, "r") as f:
        data = f[dataset][()]
    if index is not None:
        return float(data[index])
    return float(data)


def extract_quantity_for_engine(
    engine: str,
    engine_cfg: Dict[str, Any],
    quantity: str,
    main_output: Path,
) -> Optional[float]:
    """
    Try to read a quantity for this engine.
    1) from the main output file
    2) if not found, from any extra file patterns in JSON
       (e.g. ddscat_*.log)
    """
    outputs = engine_cfg.get("outputs", {})
    spec = outputs.get(quantity)
    if not spec:
        return None

    pattern = spec["pattern"]
    unit_factor = spec.get("unit_factor", 1.0)
    take_last = spec.get("take_last", False)

    # 1) try main file
    val = read_quantity_from_text_file(
        main_output,
        pattern,
        unit_factor=unit_factor,
        take_last=take_last,
    )
    if val is not None:
        return val

    # 2) try extra files
    extra_patterns: List[str] = engine_cfg.get("extra_files", [])
    for extra_pat in extra_patterns:
        for extra_path in Path(".").glob(extra_pat):
            val = read_quantity_from_text_file(
                extra_path,
                pattern,
                unit_factor=unit_factor,
                take_last=take_last,
            )
            if val is not None:
                return val

    return None


def extract_cpr_from_adda(
    file_path: Path,
) -> Optional[Tuple[float, float, float]]:
    text = file_path.read_text()
    pattern = (
        r"Cpr\s*=\s*\("
        r"\s*([0-9eE+.\-]+),"
        r"\s*([0-9eE+.\-]+),"
        r"\s*([0-9eE+.\-]+)\s*\)"
    )
    match = re.search(pattern, text)
    if not match:
        return None
    return (
        float(match.group(1)),
        float(match.group(2)),
        float(match.group(3)),
    )


def extract_force_from_ifdda(file_path: Path) -> Optional[float]:
    """
    Read 'Modulus of the force : <val>' from IFDDA.
    """
    text = file_path.read_text()
    m = re.search(r"Modulus of the force\s*:\s*([0-9eE+.\-]+)", text)
    if not m:
        return None
    return float(m.group(1))


def extract_field_norm_from_ifdda(file_path: Path) -> Optional[float]:
    """
    Read the normalizing field from IFDDA text:
    'Field : (2447309.3783,0.0) V/m'
    """
    text = file_path.read_text()
    m = re.search(r"Field\s*:\s*\(\s*([0-9.eE+-]+)", text)
    if not m:
        return None
    return float(m.group(1))


def find_adda_internal_field(group_idx: int) -> Optional[Path]:
    """
    ADDA writes internal field in runXXX_.../IntField-Y
    We look for run{group_idx:03d}_*/IntField-Y
    """
    pat = f"run{group_idx:03d}_*/IntField-Y"
    for p in Path(".").glob(pat):
        return p
    return None


def compute_internal_field_error(
    ifdda_h5_path: Path, adda_csv_path: Path, norm: float
) -> Optional[float]:
    """
    Compare IFDDA HDF5 near field with ADDA CSV internal field, like before.
    """
    try:
        with h5py.File(ifdda_h5_path, "r") as f:
            macro_modulus = f["Near Field/Macroscopic field modulus"][:]
        adda_df = pd.read_csv(adda_csv_path, sep=" ")
        valid_ifdda = macro_modulus[macro_modulus != 0] / norm
        rel = (
            abs((valid_ifdda**2 - adda_df["|E|^2"]) / adda_df["|E|^2"])
        ).mean()
        return rel
    except Exception as e:
        logging.error(f"Internal field comparison failed: {e}")
        return None
