import os
import argparse
import logging
from pathlib import Path
from dda_bench.config import (
    OUTPUT_DIR,
    CLEAN_OUTPUT,
    DEFAULT_COMMAND_FILE_SOLVER,
    DEFAULT_COMMAND_FILE_FULL,
    DEFAULT_COMMAND_FILE_INTERNALFIELD,
    DDA_CODES_JSON,
)
from dda_bench.commands import read_command_cases
from dda_bench.extractors import load_engine_config
from dda_bench.reporters import process_all_cases, write_summary_csv
from dda_bench.utils import clean_output_files


def build_logger(check: bool) -> logging.Logger:
    logger = logging.getLogger("compare_digits")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(levelname)s | %(message)s")

    logfile_handler = logging.FileHandler("compare_digits.log")
    logfile_handler.setLevel(logging.INFO)
    logfile_handler.setFormatter(formatter)
    logger.addHandler(logfile_handler)

    errorfile_handler = logging.FileHandler("compare_digits.errors.log")
    errorfile_handler.setLevel(logging.ERROR)
    errorfile_handler.setFormatter(formatter)
    logger.addHandler(errorfile_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR if check else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run groups of DDA commands and compare digits."
    )
    parser.add_argument(
        "--with-stats",
        action="store_true",
        help="Enable /usr/bin/time measurements.",
    )
    parser.add_argument(
        "-fp",
        "--full",
        action="store_true",
        help="Use the full-precision command file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Compute the Force.",
    )
    parser.add_argument(
        "--int",
        dest="int_field",
        action="store_true",
        help="Compute the Internal Field.",
    )
    parser.add_argument(
        "-ci",
        "--check",
        action="store_true",
        help="CI/CD mode: minimal output, fails on mismatch",
    )

    args = parser.parse_args()

    command_file = (
        DEFAULT_COMMAND_FILE_FULL if args.full else DEFAULT_COMMAND_FILE_SOLVER
    )

    quantities = ["Cext", "Cabs", "residual1", "Qext", "Qabs"]
    if args.force:
        quantities.append("force")
    if args.int_field:
        command_file = DEFAULT_COMMAND_FILE_INTERNALFIELD
        quantities.append("int_field")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    engines_cfg = load_engine_config(DDA_CODES_JSON)
    cases = read_command_cases(command_file)

    logger = build_logger(args.check)

    ok = process_all_cases(
        cases=cases,
        engines_cfg=engines_cfg,
        output_dir=OUTPUT_DIR,
        logger=logger,
        quantities=quantities,
        with_stats=args.with_stats,
        check=args.check,
        full_precision=args.full,
    )

    write_summary_csv(
        output_dir=OUTPUT_DIR,
        csv_path=str(Path(OUTPUT_DIR) / "summary.csv"),
    )

    if CLEAN_OUTPUT:
        clean_output_files(OUTPUT_DIR)

    if args.check and not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
