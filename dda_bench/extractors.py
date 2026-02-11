import json
import re
import logging
import math
import h5py
import pandas as pd
from pathlib import Path
from typing import Optional, Any


def load_engine_config(path: Path) -> dict[str, Any]:
    """
    Load dda_codes.json.
    """
    with path.open("r") as f:
        return json.load(f)


def detect_engine_from_cmd(cmd: str, engines_cfg: dict[str, Any]) -> str:
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
    type: str = "text",
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

    if type == "text_vec3_norm":
        x = float(match.group("x"))
        y = float(match.group("y"))
        z = float(match.group("z"))
        return math.sqrt(x**2 + y**2 + z**2) * unit_factor

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
    engine_cfg: dict[str, Any],
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
    type = spec["type"]

    # 1) try main file
    val = read_quantity_from_text_file(
        main_output,
        pattern,
        unit_factor=unit_factor,
        take_last=take_last,
        type=type,
    )
    if val is not None:
        return val

    # 2) try extra files
    extra_patterns: list[str] = engine_cfg.get("extra_files", [])
    base_dir = main_output.parent
    for extra_pat in extra_patterns:
        pat_path = Path(extra_pat)

        if pat_path.is_absolute():
            # absolute path: treat as a single file
            candidate_paths = [pat_path]
        else:
            # relative / glob pattern: keep existing behaviour
            candidate_paths = base_dir.glob(extra_pat)
        for extra_path in candidate_paths:
            val = read_quantity_from_text_file(
                extra_path,
                pattern,
                unit_factor=unit_factor,
                take_last=take_last,
                type=type,
            )
            if val is not None:
                return val

    return None


def find_adda_internal_field_in_dir(adda_run_dir: Path) -> Optional[Path]:
    """
    In a per-run working directory, ADDA writes something like:
      <run_dir>/runXXX_.../IntField-Y
    We search locally inside adda_run_dir.
    """
    for p in adda_run_dir.glob("run*/*IntField-Y"):
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
            # print(list(f["Near Field"].keys()))
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


def _to_meters(val: float, unit: str) -> float:
    u = (unit or "").lower()
    if u in ("m", "meter", "meters"):
        return val
    if u in ("um", "micron", "microns", "µm"):
        return val * 1e-6
    if u in ("nm", "nanometer", "nanometers"):
        return val * 1e-9
    # fallback: assume already meters
    return val


def _read_first_match(paths: list[Path], pattern: str) -> Optional[float]:
    rgx = re.compile(pattern)
    for p in paths:
        if not p.exists():
            continue
        txt = p.read_text(errors="ignore")
        m = rgx.search(txt)
        if m:
            return float(m.group("value"))
    return None


def extract_aeff_meters_for_engine(
    engine_cfg: dict[str, Any],
    stdout_path: Path,
    extra_paths: list[Path],
) -> Optional[float]:
    """
    Returns aeff in meters if it can be obtained from outputs.
    Supports:
      - direct aeff in text (ddsCAT logs, etc.)
      - aeff from N_dipoles + mesh_size (IFDDA-like)
    """
    spec = engine_cfg.get("aeff")
    if not spec:
        return None

    unit = spec.get("unit", "meter")

    # Case A: direct AEFF pattern
    if "pattern" in spec:
        source = spec.get("source", "stdout")
        paths = [stdout_path] if source == "stdout" else extra_paths
        val = _read_first_match(paths, spec["pattern"])
        if val is None:
            return None
        return _to_meters(val, unit)

    # Case B: reconstruct from DDA discretization
    n_pat = spec.get("n_dipoles_pattern")
    d_pat = spec.get("mesh_size_pattern")
    if not n_pat or not d_pat:
        return None

    n = _read_first_match([stdout_path], n_pat)
    d = _read_first_match([stdout_path], d_pat)
    if n is None or d is None or n <= 0 or d <= 0:
        return None

    d_m = _to_meters(d, unit)  # unit refers to mesh size unit here

    # V = N * d^3 ; aeff = (3V/4π)^(1/3)
    V = float(n) * (d_m**3)
    aeff = (3.0 * V / (4.0 * math.pi)) ** (1.0 / 3.0)
    return aeff
