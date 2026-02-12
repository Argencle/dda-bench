import math
from .extractors import compute_mean_relative_error
from .utils import compute_rel_err, matching_digits_from_rel_err

_EPS0 = 8.854187817620389e-12  # F/m (vacuum permittivity)
_TWO_PI = 2.0 * math.pi


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


def digits(a: float, b: float) -> int | None:
    rel = compute_rel_err(a, b)
    return matching_digits_from_rel_err(rel)


def mueller_digits_from_column_mean_rel_errors(
    a: list[float], b: list[float], ncols: int = 16
) -> int | None:
    """
    Mueller aggregation:
      1) reshape flat arrays as rows of ncols
      2) compute mean relative error for each column
      3) aggregate with min(mean_rel_error) across columns
      4) convert to matching digits
    """
    if not a or not b or len(a) != len(b) or ncols <= 0:
        return None
    if len(a) % ncols != 0:
        return None

    mean_rel_cols: list[float] = []
    for c in range(ncols):
        col_a = a[c::ncols]
        col_b = b[c::ncols]
        rel_col = compute_mean_relative_error(col_a, col_b)
        if rel_col is None:
            return None
        mean_rel_cols.append(rel_col)

    rel = min(mean_rel_cols)
    return matching_digits_from_rel_err(rel)


def compare_extabs(
    per_vals: dict[str, dict[str, float]],
    per_src: dict[str, dict[str, str]],
    eng_i: str,
    eng_j: str,
    c_key: str,
    q_key: str,
    tol_min: int,
    tol_max: int,
) -> tuple[str, bool]:
    """
    Returns:
      (display_token, failed_bool)

    Rules:
      1) If BOTH engines have RAW C => compare C and show "...C"
      2) Else if BOTH have RAW Q => compare Q and show "...Q"
      3) Else if both have C (raw+derived mix) => compare C and show "...C*"
      4) Else if both have Q (raw+derived mix) => compare Q and show "...Q*"
      5) Else => "NA" (no fail)
    """
    vi = per_vals.get(eng_i, {})
    vj = per_vals.get(eng_j, {})
    si = per_src.get(eng_i, {})
    sj = per_src.get(eng_j, {})

    if (
        c_key in vi
        and c_key in vj
        and si.get(c_key) == "raw"
        and sj.get(c_key) == "raw"
    ):
        d = digits(vi[c_key], vj[c_key])
        if d is None:
            return "NA❌", True
        bad = d < tol_min or d > tol_max
        return f"{d}C{'❌' if bad else ''}", bad

    if (
        q_key in vi
        and q_key in vj
        and si.get(q_key) == "raw"
        and sj.get(q_key) == "raw"
    ):
        d = digits(vi[q_key], vj[q_key])
        if d is None:
            return "NA❌", True
        bad = d < tol_min or d > tol_max
        return f"{d}Q{'❌' if bad else ''}", bad

    if c_key in vi and c_key in vj:
        d = digits(vi[c_key], vj[c_key])
        if d is None:
            return "NA❌", True
        bad = d < tol_min or d > tol_max
        return f"{d}C*{'❌' if bad else ''}", bad

    if q_key in vi and q_key in vj:
        d = digits(vi[q_key], vj[q_key])
        if d is None:
            return "NA❌", True
        bad = d < tol_min or d > tol_max
        return f"{d}Q*{'❌' if bad else ''}", bad

    return "NA", False
