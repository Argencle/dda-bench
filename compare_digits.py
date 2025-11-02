import os
import argparse
import logging
from dda_bench.config import (
    OUTPUT_DIR,
    CLEAN_OUTPUT,
    DEFAULT_COMMAND_FILE_SOLVER,
    DEFAULT_COMMAND_FILE_FULL,
)
from dda_bench.commands import read_command_pairs
from dda_bench.reporters import build_header, process_all_pairs
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


def main():
    parser = argparse.ArgumentParser(
        description="Compare ADDA and IFDDA Cext and Cabs results."
    )
    parser.add_argument(
        "--with-stats",
        action="store_true",
        help="Enable /usr/bin/time measurements",
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

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    command_pairs = read_command_pairs(command_file)

    logger = build_logger(args.check)
    build_header(logger, args.with_stats, args.force, args.int_field)

    process_all_pairs(
        command_pairs,
        OUTPUT_DIR,
        logger=logger,
        with_stats=args.with_stats,
        force=args.force,
        int_field=args.int_field,
        full_precision=args.full,
        check=args.check,
    )

    if CLEAN_OUTPUT:
        clean_output_files()


if __name__ == "__main__":
    main()
