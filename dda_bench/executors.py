import os
import subprocess
import shutil
from pathlib import Path
from typing import Any
from .commands import parse_command_lines

REPO_ROOT = Path.cwd()


def _resolve_env(engine_cfg: dict[str, Any]) -> dict[str, str] | None:
    """
    Build an env dict based on engine_cfg["env"].
    Values can be:
      - absolute paths
      - repo-relative paths (resolved against REPO_ROOT)
    Returns a full env dict (copy of os.environ) if "env" exists, else None.
    """
    env_cfg = engine_cfg.get("env")
    if not env_cfg:
        return None

    env = dict(os.environ)

    for k, v in env_cfg.items():
        p = Path(v)
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        env[k] = str(p)

    return env


def _build_real_command(
    cmd: str, engine: str, engine_cfg: dict[str, Any]
) -> str:
    """
    Turn the 'logical' command from the tests file into the real one
    using the executable paths from dda_codes.json.
    """
    prefix = engine_cfg.get("prefix", engine)
    exe = engine_cfg.get("exe")
    args = parse_command_lines(cmd, prefix)
    if not exe:
        if cmd.startswith(prefix):
            # If no exe is given, assume the command itself is correct
            return args.strip()
        return cmd
    exe_path = Path(exe)
    if not exe_path.is_absolute():
        exe_path = (REPO_ROOT / exe_path).resolve()

    return f"{exe_path} {args}".strip()


def _sanitize_case_id(case_id: str | None) -> str:
    return str(case_id).replace("/", "_").replace(" ", "_")


def _symlink(src: Path, dst: Path) -> None:
    """
    Create a symlink dst -> src if dst doesn't already exist.
    """
    if dst.exists() or dst.is_symlink():
        return
    dst.symlink_to(src)


def _should_run_step(step: dict[str, Any], cmd: str) -> bool:
    """
    Optional condition for a step:
      - "when_contains": string or list[str]
    """
    cond = step.get("when_contains")
    if not cond:
        return True

    hay = f" {cmd} "
    if isinstance(cond, str):
        return cond in hay
    if isinstance(cond, list):
        return any(c in hay for c in cond)
    return True


def _apply_prepare_steps(
    engine_cfg: dict[str, Any], run_dir: Path, env: dict[str, str], cmd: str
) -> None:
    """
    Execute prepare steps declared in dda_codes.json.

    Supported actions:
      1) symlink
      2) copy_env_file
      3) copy_file
    """
    steps = engine_cfg.get("prepare", [])
    for step in steps:
        if not _should_run_step(step, cmd):
            continue

        action = step.get("action")
        if action == "symlink":
            src = Path(step["src"])
            dst = Path(step["dst"])
            if not src.is_absolute():
                src = (REPO_ROOT / src).resolve()
            dst = run_dir / dst
            if src.exists():
                _symlink(src, dst)

        elif action == "copy_env_file":
            env_key = step["env_key"]
            dst_rel = step["dst"]
            set_env = bool(step.get("set_env_to_dst", False))

            src_val = env.get(env_key)
            if not src_val:
                raise ValueError(f"{env_key} not set in env for engine")

            src_path = Path(src_val)
            if not src_path.is_absolute():
                src_path = (REPO_ROOT / src_path).resolve()

            dst_path = run_dir / dst_rel
            if not src_path.exists():
                raise FileNotFoundError(
                    f"{env_key} points to missing file: {src_path}"
                )

            shutil.copyfile(src_path, dst_path)

            if set_env:
                env[env_key] = str(dst_path.resolve())

        elif action == "copy_file":
            src = Path(step["src"])
            dst = Path(step["dst"])
            if not src.is_absolute():
                src = (REPO_ROOT / src).resolve()
            dst = run_dir / dst
            if src.exists():
                shutil.copyfile(src, dst)

        else:
            raise ValueError(f"Unknown prepare action: {action}")


def _run_command_with_stats(
    command: str,
    stdout_path: Path,
    stderr_path: Path,
    time_path: Path | None,
    with_stats: bool,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> tuple[float | None, int | None]:
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
    engine_cfg: dict[str, Any],
    case_id: str | None,
    cmd_idx: int,
    output_dir: str,
    with_stats: bool,
) -> tuple[Path, Path, float | None, int | None]:
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

    stdout_path = run_dir / f"stdout_{cmd_idx:02d}.txt"
    stderr_path = run_dir / f"stderr_{cmd_idx:02d}.txt"
    time_path = run_dir / f"time_{cmd_idx:02d}.txt" if with_stats else None

    env = _resolve_env(engine_cfg)
    if env is None:
        env = dict(os.environ)

    _apply_prepare_steps(engine_cfg, run_dir, env, cmd)

    real_cmd = _build_real_command(cmd, engine, engine_cfg)
    cpu_time, mem = _run_command_with_stats(
        real_cmd,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        time_path=time_path,
        with_stats=with_stats,
        cwd=run_dir,
        env=env,
    )

    return run_dir, stdout_path, cpu_time, mem
