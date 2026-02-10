import csv
import json
import math
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from .commands import CommandCase
from .executors import run_case_command
from .extractors import (
    detect_engine_from_cmd,
    extract_quantity_for_engine,
    extract_cpr_from_adda,
    extract_force_from_ifdda,
    extract_field_norm_from_ifdda,
    find_adda_internal_field_in_dir,
    compute_internal_field_error,
    extract_aeff_meters_for_engine,
)
from .utils import compute_rel_err, matching_digits_from_rel_err

# display widths
CASE_W = 45
ENGINE_W = 7
QNAME_W = 3  # label width like "Ext", "Abs", "residual1", ...

# ---------------------------------------------------------------------
# Helpers: results + summary
# ---------------------------------------------------------------------


def write_case_results(
    case_id: Optional[str],
    per_engine_values: Dict[str, Dict[str, float]],
    output_dir: str,
) -> None:
    if not case_id:
        case_id = "unknown_case"

    case_dir = Path(output_dir) / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    out = case_dir / "results.json"
    data: Dict[str, Any] = {"case": case_id, "engines": {}}

    for eng, vals in per_engine_values.items():
        data["engines"][eng] = dict(vals)

    out.write_text(json.dumps(data, indent=2))


def write_summary_csv(output_dir: str, csv_path: str) -> None:
    out = Path(output_dir)
    rows: List[Dict[str, Any]] = []

    for result_file in out.glob("*/results.json"):
        data = json.loads(result_file.read_text())
        case_id = data.get("case", "unknown_case")

        for eng, vals in data.get("engines", {}).items():
            row = {"case": case_id, "engine": eng, **vals}
            rows.append(row)

    if not rows:
        return

    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------
# Tolerance range
# ---------------------------------------------------------------------


def _case_expected_range(full_precision: bool) -> Tuple[int, int]:
    """
    Decide ONE tolerance range for the WHOLE case.

    Priority:
    1) full_precision => [11, 16]
    2) else => [4, 7]
    """
    if full_precision:
        return 11, 16
    return 4, 7


# ---------------------------------------------------------------------
# C<->Q filling (always for results.json / summary.csv)
# ---------------------------------------------------------------------


def _fill_cq(
    vals: Dict[str, float], src: Dict[str, str], aeff_m: float
) -> None:
    """
    Ensure we have (Cext,Cabs,Qext,Qabs) when possible.

    src[q] is:
      - "raw"    => extracted directly from code outputs
      - "derived"=> computed via Q<->C using aeff
    """
    area = math.pi * (aeff_m**2)  # m^2
    if area <= 0.0:
        return

    # If Q available but C missing
    if "Qext" in vals and "Cext" not in vals:
        vals["Cext"] = vals["Qext"] * area
        src["Cext"] = "derived"
    if "Qabs" in vals and "Cabs" not in vals:
        vals["Cabs"] = vals["Qabs"] * area
        src["Cabs"] = "derived"

    # If C available but Q missing
    if "Cext" in vals and "Qext" not in vals:
        vals["Qext"] = vals["Cext"] / area
        src["Qext"] = "derived"
    if "Cabs" in vals and "Qabs" not in vals:
        vals["Qabs"] = vals["Cabs"] / area
        src["Qabs"] = "derived"


# ---------------------------------------------------------------------
# Ext/Abs display logic (C vs Q, raw vs derived)
# ---------------------------------------------------------------------


def _digits(a: float, b: float) -> Optional[int]:
    rel = compute_rel_err(a, b)
    return matching_digits_from_rel_err(rel)


def _compare_extabs(
    per_vals: Dict[str, Dict[str, float]],
    per_src: Dict[str, Dict[str, str]],
    eng_i: str,
    eng_j: str,
    c_key: str,
    q_key: str,
    case_min: int,
    case_max: int,
) -> Tuple[str, bool]:
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

    # 1) raw C for both
    if (
        c_key in vi
        and c_key in vj
        and si.get(c_key) == "raw"
        and sj.get(c_key) == "raw"
    ):
        d = _digits(vi[c_key], vj[c_key])
        if d is None:
            return "NA❌", True
        bad = d < case_min or d > case_max
        return f"{d}C{'❌' if bad else ''}", bad

    # 2) raw Q for both
    if (
        q_key in vi
        and q_key in vj
        and si.get(q_key) == "raw"
        and sj.get(q_key) == "raw"
    ):
        d = _digits(vi[q_key], vj[q_key])
        if d is None:
            return "NA❌", True
        bad = d < case_min or d > case_max
        return f"{d}Q{'❌' if bad else ''}", bad

    # 3) both have C (derived)
    if c_key in vi and c_key in vj:
        d = _digits(vi[c_key], vj[c_key])
        if d is None:
            return "NA❌", True
        bad = d < case_min or d > case_max
        return f"{d}C*{'❌' if bad else ''}", bad

    # 4) both have Q (derived)
    if q_key in vi and q_key in vj:
        d = _digits(vi[q_key], vj[q_key])
        if d is None:
            return "NA❌", True
        bad = d < case_min or d > case_max
        return f"{d}Q*{'❌' if bad else ''}", bad

    # 5) no common metric
    return "NA", False


