import math
from pathlib import Path
from typing import Any
from .commands import CommandCase
from .executors import run_case_command
from .extractors import (
    detect_engine_from_cmd,
    extract_quantity_for_engine,
    extract_series_for_engine,
    compute_mean_relative_error,
    extract_aeff_meters_for_engine,
    extract_lambda_meters_for_engine,
)
from .comparators import (
    digits,
    compare_extabs,
    mueller_digits_from_column_mean_rel_errors,
    aligned_force_metric,
    aligned_torque_metric,
)
from .io_results import write_case_results
from .utils import (
    compute_rel_err,
    matching_digits_from_rel_err,
)

# display widths
CASE_W = 50
ENGINE_W = 7
QNAME_W = 3  # label width like "Ext", "Abs", "residual1", "int_field", "force"

# ---------------------------------------------------------------------
# Meta parsing: tolerances + skip_pairs
# ---------------------------------------------------------------------


def _parse_int_pair(
    meta: dict[str, str], kmin: str, kmax: str
) -> tuple[int, int] | None:
    if kmin not in meta and kmax not in meta:
        return None
    if kmin not in meta or kmax not in meta:
        raise ValueError(
            f"Case meta must define both {kmin} and {kmax}. Got: {meta}"
        )
    a = int(meta[kmin])
    b = int(meta[kmax])
    if a > b:
        raise ValueError(
            f"Invalid tolerance range {a} {b} for keys {kmin}/{kmax}"
        )
    return a, b


def _case_tol_ranges(
    case: CommandCase,
) -> tuple[
    tuple[int, int],
    tuple[int, int],
    tuple[int, int],
    tuple[int, int] | None,
    tuple[int, int] | None,
    tuple[int, int] | None,
    tuple[int, int] | None,
]:
    """
    Rules (enforced by read_command_cases()):
      - EITHER:
          A) @tol: <min> <max>              -> applies to BOTH Ext and Abs
        OR
          B) @tol_ext: <min> <max> AND @tol_abs: <min> <max>
      - ALWAYS:
          @tol_res: <min> <max>

    Optional (but can be required if the case is tagged need_int/need_force):
      - @tol_int: <min> <max>
      - @tol_force: <min> <max>
      - @tol_torque: <min> <max>
      - @tol_mueller: <min> <max>

    Returns:
      (tol_ext, tol_abs, tol_res, tol_int_or_none, tol_force_or_none, tol_torque_or_none, tol_mueller_or_none)
    """
    meta = case.meta or {}

    tol = _parse_int_pair(meta, "tol_min", "tol_max")
    tol_ext = _parse_int_pair(meta, "tol_ext_min", "tol_ext_max")
    tol_abs = _parse_int_pair(meta, "tol_abs_min", "tol_abs_max")

    tol_res = _parse_int_pair(meta, "tol_res_min", "tol_res_max")
    if tol_res is None:
        # should not happen if read_command_cases validates, but keep safe
        raise ValueError(
            f"Case '{case.case_id}' must define @tol_res: <min> <max>."
        )

    need_int = meta.get("need_int") == "1"
    need_force = meta.get("need_force") == "1"
    need_torque = meta.get("need_torque") == "1"
    need_mueller = meta.get("need_mueller") == "1"
    tol_int = _parse_int_pair(meta, "tol_int_min", "tol_int_max")
    tol_force = _parse_int_pair(meta, "tol_force_min", "tol_force_max")
    tol_torque = _parse_int_pair(meta, "tol_torque_min", "tol_torque_max")
    tol_mueller = _parse_int_pair(meta, "tol_mueller_min", "tol_mueller_max")

    if tol is not None:
        # forbid mixing (safety; normally already validated)
        if tol_ext is not None or tol_abs is not None:
            raise ValueError(
                f"Case '{case.case_id}' mixes @tol with @tol_ext/@tol_abs."
            )
        # if need_int/need_force, enforce presence
        if need_int and tol_int is None:
            raise ValueError(
                f"Case '{case.case_id}' has @need_int but no @tol_int."
            )
        if need_force and tol_force is None:
            raise ValueError(
                f"Case '{case.case_id}' has @need_force but no @tol_force."
            )
        if need_torque and tol_torque is None:
            raise ValueError(
                f"Case '{case.case_id}' has @need_torque but no @tol_torque."
            )
        if need_mueller and tol_mueller is None:
            raise ValueError(
                f"Case '{case.case_id}' has @need_mueller but no @tol_mueller."
            )
        return (
            tol,
            tol,
            tol_res,
            tol_int,
            tol_force,
            tol_torque,
            tol_mueller,
        )

    # no @tol => need ext+abs (safety; normally already validated)
    if tol_ext is None or tol_abs is None:
        raise ValueError(
            f"Case '{case.case_id}' must define BOTH @tol_ext and @tol_abs when @tol is absent."
        )

    # enforce need_int/need_force => tol present
    if need_int and tol_int is None:
        raise ValueError(
            f"Case '{case.case_id}' has @need_int but no @tol_int."
        )
    if need_force and tol_force is None:
        raise ValueError(
            f"Case '{case.case_id}' has @need_force but no @tol_force."
        )
    if need_torque and tol_torque is None:
        raise ValueError(
            f"Case '{case.case_id}' has @need_torque but no @tol_torque."
        )
    if need_mueller and tol_mueller is None:
        raise ValueError(
            f"Case '{case.case_id}' has @need_mueller but no @tol_mueller."
        )

    return (
        tol_ext,
        tol_abs,
        tol_res,
        tol_int,
        tol_force,
        tol_torque,
        tol_mueller,
    )


