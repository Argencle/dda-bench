import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from .config import ADDA_PATH, IFDDA_PATH
from .commands import parse_command_lines


def build_real_command(cmd: str, engine: str) -> str:
    """
    Turn the 'logical' command from the tests file into the real one
    using the executable paths from config.
    """
    if engine == "adda":
        args = parse_command_lines(cmd, "adda")
        return f"{ADDA_PATH} {args}"
    if engine == "ifdda":
        args = parse_command_lines(cmd, "ifdda")
        return f"{IFDDA_PATH} {args}"
    return cmd


def run_command_with_stats(
    command: str, output_file: Path, with_stats: bool
) -> Tuple[Optional[float], Optional[int]]:
    if with_stats:
        time_log = output_file.with_suffix(output_file.suffix + ".time")
        full_cmd = f"/usr/bin/time -v {command}"
        with output_file.open("w") as out, time_log.open("w") as err:
            subprocess.run(full_cmd, shell=True, stdout=out, stderr=err)

        cpu_time = None
        max_mem_kb = None
        with time_log.open("r") as f:
            for line in f:
                if "User time (seconds):" in line:
                    cpu_time = float(line.split(":")[1].strip())
                elif "Maximum resident set size" in line:
                    max_mem_kb = int(line.split(":")[1].strip())
        return cpu_time, max_mem_kb
    else:
        with output_file.open("w") as out:
            subprocess.run(
                command, shell=True, stdout=out, stderr=subprocess.DEVNULL
            )
        return None, None


def _copy_extra_files(engine_cfg: Dict[str, Any], output_path: Path) -> None:
    extra_patterns: List[str] = engine_cfg.get("extra_files", [])
    if not extra_patterns:
        return

    extra_idx = 0
    for extra_pat in extra_patterns:
        pat_path = Path(extra_pat)
        if pat_path.is_absolute():
            candidate_paths = [pat_path]
        else:
            candidate_paths = Path(".").glob(extra_pat)

        for extra_path in candidate_paths:
            if not extra_path.exists():
                continue
            dest = output_path.with_name(
                f"{output_path.stem}_extra_{extra_idx:02d}_{extra_path.name}"
            )
            shutil.copyfile(extra_path, dest)
            extra_idx += 1


def run_group_command(
    cmd: str,
    engine: str,
    engine_cfg: Dict[str, Any],
    group_idx: int,
    cmd_idx: int,
    output_dir: str,
    with_stats: bool,
) -> Tuple[Path, Optional[float], Optional[int]]:
    output_path = (
        Path(output_dir) / f"group_{group_idx:03d}_{engine}_{cmd_idx:02d}.txt"
    )
    real_cmd = build_real_command(cmd, engine)
    cpu_time, mem = run_command_with_stats(real_cmd, output_path, with_stats)
    _copy_extra_files(engine_cfg, output_path)
    return output_path, cpu_time, mem