# ---------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------


def process_all_cases(
    cases: List[CommandCase],
    engines_cfg: Dict[str, Any],
    output_dir: str,
    logger,
    quantities: List[str],
    with_stats: bool,
    full_precision: bool,
) -> bool:
    all_ok = True
    for case in cases:
        ok = process_one_case(
            case=case,
            engines_cfg=engines_cfg,
            output_dir=output_dir,
            logger=logger,
            quantities=quantities,
            with_stats=with_stats,
            full_precision=full_precision,
        )
        if not ok:
            all_ok = False
    return all_ok


def process_one_case(
    case: CommandCase,
    engines_cfg: Dict[str, Any],
    output_dir: str,
    logger,
    quantities: List[str],
    with_stats: bool,
    full_precision: bool,
) -> bool:
    case_id = case.case_id
    case_cmds = case.commands

    case_min, case_max = _case_expected_range(full_precision)

    # 1) run all commands
    per_engine_values: Dict[str, Dict[str, float]] = {}
    per_engine_sources: Dict[str, Dict[str, str]] = {}  # raw/derived
    per_engine_stats: Dict[str, Tuple[Optional[float], Optional[int]]] = {}
    per_engine_files: Dict[str, List[Path]] = {}  # stdout files
    per_engine_run_dirs: Dict[str, List[Path]] = {}  # working dirs

    for cmd_idx, (cmd, lineno) in enumerate(case_cmds):
        engine = detect_engine_from_cmd(cmd, engines_cfg)
        engine_cfg = engines_cfg.get(engine, {})

        run_dir, stdout_path, cpu_time, mem = run_case_command(
            cmd=cmd,
            engine=engine,
            engine_cfg=engine_cfg,
            case_id=case_id,
            cmd_idx=cmd_idx,
            output_dir=output_dir,
            with_stats=with_stats,
        )

        per_engine_stats[engine] = (cpu_time, mem)
        per_engine_files.setdefault(engine, []).append(stdout_path)
        per_engine_run_dirs.setdefault(engine, []).append(run_dir)

        per_engine_values.setdefault(engine, {})
        per_engine_sources.setdefault(engine, {})

        for q in quantities:
            val = extract_quantity_for_engine(
                engine, engine_cfg, q, stdout_path
            )
            if val is not None:
                per_engine_values[engine][q] = val
                per_engine_sources[engine][q] = "raw"

    engines_in_case = list(per_engine_values.keys())
    case_failed = False

    # 2) compute AEFF + fill missing C<->Q for results (always)
    per_engine_aeff: Dict[str, float] = {}
    for eng, files in per_engine_files.items():
        stdout0 = files[0] if files else None
        if not stdout0:
            continue

        # extra paths live in run_dir (same directory as stdout files)
        run_dir = stdout0.parent
        extra_paths: List[Path] = []
        for pat in engines_cfg.get(eng, {}).get("extra_files", []):
            extra_paths += list(run_dir.glob(pat))

        aeff_m = extract_aeff_meters_for_engine(
            eng,
            engines_cfg.get(eng, {}),
            stdout_path=stdout0,
            extra_paths=extra_paths,
        )
        if aeff_m:
            per_engine_aeff[eng] = aeff_m

    for eng, aeff_m in per_engine_aeff.items():
        _fill_cq(
            per_engine_values.setdefault(eng, {}),
            per_engine_sources.setdefault(eng, {}),
            aeff_m,
        )

    # 3) pairwise compare
    # We DISPLAY "Ext" and "Abs" instead of Cext/Cabs/Qext/Qabs columns,
    # but results.json still contains everything (raw + derived).
    for i in range(len(engines_in_case)):
        for j in range(i + 1, len(engines_in_case)):
            eng_i = engines_in_case[i]
            eng_j = engines_in_case[j]

            line_parts = [
                f"{(case_id or 'unknown_case'):<{CASE_W}}",
                f"{eng_i:<{ENGINE_W}}",
                f"{eng_j:<{ENGINE_W}}",
            ]

            pair_failed = False

            # --- Ext / Abs ---
            ext_txt, ext_bad = _compare_extabs(
                per_vals=per_engine_values,
                per_src=per_engine_sources,
                eng_i=eng_i,
                eng_j=eng_j,
                c_key="Cext",
                q_key="Qext",
                case_min=case_min,
                case_max=case_max,
            )
            line_parts.append(f"{'Ext':<{QNAME_W}}:{ext_txt}")
            if ext_bad:
                pair_failed = True

            abs_txt, abs_bad = _compare_extabs(
                per_vals=per_engine_values,
                per_src=per_engine_sources,
                eng_i=eng_i,
                eng_j=eng_j,
                c_key="Cabs",
                q_key="Qabs",
                case_min=case_min,
                case_max=case_max,
            )
            line_parts.append(f"{'Abs':<{QNAME_W}}:{abs_txt}")
            if abs_bad:
                pair_failed = True

            # --- Then the rest of the quantities ---
            for q in quantities:
                # We do NOT display these 4
                if q in ("Cext", "Cabs", "Qext", "Qabs"):
                    continue

                # residuals => warning only (never fail)
                if q == "residual1":
                    v_i = per_engine_values.get(eng_i, {}).get(q)
                    v_j = per_engine_values.get(eng_j, {}).get(q)
                    if v_i is None or v_j is None:
                        line_parts.append(f"{q:<{QNAME_W}}:NA")
                        continue
                    d = _digits(v_i, v_j)
                    if d is None:
                        line_parts.append(f"{q:<{QNAME_W}}:NA")
                        continue
                    warn = d < case_min or d > case_max
                    line_parts.append(
                        f"{q:<{QNAME_W}}:{d}{'⚠️' if warn else ''}"
                    )
                    continue

                # internal field special compare (ADDA + IFDDA)
                if q == "int_field" and {"adda", "ifdda"} <= {eng_i, eng_j}:
                    adda_dirs = per_engine_run_dirs.get("adda", [])
                    ifdda_dirs = per_engine_run_dirs.get("ifdda", [])

                    adda_run = adda_dirs[0] if adda_dirs else None
                    ifdda_run = ifdda_dirs[0] if ifdda_dirs else None

                    adda_csv = (
                        find_adda_internal_field_in_dir(adda_run)
                        if adda_run
                        else None
                    )
                    ifdda_h5 = (ifdda_run / "ifdda.h5") if ifdda_run else None

                    ifdda_files = per_engine_files.get("ifdda", [])
                    ifdda_out = ifdda_files[0] if ifdda_files else None

                    if (
                        adda_csv
                        and adda_csv.exists()
                        and ifdda_h5
                        and ifdda_h5.exists()
                        and ifdda_out
                        and ifdda_out.exists()
                    ):
                        norm = extract_field_norm_from_ifdda(ifdda_out)
                        if norm:
                            rel = compute_internal_field_error(
                                ifdda_h5, adda_csv, norm
                            )
                            d = matching_digits_from_rel_err(rel)
                            if d is None or d < case_min:
                                line_parts.append(
                                    f"{q:<{QNAME_W}}:{d if d is not None else 'NA'}❌"
                                )
                                pair_failed = True
                            else:
                                line_parts.append(f"{q:<{QNAME_W}}:{d}")
                            continue

                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                    continue

                # force special compare (ADDA + IFDDA)
                if q == "force" and {"adda", "ifdda"} <= {eng_i, eng_j}:
                    adda_files = per_engine_files.get("adda", [])
                    ifdda_files = per_engine_files.get("ifdda", [])
                    adda_out = adda_files[0] if adda_files else None
                    ifdda_out = ifdda_files[0] if ifdda_files else None

                    if (
                        adda_out
                        and adda_out.exists()
                        and ifdda_out
                        and ifdda_out.exists()
                    ):
                        cpr = extract_cpr_from_adda(adda_out)
                        ifdda_force = extract_force_from_ifdda(ifdda_out)
                        ifdda_force = (
                            (ifdda_force * 1e12) if ifdda_force else None
                        )
                        norm = extract_field_norm_from_ifdda(ifdda_out)

                        if cpr and ifdda_force and norm:
                            eps0 = 8.854187817620389e-12
                            fx, fy, fz = (c * norm**2 * eps0 / 2 for c in cpr)
                            adda_force = (fx**2 + fy**2 + fz**2) ** 0.5

                            rel = compute_rel_err(ifdda_force, adda_force)
                            d = matching_digits_from_rel_err(rel)

                            if d is None or d < case_min:
                                line_parts.append(
                                    f"{q:<{QNAME_W}}:{d if d is not None else 'NA'}❌"
                                )
                                pair_failed = True
                            else:
                                line_parts.append(f"{q:<{QNAME_W}}:{d}")
                            continue

                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                    continue

                # generic scalar compare
                v_i = per_engine_values.get(eng_i, {}).get(q)
                v_j = per_engine_values.get(eng_j, {}).get(q)

                if v_i is None or v_j is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                    continue

                rel = compute_rel_err(v_i, v_j)
                d = matching_digits_from_rel_err(rel)

                if d is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                    pair_failed = True
                    continue

                bad = d < case_min or d > case_max
                line_parts.append(f"{q:<{QNAME_W}}:{d}{'❌' if bad else ''}")
                if bad:
                    pair_failed = True

            # stats
            if with_stats:
                cpu_i, mem_i = per_engine_stats.get(eng_i, (0.0, 0))
                cpu_j, mem_j = per_engine_stats.get(eng_j, (0.0, 0))
                line_parts.append(f"CPU_i={cpu_i or 0:.2f}s")
                line_parts.append(f"MEM_i={(mem_i or 0)/1024:.2f}MiB")
                line_parts.append(f"CPU_j={cpu_j or 0:.2f}s")
                line_parts.append(f"MEM_j={(mem_j or 0)/1024:.2f}MiB")

            line_str = " | ".join(line_parts)
            if pair_failed:
                case_failed = True
                logger.error(line_str)
            else:
                logger.info(line_str)

    # 4) persist results
    write_case_results(
        case_id=case_id,
        per_engine_values=per_engine_values,
        output_dir=output_dir,
    )

    return not case_failed