def _parse_skip_pairs(
    case: CommandCase,
    engines_cfg: dict[str, Any],
) -> set[tuple[str, str]]:
    """
    meta["skip_pairs"] is a list of (engineA, engineB) tuples.
    Returns a symmetric set containing (a,b) and (b,a).

    Safety:
      - raises if an engine name is not present in engines_cfg
    """
    meta = case.meta or {}
    raw = meta.get("skip_pairs")
    if not raw:
        return set()

    if not isinstance(raw, list):
        raise ValueError(
            f"Case '{case.case_id}': meta['skip_pairs'] must be a list of pairs"
        )

    out: set[tuple[str, str]] = set()
    for pair in raw:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not pair[0]
            or not pair[1]
        ):
            raise ValueError(
                f"Case '{case.case_id}': invalid skip_pairs entry: {pair}"
            )

        a, b = pair[0].strip(), pair[1].strip()

        # validate against dda_codes.json keys
        if a not in engines_cfg:
            raise ValueError(
                f"Case '{case.case_id}': @skip_pairs refers to unknown engine '{a}' "
                "(not found in dda_codes.json)."
            )
        if b not in engines_cfg:
            raise ValueError(
                f"Case '{case.case_id}': @skip_pairs refers to unknown engine '{b}' "
                "(not found in dda_codes.json)."
            )

        out.add((a, b))
        out.add((b, a))

    return out


# ---------------------------------------------------------------------
# C<->Q filling (always for results.json / summary.csv)
# ---------------------------------------------------------------------


