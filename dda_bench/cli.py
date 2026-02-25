import os
import argparse
import logging
from importlib import resources
from pathlib import Path
from .commands import read_command_cases
from .extractors import load_engine_config
from .comparison import process_all_cases
from .io_results import write_summary_csv
from .utils import clean_output_files


DEFAULT_COMMAND_FILE = "DDA_commands"
DEFAULT_DDA_CODES_JSON = "dda_codes.json"
DEFAULT_BIN_DIR = "bin"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("dda_bench.cli")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(levelname)s | %(message)s")

    logfile_handler = logging.FileHandler("dda_bench.log")
    logfile_handler.setLevel(logging.INFO)
    logfile_handler.setFormatter(formatter)
    logger.addHandler(logfile_handler)

    errorfile_handler = logging.FileHandler("dda_bench.errors.log")
    errorfile_handler.setLevel(logging.ERROR)
    errorfile_handler.setFormatter(formatter)
    logger.addHandler(errorfile_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DDA cases and compare matching digits across engines."
    )

    parser.add_argument(
        "--commands",
        help="Command file path.",
    )
    parser.add_argument(
        "--code-config",
        help="Engine config JSON path.",
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
    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Create starter files (DDA_commands, dda_codes.json, and bin/) "
            "in current directory and exit."
        ),
    )

    return parser.parse_args()


def _resolve_input_files(args: argparse.Namespace) -> tuple[str, str]:
    commands_arg = args.commands
    config_arg = args.code_config
    default_commands = Path(DEFAULT_COMMAND_FILE)
    default_config = Path(DEFAULT_DDA_CODES_JSON)

    commands_path = (
        Path(commands_arg).expanduser().resolve()
        if commands_arg
        else (
            default_commands.resolve() if default_commands.exists() else None
        )
    )
    config_path = (
        Path(config_arg).expanduser().resolve()
        if config_arg
        else default_config.resolve() if default_config.exists() else None
    )

    if commands_path is None or config_path is None:
        raise FileNotFoundError(
            "Missing input files. Provide both --commands and --code-config, "
            "or place DDA_commands and dda_codes.json in the current directory, "
            "or run --init first."
        )

    return str(commands_path), str(config_path)


def _write_init_templates(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    dst_commands = target_dir / DEFAULT_COMMAND_FILE
    dst_codes = target_dir / DEFAULT_DDA_CODES_JSON
    dst_bin = target_dir / DEFAULT_BIN_DIR

    src_commands = resources.files("dda_bench").joinpath(
        f"examples/{DEFAULT_COMMAND_FILE}"
    )
    src_codes = resources.files("dda_bench").joinpath(
        f"examples/{DEFAULT_DDA_CODES_JSON}"
    )
    src_bin = resources.files("dda_bench").joinpath(DEFAULT_BIN_DIR)

    def _copy_tree(src, dst: Path, bin_root: Path) -> bool:
        if src.is_dir():
            copied_any = False
            for child in src.iterdir():
                if _copy_tree(child, dst / child.name, bin_root):
                    copied_any = True
            return copied_any

        rel = dst.relative_to(bin_root)
        keep = rel.parts[0] == "diel" or dst.suffix in {".dat", ".par"}
        if not keep:
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        return True

    dst_commands.write_text(src_commands.read_text())
    dst_codes.write_text(src_codes.read_text())
    dst_bin.mkdir(parents=True, exist_ok=True)
    for child in src_bin.iterdir():
        _copy_tree(child, dst_bin / child.name, dst_bin)

    print(f"Initialized templates in: {target_dir}")
    print(f"- {dst_commands.name}")
    print(f"- {dst_codes.name}")
    print(f"- {dst_bin.name}/")


def main() -> None:
    args = _parse_args()

    if args.init:
        _write_init_templates(Path.cwd())
        return

    commands_path, code_config_path = _resolve_input_files(args)

    # runtime env
    os.environ["OMP_NUM_THREADS"] = str(args.omp)

    # engine config
    engines_cfg = load_engine_config(Path(code_config_path))

    # quantities selection
    quantities = [
        "Cext",
        "Cabs",
        "residual1",
        "Qext",
        "Qabs",
        "int_field",
        "force",
        "E0",
        "Cpr",
        "torque",
        "Qtrq",
        "mueller",
    ]

    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # load cases
    cases = read_command_cases(commands_path)

    logger = _build_logger()

    process_all_cases(
        cases=cases,
        engines_cfg=engines_cfg,
        output_dir=output_dir,
        logger=logger,
        quantities=quantities,
    )

    write_summary_csv(
        output_dir=output_dir,
        csv_path=str(Path(output_dir) / "summary.csv"),
    )

    if args.clean:
        clean_output_files(output_dir, engines_cfg)


if __name__ == "__main__":
    main()
