from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path

from .commands import CommandCase
from .extractors import (
    detect_engine_from_cmd,
    extract_quantity_for_engine,
    extract_cpr_from_adda,
    extract_force_from_ifdda,
    extract_field_norm_from_ifdda,
    find_adda_internal_field_in_dir,
    compute_internal_field_error,
)
from .executors import run_case_command
from .utils import (
    compute_rel_err,
    matching_digits_from_rel_err,
    extract_eps_from_adda,
)

CASE_W = 45
ENGINE_W = 7
QNAME_W = 3


def _case_expected_range(
    case_cmds: List[Tuple[str, int]],
    engines_cfg: Dict[str, Any],
    full_precision: bool,
) -> Tuple[int, int]:
    """
    Decide ONE tolerance range for the WHOLE case.

    Priority:
    1. if full_precision: [11, 16]
    2. else: if ANY cmd in the case has '-eps N' → [N-1, N+2]
    3. else: [4, 7]
    """
    if full_precision:
        return 11, 16

    for cmd, _ in case_cmds:
        eps = extract_eps_from_adda(cmd)
        if eps is not None:
            return eps - 1, eps + 2

    return 4, 7


def process_all_cases(
    cases: List[CommandCase],
    engines_cfg: Dict[str, Any],
    output_dir: str,
    logger,
    quantities: List[str],
    with_stats: bool,
    check: bool,
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
            check=check,
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
    check: bool,
    full_precision: bool,
) -> bool:
    case_id = case.case_id
    case_cmds = case.commands

    # 0) decide tolerance for this case
    case_min, case_max = _case_expected_range(
        case_cmds, engines_cfg, full_precision
    )

    # 1) run all commands in this case
    per_engine_values: Dict[str, Dict[str, float]] = {}
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
        for q in quantities:
            val = extract_quantity_for_engine(
                engine, engine_cfg, q, stdout_path
            )
            if val is not None:
                per_engine_values[engine][q] = val

    engines_in_case = list(per_engine_values.keys())
    case_failed = False

    # 2) pairwise compare
    for i in range(len(engines_in_case)):
        for j in range(i + 1, len(engines_in_case)):
            eng_i = engines_in_case[i]
            eng_j = engines_in_case[j]

            line_parts = [
                f"{case_id:<{CASE_W}}",
                f"{eng_i:<{ENGINE_W}}",
                f"{eng_j:<{ENGINE_W}}",
            ]

            pair_failed = False

            for q in quantities:
                # residuals are displayed but do not fail the case (current behavior)
                if q == "residual1":
                    v_i = per_engine_values.get(eng_i, {}).get(q)
                    v_j = per_engine_values.get(eng_j, {}).get(q)
                    if v_i is None or v_j is None:
                        line_parts.append(f"{q:<{QNAME_W}}:N/A")
                        continue
                    rel = compute_rel_err(v_i, v_j)
                    digits = matching_digits_from_rel_err(rel)
                    line_parts.append(
                        f"{q:<{QNAME_W}}:{digits if digits is not None else 'NA'}❌"
                    )
                    continue

                # internal field special compare (requires ADDA + IFDDA)
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
                            digits = matching_digits_from_rel_err(rel)
                            if digits is None or digits < case_min:
                                line_parts.append(
                                    f"{q:<{QNAME_W}}:{digits if digits is not None else 'NA'}❌"
                                )
                                pair_failed = True
                            else:
                                line_parts.append(f"{q:<{QNAME_W}}:{digits}")
                            continue

                    line_parts.append(f"{q:<{QNAME_W}}:N/A")
                    continue

                # force special compare (requires ADDA + IFDDA)
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
                            digits = matching_digits_from_rel_err(rel)

                            if digits is None or digits < case_min:
                                line_parts.append(
                                    f"{q:<{QNAME_W}}:{digits if digits is not None else 'NA'}❌"
                                )
                                pair_failed = True
                            else:
                                line_parts.append(f"{q:<{QNAME_W}}:{digits}")
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
                digits = matching_digits_from_rel_err(rel)

                if digits is None:
                    line_parts.append(f"{q:<{QNAME_W}}:NA")
                    pair_failed = True
                    continue

                out_of_range = digits < case_min or digits > case_max
                if out_of_range:
                    line_parts.append(f"{q:<{QNAME_W}}:{digits}❌")
                    pair_failed = True
                else:
                    line_parts.append(f"{q:<{QNAME_W}}:{digits}")

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

    return not case_failed