def _fill_cq(
    vals: dict[str, float], src: dict[str, str], aeff_m: float
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


def _add_recomputed_quantities(
    eng: str,
    per_vals: dict[str, dict[str, float]],
    per_src: dict[str, dict[str, str]],
) -> None:
    """
    Add recalculated quantities to outputs.
    """
    vals = per_vals.setdefault(eng, {})
    src = per_src.setdefault(eng, {})

    name_cpr, cpr_val = aligned_force_metric(eng, per_vals)
    if cpr_val is not None and name_cpr == "Cpr*":
        vals["Cpr_recalc"] = cpr_val
        src["Cpr_recalc"] = "derived"

    name_qtrq, qtrq_val = aligned_torque_metric(eng, per_vals)
    if qtrq_val is not None and name_qtrq == "Qtrq*":
        vals["Qtrq_recalc"] = qtrq_val
        src["Qtrq_recalc"] = "derived"


def _build_case_quantities(
    quantities: list[str],
    need_int: bool,
    need_force: bool,
    need_torque: bool,
    need_mueller: bool,
) -> list[str]:
    """
    Build per-case quantity list based on needs.
    """
    case_quantities: list[str] = []
    for q in quantities:
        if q == "int_field" and not need_int:
            continue
        if q == "E0" and not (need_int or need_force or need_torque):
            continue
        if q in ("force", "Cpr") and not need_force:
            continue
        if q in ("torque", "Qtrq") and not need_torque:
            continue
        if q == "mueller" and not need_mueller:
            continue
        case_quantities.append(q)

    # Ensure required quantities exist even if caller omitted them
    if need_int and "int_field" not in case_quantities:
        case_quantities.append("int_field")
    if (need_int or need_force or need_torque) and "E0" not in case_quantities:
        case_quantities.append("E0")
    if need_force and "force" not in case_quantities:
        case_quantities.append("force")
    if need_torque and "torque" not in case_quantities:
        case_quantities.append("torque")
    if need_mueller and "mueller" not in case_quantities:
        case_quantities.append("mueller")

    return case_quantities


def _run_and_extract_case_commands(
    case_cmds: list[tuple[str, int]],
    case_id: str | None,
    engines_cfg: dict[str, Any],
    output_dir: str,
    case_quantities: list[str],
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, dict[str, str]],
    dict[str, list[Path]],
]:
    """
    Run all commands of one case and extract scalar quantities.
    """
    per_engine_values: dict[str, dict[str, float]] = {}
    per_engine_sources: dict[str, dict[str, str]] = {}
    per_engine_files: dict[str, list[Path]] = {}

    for cmd_idx, (cmd, _) in enumerate(case_cmds):
        engine = detect_engine_from_cmd(cmd, engines_cfg)
        engine_cfg = engines_cfg.get(engine, {})

        _, stdout_path = run_case_command(
            cmd=cmd,
            engine=engine,
            engine_cfg=engine_cfg,
            case_id=case_id,
            cmd_idx=cmd_idx,
            output_dir=output_dir,
        )

        per_engine_files.setdefault(engine, []).append(stdout_path)
        per_engine_values.setdefault(engine, {})
        per_engine_sources.setdefault(engine, {})

        for q in case_quantities:
            val = extract_quantity_for_engine(engine_cfg, q, stdout_path)
            if val is not None:
                per_engine_values[engine][q] = val
                per_engine_sources[engine][q] = "raw"

    return per_engine_values, per_engine_sources, per_engine_files


def _enrich_engine_quantities(
    per_engine_values: dict[str, dict[str, float]],
    per_engine_sources: dict[str, dict[str, str]],
    per_engine_files: dict[str, list[Path]],
    engines_cfg: dict[str, Any],
    engines_in_case: list[str],
) -> None:
    """
    Add AEFF/lambda and derived quantities used by comparisons and outputs.
    """
    per_engine_aeff: dict[str, float] = {}
    for eng, files in per_engine_files.items():
        stdout0 = files[0] if files else None
        if not stdout0:
            continue

        run_dir = stdout0.parent
        extra_paths: list[Path] = []
        for pat in engines_cfg.get(eng, {}).get("extra_files", []):
            extra_paths += list(run_dir.glob(pat))

        aeff_m = extract_aeff_meters_for_engine(
            engines_cfg.get(eng, {}),
            stdout_path=stdout0,
            extra_paths=extra_paths,
        )
        if aeff_m:
            per_engine_aeff[eng] = aeff_m

    for eng, aeff_m in per_engine_aeff.items():
        vals = per_engine_values.setdefault(eng, {})
        src = per_engine_sources.setdefault(eng, {})
        vals["aeff"] = aeff_m
        src["aeff"] = "raw"
        _fill_cq(vals, src, aeff_m)

    for eng, files in per_engine_files.items():
        stdout0 = files[0] if files else None
        if not stdout0:
            continue
        lambda_m = extract_lambda_meters_for_engine(
            engines_cfg.get(eng, {}),
            stdout_path=stdout0,
        )
        if lambda_m is not None:
            per_engine_values.setdefault(eng, {})["lambda"] = lambda_m
            per_engine_sources.setdefault(eng, {})["lambda"] = "raw"

    for eng in engines_in_case:
        _add_recomputed_quantities(eng, per_engine_values, per_engine_sources)


