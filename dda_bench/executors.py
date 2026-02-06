import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from .config import ADDA_PATH, IFDDA_PATH
from .commands import parse_command_lines

REPO_ROOT = Path.cwd()


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


def _sanitize_case_id(case_id: Optional[str]) -> str:
    return str(case_id).replace("/", "_").replace(" ", "_")


def _symlink(src: Path, dst: Path) -> None:
    """
    Create a symlink dst -> src if dst doesn't already exist.
    """
    if dst.exists() or dst.is_symlink():
        return
    dst.symlink_to(src)


def _maybe_prepare_inputs(engine: str, cmd: str, run_dir: Path) -> None:
    """
    Create only the needed symlinks/files inside run_dir
    depending on engine+cmd.
    """
    repo = REPO_ROOT

    if engine == "ddscat":
        # DDSCAT needs diel/ in cwd because commands use -DIEL "diel/..."
        diel_dir = repo / "bin" / "diel"
        if diel_dir.exists():
            _symlink(diel_dir, run_dir / "diel")

        # If DDSCAT uses CSHAPE FROM_FILE, it likely needs a shape file in cwd
        # (you can refine this later if DDSCAT expects a different filename)
        if " -CSHAPE FROM_FILE " in f" {cmd} ":
            shape_dat = repo / "bin" / "shape.dat"
            if shape_dat.exists():
                _symlink(shape_dat, run_dir / "shape.dat")
        return

    if engine == "adda":
        # Only if ADDA reads a shape file
        if " -shape read " in f" {cmd} ":
            shape_dat = repo / "bin" / "shape.dat"
            if shape_dat.exists():
                _symlink(shape_dat, run_dir / "shape.dat")
        return

    if engine == "ifdda":
        # Only if IFDDA uses an arbitrary object file
        if " -object arbitrary " in f" {cmd} ":
            shape_ifdda = repo / "bin" / "shape_ifdda.dat"
            if shape_ifdda.exists():
                _symlink(shape_ifdda, run_dir / "shape_ifdda.dat")
        return


def run_command_with_stats(
    command: str,
    stdout_path: Path,
    stderr_path: Path,
    time_path: Optional[Path],
    with_stats: bool,
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[float], Optional[int]]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    if with_stats:
        if time_path is None:
            time_path = stdout_path.with_name("time.txt")

        # We want:
        # - program stdout -> stdout_path
        # - program stderr -> stderr_path
        # - /usr/bin/time -v output -> time_path
        #
        # /usr/bin/time writes to stderr, so we run it in a shell wrapper:
        #   (time -v <cmd> 2> time.txt) 2> stderr.txt
        wrapped = f"(/usr/bin/time -v {command} 2> {time_path.name}) 2> {stderr_path.name}"

        with stdout_path.open("w") as out:
            subprocess.run(
                wrapped,
                shell=True,
                stdout=out,
                stderr=subprocess.DEVNULL,  # already redirected in wrapped
                cwd=cwd,
                env=env,
            )

        cpu_time = None
        max_mem_kb = None
        if time_path.exists():
            with time_path.open("r") as f:
                for line in f:
                    if "User time (seconds):" in line:
                        cpu_time = float(line.split(":", 1)[1].strip())
                    elif "Maximum resident set size" in line:
                        max_mem_kb = int(line.split(":", 1)[1].strip())
        return cpu_time, max_mem_kb

    with stdout_path.open("w") as out, stderr_path.open("w") as err:
        subprocess.run(
            command, shell=True, stdout=out, stderr=err, cwd=cwd, env=env
        )

    return None, None


def run_case_command(
    cmd: str,
    engine: str,
    engine_cfg: Dict[str, Any],
    case_id: Optional[str],
    cmd_idx: int,
    output_dir: str,
    with_stats: bool,
) -> Tuple[Path, Path, Optional[float], Optional[int]]:
    """
    Execute one command in:
      outputs/<case_id>/<engine>/

    Files:
      stdout_XX.txt
      stderr_XX.txt
      time_XX.txt (if with_stats)
    """
    safe_case = _sanitize_case_id(case_id)
    run_dir = Path(output_dir) / safe_case / engine
    run_dir.mkdir(parents=True, exist_ok=True)

    # Prepare only the needed symlinks for this engine+cmd
    _maybe_prepare_inputs(engine, cmd, run_dir)

    stdout_path = run_dir / f"stdout_{cmd_idx:02d}.txt"
    stderr_path = run_dir / f"stderr_{cmd_idx:02d}.txt"
    time_path = run_dir / f"time_{cmd_idx:02d}.txt" if with_stats else None

    # Prevent DDSCAT from writing in bin/ by giving it a local ddscat.par
    env = None
    if engine == "ddscat":
        env = dict(os.environ)
        par_src = REPO_ROOT / "bin" / "ddscat.par"
        par_dst = run_dir / "ddscat.par"
        if par_src.exists():
            shutil.copyfile(par_src, par_dst)
            env["DDSCAT_PAR"] = str(par_dst.resolve())

        # If DDSCAT_EXE is set in env, keep it; otherwise rely on command
        # env["DDSCAT_EXE"] can be left as-is from your config.
        exe = REPO_ROOT / "bin" / "ddscat"
        if exe.exists():
            env["DDSCAT_EXE"] = str(exe.resolve())
    real_cmd = build_real_command(cmd, engine)
    cpu_time, mem = run_command_with_stats(
        real_cmd,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        time_path=time_path,
        with_stats=with_stats,
        cwd=run_dir,
        env=env,
    )

    return run_dir, stdout_path, cpu_time, mem
