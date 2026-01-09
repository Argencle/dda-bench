from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
from .extractors import (
    detect_engine_from_cmd,
    extract_quantity_for_engine,
    extract_cpr_from_adda,
    extract_force_from_ifdda,
    extract_field_norm_from_ifdda,
    find_adda_internal_field,
    compute_internal_field_error,
)
from .executors import run_group_command
from .utils import (
    compute_rel_err,
    matching_digits_from_rel_err,
    extract_eps_from_adda,
)


def _group_expected_range(
    group_cmds: List[Tuple[str, int]],
    engines_cfg: Dict[str, Any],
    full_precision: bool,
) -> Tuple[int, int]:
    """
    Decide ONE tolerance range for the WHOLE group.

    Priority:
    1. if full_precision: [11, 16]
    2. else: if ANY cmd in the group has '-eps N' → [N-1, N+2]
    3. else: [4, 7]
    """
    if full_precision:
        return 11, 16

    for cmd, _ in group_cmds:
        eps = extract_eps_from_adda(cmd)
        if eps is not None:
            return eps - 1, eps + 2

    # fallback if no -eps was found
    return 4, 7


def process_all_groups(
    groups: List[List[Tuple[str, int]]],
    engines_cfg: Dict[str, Any],
    output_dir: str,
    logger,
    quantities: List[str],
    with_stats: bool,
    check: bool,
    full_precision: bool,
) -> bool:
    all_ok = True
    for group_idx, group_cmds in enumerate(groups):
        ok = process_one_group(
            group_cmds=group_cmds,
            group_idx=group_idx,
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


def process_one_group(
    group_cmds: List[Tuple[str, int]],
    group_idx: int,
    engines_cfg: Dict[str, Any],
    output_dir: str,
    logger,
    quantities: List[str],
    with_stats: bool,
    check: bool,
    full_precision: bool,
) -> bool:
    """
    General, engine-agnostic:
    - run all commands of the group
    - read the quantities declared in JSON for each engine
    - compare every pair of engines on those quantities
    - use ONE tolerance range for the whole group (like your old script)
    """
    # 0) decide group tolerance
    group_min, group_max = _group_expected_range(
        group_cmds, engines_cfg, full_precision
    )

    # 1) run all commands
    per_engine_values: Dict[str, Dict[str, float]] = {}
    per_engine_stats: Dict[str, Tuple[Optional[float], Optional[int]]] = {}
    per_engine_files: Dict[str, List[Path]] = {}

    for cmd_idx, (cmd, lineno) in enumerate(group_cmds):
        engine = detect_engine_from_cmd(cmd, engines_cfg)
        out_path, cpu_time, mem = run_group_command(
            cmd=cmd,
            engine=engine,
            group_idx=group_idx,
            cmd_idx=cmd_idx,
            output_dir=output_dir,
            with_stats=with_stats,
        )
        per_engine_stats[engine] = (cpu_time, mem)
        per_engine_files.setdefault(engine, []).append(out_path)

        engine_cfg = engines_cfg.get(engine, {})
        per_engine_values.setdefault(engine, {})
        for q in quantities:
            val = extract_quantity_for_engine(engine, engine_cfg, q, out_path)
            if val is not None:
                per_engine_values[engine][q] = val

    engines_in_group = list(per_engine_values.keys())
    group_failed = False

    # 2) pairwise compare
    for i in range(len(engines_in_group)):
        for j in range(i + 1, len(engines_in_group)):
            eng_i = engines_in_group[i]
            eng_j = engines_in_group[j]

            line_parts = [
                f"group {group_idx:03d}",
                f"{eng_i:>8s}",
                f"{eng_j:>8s}",
            ]

            pair_failed = False

            for q in quantities:
                if q == "residual1":
                    v_i = per_engine_values.get(eng_i, {}).get(q)
                    v_j = per_engine_values.get(eng_j, {}).get(q)
                    if v_i is None or v_j is None:
                        line_parts.append(f"{q}:N/A")
                        continue
                    rel = compute_rel_err(v_i, v_j)
                    digits = matching_digits_from_rel_err(rel)
                    # show it, but don't fail
                    line_parts.append(
                        f"{q}:{digits if digits is not None else 'N/A'}❌"
                    )
                    continue

                if q == "int_field" and {"adda", "ifdda"} <= {eng_i, eng_j}:
                    # ADDA CSV
                    adda_csv = find_adda_internal_field(group_idx)
                    # IFDDA HDF5
                    ifdda_h5 = Path("ifdda.h5")
                    # IFDDA text output (to grab the norm)
                    ifdda_files = per_engine_files.get("ifdda", [])
                    ifdda_out = ifdda_files[0] if ifdda_files else None

                    if (
                        adda_csv
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
                            if digits is None or digits < group_min:
                                line_parts.append(
                                    f"{q}:{digits if digits is not None else 'N/A'}❌"
                                )
                                pair_failed = True
                            else:
                                line_parts.append(f"{q}:{digits}")
                            continue
                    line_parts.append(f"{q}:N/A")
                    continue

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
                        norm = extract_field_norm_from_ifdda(ifdda_out)
                        if cpr and ifdda_force and norm:
                            eps0 = 8.8541878176e-12
                            fx, fy, fz = (c * norm**2 * eps0 / 2 for c in cpr)
                            adda_force = (fx**2 + fy**2 + fz**2) ** 0.5
                            rel = compute_rel_err(ifdda_force, adda_force)
                            digits = matching_digits_from_rel_err(rel)
                            if digits is None or digits < group_min:
                                line_parts.append(
                                    f"{q}:{digits if digits is not None else 'N/A'}❌"
                                )
                                pair_failed = True
                            else:
                                line_parts.append(f"{q}:{digits}")
                            continue
                    line_parts.append(f"{q}:N/A")
                    continue

                v_i = per_engine_values.get(eng_i, {}).get(q)
                v_j = per_engine_values.get(eng_j, {}).get(q)

                if v_i is None or v_j is None:
                    line_parts.append(f"{q}:N/A")
                    continue

                rel = compute_rel_err(v_i, v_j)
                digits = matching_digits_from_rel_err(rel)

                if digits is None:
                    line_parts.append(f"{q}:N/A")
                    pair_failed = True
                    continue

                out_of_range = digits < group_min or digits > group_max

                if out_of_range:
                    line_parts.append(f"{q}:{digits}❌")
                    pair_failed = True
                else:
                    line_parts.append(f"{q}:{digits}")

            # stats
            if with_stats:
                cpu_i, mem_i = per_engine_stats.get(eng_i, (0.0, 0))
                cpu_j, mem_j = per_engine_stats.get(eng_j, (0.0, 0))
                line_parts.append(f"CPU_i={cpu_i or 0:.2f}s")
                line_parts.append(f"MEM_i={(mem_i or 0)/1024:.2f}MB")
                line_parts.append(f"CPU_j={cpu_j or 0:.2f}s")
                line_parts.append(f"MEM_j={(mem_j or 0)/1024:.2f}MB")

            line_str = " | ".join(line_parts)

            if pair_failed:
                group_failed = True
                logger.error(line_str)
            else:
                logger.info(line_str)

    return not group_failed