# ---------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------


def process_all_cases(
    cases: list[CommandCase],
    engines_cfg: dict[str, Any],
    output_dir: str,
    logger,
    quantities: list[str],
) -> None:
    for case in cases:
        _process_one_case(
            case=case,
            engines_cfg=engines_cfg,
            output_dir=output_dir,
            logger=logger,
            quantities=quantities,
        )


def _process_one_case(
    case: CommandCase,
    engines_cfg: dict[str, Any],
    output_dir: str,
    logger,
    quantities: list[str],
) -> None:
    case_id = case.case_id
    case_cmds = case.commands
    meta = case.meta or {}

    (
        tol_ext,
        tol_abs,
        tol_res,
        tol_int,
        tol_force,
        tol_torque,
        tol_mueller,
    ) = _case_tol_ranges(case)
    (tol_ext_min, tol_ext_max) = tol_ext
    (tol_abs_min, tol_abs_max) = tol_abs
    (tol_res_min, tol_res_max) = tol_res
    (tol_int_min, tol_int_max) = tol_int if tol_int else (None, None)

    need_int = meta.get("need_int") == "1"
    need_force = meta.get("need_force") == "1"
    need_torque = meta.get("need_torque") == "1"
    need_mueller = meta.get("need_mueller") == "1"

    skip_pairs = _parse_skip_pairs(case, engines_cfg)

    case_quantities = _build_case_quantities(
        quantities=quantities,
        need_int=need_int,
        need_force=need_force,
        need_torque=need_torque,
        need_mueller=need_mueller,
    )

    per_engine_values, per_engine_sources, per_engine_files = (
        _run_and_extract_case_commands(
            case_cmds=case_cmds,
            case_id=case_id,
            engines_cfg=engines_cfg,
            output_dir=output_dir,
            case_quantities=case_quantities,
        )
    )

    engines_in_case = list(per_engine_values.keys())
    engines_set = set(engines_in_case)
    for a, b in skip_pairs:
        if a not in engines_set or b not in engines_set:
            logger.warning(
                f"{case_id}: @skip_pairs ({a},{b}) but one/both engines not in this case "
                f"(present: {sorted(engines_set)})"
            )

    _enrich_engine_quantities(
        per_engine_values=per_engine_values,
        per_engine_sources=per_engine_sources,
        per_engine_files=per_engine_files,
        engines_cfg=engines_cfg,
        engines_in_case=engines_in_case,
    )

    # 3) pairwise compare
    # We DISPLAY "Ext" and "Abs" instead of Cext/Cabs/Qext/Qabs columns,
    # but results.json still contains everything (raw + derived).
    for i in range(len(engines_in_case)):
        for j in range(i + 1, len(engines_in_case)):
            eng_i = engines_in_case[i]
            eng_j = engines_in_case[j]

            # --- skip requested pairs for this case ---
            if (eng_i, eng_j) in skip_pairs:
                logger.info(
                    " | ".join(
                        [
                            f"{(case_id or 'unknown_case'):<{CASE_W}}",
                            f"{eng_i:<{ENGINE_W}}",
                            f"{eng_j:<{ENGINE_W}}",
                            f"{'SKIP':<{QNAME_W}}:@skip_pairs",
                        ]
                    )
                )
                continue

            line_parts = [
                f"{(case_id or 'unknown_case'):<{CASE_W}}",
                f"{eng_i:<{ENGINE_W}}",
                f"{eng_j:<{ENGINE_W}}",
            ]

            pair_failed = False

            # --- Ext / Abs ---
            ext_txt, ext_bad = compare_extabs(
                per_vals=per_engine_values,
                per_src=per_engine_sources,
                eng_i=eng_i,
                eng_j=eng_j,
                c_key="Cext",
                q_key="Qext",
                tol_min=tol_ext_min,
                tol_max=tol_ext_max,
            )
            line_parts.append(f"{'Ext':<{QNAME_W}}:{ext_txt}")
            if ext_bad:
                pair_failed = True

            abs_txt, abs_bad = compare_extabs(
                per_vals=per_engine_values,
                per_src=per_engine_sources,
                eng_i=eng_i,
                eng_j=eng_j,
                c_key="Cabs",
                q_key="Qabs",
                tol_min=tol_abs_min,
                tol_max=tol_abs_max,
            )
            line_parts.append(f"{'Abs':<{QNAME_W}}:{abs_txt}")
            if abs_bad:
                pair_failed = True
            # --- residual1 (always displayed if requested) ---
            if "residual1" in case_quantities:
                q = "residual1"
                v_i = per_engine_values.get(eng_i, {}).get(q)
                v_j = per_engine_values.get(eng_j, {}).get(q)

                if v_i is None or v_j is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                else:
                    d = digits(v_i, v_j)
                    if d is None:
                        line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                        pair_failed = True
                    else:
                        bad = d < tol_res_min or d > tol_res_max
                        line_parts.append(
                            f"{q:<{QNAME_W}}:{d}{'❌' if bad else ''}"
                        )
                        if bad:
                            pair_failed = True

            # --- int_field (only for cases that need it) ---
            if need_int:
                q = "int_field"

                if tol_int is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                else:
                    tol_int_min, tol_int_max = tol_int

                    # stdout paths for THIS pair
                    files_i = per_engine_files.get(eng_i)
                    files_j = per_engine_files.get(eng_j)
                    out_i = files_i[0] if files_i else None
                    out_j = files_j[0] if files_j else None

                    if not out_i or not out_j:
                        # if the case requires int_field, missing outputs fail
                        line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                        pair_failed = True
                    else:
                        cfg_i = engines_cfg.get(eng_i, {})
                        cfg_j = engines_cfg.get(eng_j, {})

                        series_i = extract_series_for_engine(
                            cfg_i,
                            q,
                            out_i,
                            per_engine_values=per_engine_values.get(eng_i, {}),
                        )
                        series_j = extract_series_for_engine(
                            cfg_j,
                            q,
                            out_j,
                            per_engine_values=per_engine_values.get(eng_j, {}),
                        )

                        if series_i and series_j:
                            rel = compute_mean_relative_error(
                                series_i, series_j
                            )
                            d = (
                                matching_digits_from_rel_err(rel)
                                if rel is not None
                                else None
                            )

                            if d is None:
                                line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                                pair_failed = True
                            else:
                                bad = d < tol_int_min or d > tol_int_max
                                line_parts.append(
                                    f"{q:<{QNAME_W}}:{d}{'❌' if bad else ''}"
                                )
                                if bad:
                                    pair_failed = True
                        else:
                            # Case requires int_field but don't provide it
                            line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                            pair_failed = True

            # --- force (only for cases that need it) ---
            if need_force:
                q = "force"

                # We always try to compare a consistent metric:
                # Prefer Cpr (raw), else derive Cpr from (force,E0).
                name_i, v_i = aligned_force_metric(eng_i, per_engine_values)
                name_j, v_j = aligned_force_metric(eng_j, per_engine_values)

                # If one side is Cpr/Cpr* and the other is force,
                # we refuse comparison as they are not directly comparable
                consistent = True
                if (name_i.startswith("Cpr") and name_j == "force") or (
                    name_j.startswith("Cpr") and name_i == "force"
                ):
                    consistent = False

                if not consistent:
                    # No meaningful comparison for this pair
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                elif v_i is None or v_j is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                    pair_failed = True
                else:
                    rel = compute_rel_err(v_i, v_j)
                    d = matching_digits_from_rel_err(rel)
                    if d is None:
                        line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                        pair_failed = True
                    else:
                        tol_force_min, tol_force_max = (
                            tol_force if tol_force else (0, 10**9)
                        )
                        bad = d < tol_force_min or d > tol_force_max

                        # display which metric was used
                        # examples: "12Cpr", "9Cpr*", "7force"
                        label = (
                            name_i
                            if name_i == name_j
                            else (name_i if "*" in name_i else name_j)
                        )

                        line_parts.append(
                            f"{q:<{QNAME_W}}:{d}{label}{'❌' if bad else ''}"
                        )
                        if bad:
                            pair_failed = True
            # --- force (only for cases that need it) ---
            if need_torque:
                q = "torque"

                # We always try to compare a consistent metric:
                # Prefer Qtrq (raw),
                # else derive Qtrq from (torque,E0,lambda,aeff).
                name_i, v_i = aligned_torque_metric(
                    eng_i,
                    per_engine_values,
                )
                name_j, v_j = aligned_torque_metric(
                    eng_j,
                    per_engine_values,
                )

                # If one side is Qtrq/Qtrq* and the other is NA,
                # we refuse comparison as they are not directly comparable
                consistent = True
                if (name_i.startswith("Qtrq") and name_j == "NA") or (
                    name_j.startswith("Qtrq") and name_i == "NA"
                ):
                    consistent = False

                if not consistent:
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                elif v_i is None or v_j is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                    pair_failed = True
                else:
                    rel = compute_rel_err(v_i, v_j)
                    d = matching_digits_from_rel_err(rel)
                    if d is None:
                        line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                        pair_failed = True
                    else:
                        tol_torque_min, tol_torque_max = (
                            tol_torque if tol_torque else (0, 10**9)
                        )
                        bad = d < tol_torque_min or d > tol_torque_max

                        # display which metric was used
                        # examples: "12Qtrq", "9Qtrq*", "7NA"
                        label = (
                            name_i
                            if name_i == name_j
                            else (name_i if "*" in name_i else name_j)
                        )

                        line_parts.append(
                            f"{q:<{QNAME_W}}:{d}{label}{'❌' if bad else ''}"
                        )
                        if bad:
                            pair_failed = True

            # --- mueller (only for cases that need it) ---
            if need_mueller:
                q = "mueller"
                if tol_mueller is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                else:
                    tol_mueller_min, tol_mueller_max = tol_mueller
                    files_i = per_engine_files.get(eng_i)
                    files_j = per_engine_files.get(eng_j)
                    out_i = files_i[0] if files_i else None
                    out_j = files_j[0] if files_j else None

                    if not out_i or not out_j:
                        line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                        pair_failed = True
                    else:
                        cfg_i = engines_cfg.get(eng_i, {})
                        cfg_j = engines_cfg.get(eng_j, {})

                        series_i = extract_series_for_engine(
                            cfg_i,
                            q,
                            out_i,
                            per_engine_values=per_engine_values.get(eng_i, {}),
                        )
                        series_j = extract_series_for_engine(
                            cfg_j,
                            q,
                            out_j,
                            per_engine_values=per_engine_values.get(eng_j, {}),
                        )

                        if series_i and series_j:
                            d = mueller_digits_from_column_mean_rel_errors(
                                series_i, series_j
                            )
                            if d is None:
                                line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                                pair_failed = True
                            else:
                                bad = (
                                    d < tol_mueller_min or d > tol_mueller_max
                                )
                                line_parts.append(
                                    f"{q:<{QNAME_W}}:{d}{'❌' if bad else ''}"
                                )
                                if bad:
                                    pair_failed = True
                        else:
                            line_parts.append(f"{q:<{QNAME_W}}:NA❌")
                            pair_failed = True

            # --- other generic scalar compares (optional, still supported) ---
            for q in case_quantities:
                if q in (
                    "Cext",
                    "Cabs",
                    "Qext",
                    "Qabs",
                    "residual1",
                    "int_field",
                    "force",
                    "E0",
                    "Cpr",
                    "torque",
                    "Qtrq",
                    "mueller",
                ):
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

                bad = d < tol_ext_min or d > tol_ext_max
                line_parts.append(f"{q:<{QNAME_W}}:{d}{'❌' if bad else ''}")
                if bad:
                    pair_failed = True

            line_str = " | ".join(line_parts)
            if pair_failed:
                logger.error(line_str)
            else:
                logger.info(line_str)

    # 4) persist results
    write_case_results(
        case_id=case_id,
        per_engine_values=per_engine_values,
        output_dir=output_dir,
    )

    return
