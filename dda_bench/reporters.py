import os
import sys
import logging
from typing import List, Tuple, Optional
from .config import (
    COL_WIDTH_LINE,
    COL_WIDTH_MATCH,
    COL_WIDTH_FORCE,
    COL_WIDTH_INT,
    COL_WIDTH_TIME,
    COL_WIDTH_MEM,
    ADDA_PATH,
    IFDDA_PATH,
)
from .commands import parse_command_lines
from .executors import process_pair
from .extractors import (
    extract_cpr_from_adda,
    extract_force_from_ifdda,
    extract_field_norm_from_ifdda,
    compute_internal_field_error,
)
from .utils import (
    find_adda_internal_field,
    extract_eps_from_adda,
    convert_to_SI_units,
    compute_rel_err,
    matching_digits_from_rel_err,
    clean_output_files,
)


def build_header(
    logger: logging.Logger, with_stats: bool, force: bool, int_field: bool
) -> None:
    columns = [
        ("Line", COL_WIDTH_LINE),
        ("Cext Match", COL_WIDTH_MATCH),
        ("Cabs Match", COL_WIDTH_MATCH),
    ]
    if force:
        columns.append(("Force Match", COL_WIDTH_FORCE))
    if int_field:
        columns.append(("IntField Match", COL_WIDTH_INT))
    if with_stats:
        columns.extend(
            [
                ("A_CPU", COL_WIDTH_TIME),
                ("A_MEM", COL_WIDTH_MEM),
                ("I_CPU", COL_WIDTH_TIME),
                ("I_MEM", COL_WIDTH_MEM),
            ]
        )

    header = " | ".join([f"{name:>{width}}" for name, width in columns])
    separator = "-" * len(header)
    logger.info(header)
    logger.info(separator)


def compute_force_digits(
    adda_out_path: str, ifdda_out_path: str, line_parts: List[str]
) -> Optional[int]:
    force_match_str = "N/A"
    digits_force = None
    adda_cpr = extract_cpr_from_adda(adda_out_path)
    if adda_cpr:
        ifdda_force = extract_force_from_ifdda(ifdda_out_path)
        norm = extract_field_norm_from_ifdda(ifdda_out_path)
        if norm and ifdda_force:
            epsilon_0 = 8.8541878176e-12
            fx, fy, fz = (c * norm**2 * epsilon_0 / 2 for c in adda_cpr)
            adda_force = (fx**2 + fy**2 + fz**2) ** 0.5
            adda_force = convert_to_SI_units(adda_force)
            force_rel_err = compute_rel_err(ifdda_force, adda_force)
            digits_force = matching_digits_from_rel_err(force_rel_err)
            force_match_str = f"{digits_force}"
    line_parts.append(f"{force_match_str:>{COL_WIDTH_FORCE}}")
    return digits_force


def compute_internal_field_digits(
    index: int, ifdda_out_path: str, ifdda_h5_path: str, line_parts: List[str]
) -> Optional[int]:
    int_field_err_str = "N/A"
    digits_int = None
    adda_field_path = find_adda_internal_field(index)
    if adda_field_path:
        norm = extract_field_norm_from_ifdda(ifdda_out_path)
        if norm:
            int_field_error = compute_internal_field_error(
                ifdda_h5_path, adda_field_path, norm
            )
            digits_int = matching_digits_from_rel_err(int_field_error)
            int_field_err_str = f"{digits_int}"
    line_parts.append(f"{int_field_err_str:>{COL_WIDTH_INT}}")
    return digits_int


def update_minimum_matching(
    match: Optional[int],
    line_number: int,
    current_min: int,
    lines: List[int],
    errors: List[int],
) -> Tuple[int, List[int], List[int]]:
    if match is not None:
        if match < current_min:
            return match, [line_number], [match]
        elif match == current_min:
            lines.append(line_number)
            errors.append(match)
    return current_min, lines, errors


