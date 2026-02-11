import json
import re
import logging
import math
import h5py
import pandas as pd
from pathlib import Path
from typing import Any


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


def _read_quantity_from_text_file(
    output_path: Path,
    pattern: str,
    unit_factor: float = 1.0,
    take_last: bool = False,
    type: str = "text",
) -> float | None:
    if not output_path.exists():
        return None

    text = output_path.read_text()

    match: re.Match[str] | None

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


def _resolve_paths_from_spec(
    spec: dict[str, Any],
    main_output: Path,
) -> list[Path]:
    """
    Resolve file(s) to read depending on spec["source"].

    Supported:
      - source="run_dir"      + path
      - source="run_dir_glob" + pattern
      - source="stdout"       (main_output)
    """
    run_dir = main_output.parent
    src = spec.get("source", "stdout")

    if src == "stdout":
        return [main_output]

    if src == "run_dir":
        rel = spec.get("path")
        if not rel:
            return []
        return [run_dir / rel]

    if src == "run_dir_glob":
        pat = spec.get("pattern")
        if not pat:
            return []
        return list(run_dir.glob(pat))

    return []


def _apply_transforms(
    arr: list[float],
    transforms: list[dict[str, Any]],
    per_engine_values: dict[str, float],
) -> list[float] | None:
    out = arr

    for t in transforms or []:
        ttype = t.get("type")

        if ttype == "filter_nonzero":
            out = [x for x in out if x != 0.0]
            continue

        if ttype == "divide_by_quantity":
            q = t.get("quantity")
            if not q:
                return None
            denom = per_engine_values.get(q)
            if denom is None or denom == 0.0:
                return None
            out = [x / denom for x in out]
            continue

        if ttype == "square":
            out = [x * x for x in out]
            continue

        # unknown transform
        return None

    return out


def _run_sort_key(p: Path) -> int:
    m = re.search(r"run(\d+)", str(p))
    return int(m.group(1)) if m else -1


def extract_series_for_engine(
    engine_cfg: dict[str, Any],
    quantity: str,
    main_output: Path,
    per_engine_values: dict[str, float],
) -> list[float] | None:
    """
    Extract an array-like quantity (csv/hdf5) according to dda_codes.json spec.
    """
    spec = engine_cfg.get(quantity)
    if not spec:
        spec = (engine_cfg.get("outputs") or {}).get(quantity)

    if not spec:
        return None

    qtype = spec.get("type")
    if qtype not in ("hdf5", "csv"):
        return None

    paths = _resolve_paths_from_spec(spec, main_output)
    if not paths:
        return None

    select = spec.get("select", "first")
    if select == "last_run":
        paths = sorted(paths, key=_run_sort_key)
        path = paths[-1]
    else:
        path = paths[0]

    if qtype == "hdf5":
        dataset = spec.get("dataset")
        if not dataset:
            return None
        arr = _read_array_hdf5(path, dataset)
    else:
        sep = spec.get("sep", " ")
        column = spec.get("column")
        if not column:
            return None
        arr = _read_array_csv(path, sep, column)

    if arr is None:
        return None

    transforms = spec.get("transforms", [])
    if transforms:
        arr = _apply_transforms(
            arr, transforms, per_engine_values=per_engine_values
        )

    return arr


def _read_array_hdf5(path: Path, dataset: str) -> list[float] | None:
    if not path.exists():
        return None
    with h5py.File(path, "r") as f:
        data = f[dataset][()]
    # flatten + float
    return [float(x) for x in data.ravel()]


def _read_array_csv(path: Path, sep: str, column: str) -> list[float] | None:
    if not path.exists():
        return None
    df = pd.read_csv(path, sep=sep)
    if column not in df.columns:
        return None
    return [float(x) for x in df[column].to_numpy()]


def extract_quantity_for_engine(
    engine_cfg: dict[str, Any],
    quantity: str,
    main_output: Path,
) -> float | None:
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

    qtype = spec.get("type", "text")
    if qtype not in ("text", "text_vec3_norm"):
        # arrays are handled by extract_series_for_engine()
        return None

    pattern = spec["pattern"]
    unit_factor = spec.get("unit_factor", 1.0)
    take_last = spec.get("take_last", False)

    # 1) try main file
    val = _read_quantity_from_text_file(
        main_output,
        pattern,
        unit_factor=unit_factor,
        take_last=take_last,
        type=qtype,
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
            candidate_paths: list[Path] = [pat_path]
        else:
            # relative / glob pattern: keep existing behaviour
            candidate_paths = list(base_dir.glob(extra_pat))
        for extra_path in candidate_paths:
            val = _read_quantity_from_text_file(
                extra_path,
                pattern,
                unit_factor=unit_factor,
                take_last=take_last,
                type=qtype,
            )
            if val is not None:
                return val

    return None


def compute_internal_field_error(
    a: list[float],
    b: list[float],
) -> float | None:
    """
    Mean absolute relative error: mean( abs((a_i - b_i) / b_i) )
    """
    try:
        if not a or not b:
            return None
        if len(a) != len(b):
            return None
        n = min(len(a), len(b))
        if n == 0:
            return None

        s = 0.0
        k = 0

        for i in range(n):
            bi = b[i]
            if bi == 0.0:
                continue
            ai = a[i]
            s += abs((ai - bi) / bi)
            k += 1

        if k == 0:
            return None
        return s / k

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


def _read_first_match(paths: list[Path], pattern: str) -> float | None:
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
) -> float | None:
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
