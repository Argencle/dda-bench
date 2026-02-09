import os
import argparse
import logging
from pathlib import Path
from dda_bench.config import DDA_CODES_JSON
from dda_bench.commands import read_command_cases
from dda_bench.extractors import load_engine_config
from dda_bench.reporters import process_all_cases, write_summary_csv
from dda_bench.utils import clean_output_files


DEFAULTS = {
    "solver": "tests/DDA_commands_solverprecision",
    "full": "tests/DDA_commands_fullprecision",
    "force": "tests/DDA_commands_internalfield",
    "int": "tests/DDA_commands_internalfield",
}


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DDA cases and compare matching digits across engines."
    )

    parser.add_argument(
        "--mode",
        choices=["solver", "full", "force", "int"],
        default="full",
        help="Select preset command file + quantities (default: full).",
    )
    parser.add_argument(
        "--commands",
        default=None,
        help="Override command file path (takes precedence over --mode).",
    )

    parser.add_argument(
        "--with-stats",
        action="store_true",
        help="Enable /usr/bin/time measurements.",
    )
    parser.add_argument(
        "-ci",
        "--check",
        action="store_true",
        help="CI/CD mode: minimal output, fails on mismatch",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="outputs",
        help="Output directory (default: outputs)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean generated output files inside --output after run.",
    )
    parser.add_argument(
        "--omp",
        default="1",
        help="Set OMP_NUM_THREADS (default: 1).",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # runtime env
    os.environ["OMP_NUM_THREADS"] = str(args.omp)

    # engine config
    engines_cfg = load_engine_config(DDA_CODES_JSON)

    # command file selection
    command_file = args.commands if args.commands else DEFAULTS[args.mode]

    # quantities selection
    quantities = ["Cext", "Cabs", "residual1", "Qext", "Qabs"]
    if args.mode == "force":
        quantities.append("force")
    if args.mode == "int":
        quantities.append("int_field")

    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # load cases
    cases = read_command_cases(command_file)

    logger = build_logger(args.check)

    ok = process_all_cases(
        cases=cases,
        engines_cfg=engines_cfg,
        output_dir=output_dir,
        logger=logger,
        quantities=quantities,
        with_stats=args.with_stats,
        check=args.check,
        full_precision=(args.mode == "full"),
    )

    write_summary_csv(
        output_dir=output_dir,
        csv_path=str(Path(output_dir) / "summary.csv"),
    )

    if args.clean:
        clean_output_files(output_dir, engines_cfg)

    if args.check and not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