def process_all_pairs(
    command_pairs: List[Tuple[Tuple[str, str], int]],
    output_dir: str,
    logger: logging.Logger,
    with_stats: bool = True,
    force: bool = True,
    int_field: bool = True,
    full_precision: bool = False,
    check: bool = True,
) -> None:
    """
    Run all command pairs and print a formatted summary of Cext and Cabs values
    and performance metrics. And also the minimum number of matching digits
    and the list of line numbers where this minimum occurs.
    """
    min_match_cext = 999
    min_lines: List[int] = []
    min_rel_errors: List[int] = []

    failed_lines: List[int] = []

    for i, ((adda_line, ifdda_line), line_number) in enumerate(command_pairs):
        adda_args = parse_command_lines(adda_line, "adda")
        ifdda_args = parse_command_lines(ifdda_line, "ifdda")

        adda_cmd = f"{ADDA_PATH} {adda_args}"
        ifdda_cmd = f"{IFDDA_PATH} {ifdda_args}"

        (
            match_cext,
            match_cabs,
            (adda_time, adda_mem),
            (ifdda_time, ifdda_mem),
        ) = process_pair(adda_cmd, ifdda_cmd, i, output_dir, with_stats)

        min_match_cext, min_lines, min_rel_errors = update_minimum_matching(
            match_cext, line_number, min_match_cext, min_lines, min_rel_errors
        )

        match_cext_str = (
            f"{match_cext}" if match_cext is not None else f"{'N/A':>11}"
        )
        match_cabs_str = (
            f"{match_cabs}" if match_cabs is not None else f"{'N/A':>11}"
        )

        # Build the line in parts
        line_parts = [
            f"{line_number:>{COL_WIDTH_LINE}}",
            f"{match_cext_str:>{COL_WIDTH_MATCH}}",
            f"{match_cabs_str:>{COL_WIDTH_MATCH}}",
        ]

        line_id = 12 + 3 * i
        adda_out_path = os.path.join(output_dir, f"line_{line_id}_adda.txt")
        ifdda_out_path = os.path.join(output_dir, f"line_{line_id}_ifdda.txt")
        ifdda_h5_path = "ifdda.h5"

        if force:
            match_force = compute_force_digits(
                adda_out_path, ifdda_out_path, line_parts
            )

        if int_field:
            match_int_field = compute_internal_field_digits(
                i, ifdda_out_path, ifdda_h5_path, line_parts
            )

        if with_stats:
            line_parts.extend(
                [
                    f"{(adda_time or 0):>{COL_WIDTH_TIME}.2f}",
                    f"{(adda_mem or 0) / 1024:>{COL_WIDTH_MEM}.2f}",
                    f"{(ifdda_time or 0):>{COL_WIDTH_TIME}.2f}",
                    f"{(ifdda_mem or 0) / 1024:>{COL_WIDTH_MEM}.2f}",
                ]
            )

        # Join line
        line_str = " | ".join(line_parts)

        if full_precision:
            min_digits = 11
            max_digits = 16
        else:
            eps = extract_eps_from_adda(adda_args, line_id, logger)
            min_digits = eps - 1
            max_digits = eps + 2

        # Decide if this line fails
        should_highlight = (
            (
                match_cext is not None
                and not (min_digits <= match_cext <= max_digits)
            )
            or (
                force
                and match_force
                and not (min_digits <= match_force <= max_digits)
            )
            or (
                int_field
                and match_int_field
                and not (min_digits <= match_int_field <= max_digits)
            )
        )

        if should_highlight:
            if check:
                failed_lines.append(line_number)
            logger.error(line_str)
        else:
            logger.info(line_str)

    if check:
        if failed_lines:
            logger.error(
                f"{len(failed_lines)} test(s) failed at lines: "
                f"{', '.join(map(str, failed_lines))}"
            )
            clean_output_files()
            sys.exit(1)
        else:
            logger.info("All tests passed.")
    else:
        logger.info(
            f"Minimum number of matching digits for Cext: {min_match_cext}"
        )
        logger.info(f"Occurred at line(s): {', '.join(map(str, min_lines))}")
