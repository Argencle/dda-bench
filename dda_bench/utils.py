import math
import shutil
from pathlib import Path

_EPS0 = 8.854187817620389e-12  # F/m (vacuum permittivity)
_TWO_PI = 2.0 * math.pi


def compute_rel_err(val1: float | None, val2: float | None) -> float | None:
    """
    Relative error:
      rel = |v1 - v2| / max(|v1|, |v2|)
    """
    if val1 is None or val2 is None:
        return None
    den = max(abs(val1), abs(val2))
    if den == 0.0:
        return 0.0
    return abs(val1 - val2) / den


def matching_digits_from_rel_err(
    rel_err: float | None,
) -> int | None:
    """
    Convert relative error to matching decimal digits.
    - rel_err == 0 => cap digits (perfect match)
    - rel_err < 0 or NaN/inf => None
    """
    cap: int = 16
    if rel_err is None:
        return None
    if not math.isfinite(rel_err) or rel_err < 0:
        return None
    if rel_err == 0.0:
        return cap

    d = int(math.floor(-math.log10(rel_err)))
    if d < 0:
        d = 0
    if d > cap:
        d = cap
    return d


def _cpr_from_force(force_n: float, e0_field: float) -> float | None:
    """
    From: F = Cpr * |E0|^2 * eps0 / 2
    => Cpr = 2F / (eps0 * |E0|^2)
    Returns Cpr in m^2.
    """
    if e0_field == 0.0:
        return None
    return 2.0 * force_n / (_EPS0 * (e0_field**2))


def _qtrq_from_torque(
    torque_nm: float, lambda_m: float, aeff_m: float, e0_field: float
) -> float | None:
    """
    From: T_rad = Qtrq * pi * aeff^2 * |E0|^2 * eps0 / (2k)
    =>  Qtrq = T_rad * (2k) / (pi * aeff^2 * eps0 * |E0|^2)
    Returns Qtrq dimensionless.
    """
    if lambda_m == 0.0 or aeff_m == 0.0 or e0_field == 0.0:
        return None
    k = _TWO_PI / lambda_m
    return (
        torque_nm * (2.0 * k) / (math.pi * aeff_m**2 * _EPS0 * (e0_field**2))
    )


def aligned_torque_metric(
    eng: str, vals: dict[str, dict[str, float]]
) -> tuple[str, float | None]:
    """
    Return (metric_name, value) for torque comparison for one engine.

    Priority:
      1) if "Qtrq" exists => ("Qtrq", Qtrq)
      2) else if ("torque", "lambda", "aeff", "E0") exist => ("Qtrq*", Qtrq_from_torque)
      3) else => ("NA", None)
    """
    v = vals.get(eng, {})

    if "Qtrq" in v:
        return "Qtrq", v["Qtrq"]

    if "torque" in v and "lambda" in v and "aeff" in v and "E0" in v:
        qtrq = _qtrq_from_torque(v["torque"], v["lambda"], v["aeff"], v["E0"])
        return ("Qtrq*", qtrq)

    return "NA", None


def aligned_force_metric(
    eng: str, vals: dict[str, dict[str, float]]
) -> tuple[str, float | None]:
    """
    Return (metric_name, value) for force comparison for one engine.

    Priority:
      1) if "Cpr" exists => ("Cpr", Cpr)
      2) else if ("force" and "E0") exist => ("Cpr*", Cpr_from_force)
      3) else if "force" exists => ("force", force)
      4) else => ("NA", None)
    """
    v = vals.get(eng, {})

    if "Cpr" in v:
        return "Cpr", v["Cpr"]

    if "force" in v and "E0" in v:
        cpr = _cpr_from_force(v["force"], v["E0"])
        return ("Cpr*", cpr)

    if "force" in v:
        return "force", v["force"]

    return "NA", None


def clean_output_files(output_dir: str, engines_cfg: dict) -> None:
    """
    Clean only the files inside output_dir,
    using cleanup rules from engines_cfg (dda_codes.json).
    """
    out = Path(output_dir)
    if not out.exists():
        return

    remove_names: set[str] = set()
    remove_globs: list[str] = []

    # collect cleanup rules from all engines
    for _, cfg in engines_cfg.items():
        cleanup = cfg.get("cleanup", {})
        remove_names.update(cleanup.get("remove_names", []))
        remove_globs.extend(cleanup.get("remove_globs", []))

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
