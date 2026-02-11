from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class CommandCase:
    """
    A test case identified by an explicit '# @case: <id>'
    tag in the commands file.

    meta contains parsed tags like:
      - tol_min/tol_max
      - tol_ext_min/tol_ext_max
      - tol_abs_min/tol_abs_max
      - tol_res_min/tol_res_max   (required)
      - tol_int_min/tol_int_max   (optional)
      - tol_force_min/tol_force_max (optional)
      - skip_pairs: list[tuple[str,str]] (optional)
    """

    case_id: str | None
    commands: list[tuple[str, int]]
    meta: dict[str, Any]


def _parse_pair_tag(
    stripped: str, tag: str, lineno: int, command_file: str
) -> tuple[str, str]:
    """
    Parse a tag line like:
      # @tol: 4 7
    returning ("4","7").
    """
    rhs = stripped.split(tag, 1)[1].strip()
    parts = rhs.split()
    if len(parts) != 2:
        raise ValueError(
            f"Invalid {tag} format at line {lineno} in {command_file}"
        )
    return parts[0], parts[1]


def read_command_cases(command_file: str) -> list[CommandCase]:
    """
    Read the file and return a list of cases.

    Syntax:
      - '# @case: <id>' starts a new case
      - non-empty, non-# lines are commands belonging to the current case
      - other comments '# ...' are ignored
      - blank lines are ignored

    Required tags per case:
      - Either:
          A) # @tol: <min> <max>
        OR
          B) # @tol_ext: <min> <max>  AND  # @tol_abs: <min> <max>
      - And ALWAYS:
          # @tol_res: <min> <max>

    Optional:
      - # @tol_int: <min> <max>
      - # @tol_force: <min> <max>
      - # @skip_pairs: <engine1> <engine2> <engine3> <engine4> ...
    """
    cases: list[CommandCase] = []

    current_id: str | None = None
    current_cmds: list[tuple[str, int]] = []
    current_meta: dict[str, Any] = {}

    seen_ids: set[str] = set()

    def _validate_current_case() -> None:
        """
        Enforce meta rules on the current case before saving.
        """
        nonlocal current_id, current_meta

        if current_id is None:
            return

        meta = current_meta

        has_tol = ("tol_min" in meta) or ("tol_max" in meta)
        has_ext = ("tol_ext_min" in meta) or ("tol_ext_max" in meta)
        has_abs = ("tol_abs_min" in meta) or ("tol_abs_max" in meta)

        # --- @tol_res is always required ---
        if "tol_res_min" not in meta or "tol_res_max" not in meta:
            raise ValueError(
                f"Case '{current_id}' in {command_file} must define @tol_res: <min> <max>."
            )

        # --- Either @tol OR (@tol_ext + @tol_abs) ---
        if has_tol:
            # If @tol is used, require both min/max
            if "tol_min" not in meta or "tol_max" not in meta:
                raise ValueError(
                    f"Case '{current_id}' in {command_file} has incomplete @tol (need 2 ints)."
                )
            # forbid mixing
            if has_ext or has_abs:
                raise ValueError(
                    f"Case '{current_id}' in {command_file} mixes @tol with @tol_ext/@tol_abs. "
                    "Use either @tol OR (@tol_ext + @tol_abs)."
                )
        else:
            # no @tol => require ext+abs fully
            if "tol_ext_min" not in meta or "tol_ext_max" not in meta:
                raise ValueError(
                    f"Case '{current_id}' in {command_file} must define @tol_ext: <min> <max> when @tol is absent."
                )
            if "tol_abs_min" not in meta or "tol_abs_max" not in meta:
                raise ValueError(
                    f"Case '{current_id}' in {command_file} must define @tol_abs: <min> <max> when @tol is absent."
                )

        # --- skip_pairs must be a list of 2-tuples if present ---
        if "skip_pairs" in meta:
            sp = meta["skip_pairs"]
            if not isinstance(sp, list):
                raise ValueError(
                    f"Case '{current_id}' in {command_file}: skip_pairs must be a list"
                )
            for p in sp:
                if (
                    not isinstance(p, tuple)
                    or len(p) != 2
                    or not all(isinstance(x, str) and x.strip() for x in p)
                ):
                    raise ValueError(
                        f"Case '{current_id}' in {command_file}: invalid skip_pairs entry"
                    )

        need_int = meta.get("need_int") == "1"
        need_force = meta.get("need_force") == "1"

        if need_int:
            if "tol_int_min" not in meta or "tol_int_max" not in meta:
                raise ValueError(
                    f"Case '{current_id}' in {command_file} has @need_int but is missing @tol_int: <min> <max>."
                )

        if need_force:
            if "tol_force_min" not in meta or "tol_force_max" not in meta:
                raise ValueError(
                    f"Case '{current_id}' in {command_file} has @need_force but is missing @tol_force: <min> <max>."
                )

    def flush_current() -> None:
        nonlocal current_id, current_cmds, current_meta

        # do nothing if no active case
        if current_id is None:
            current_cmds = []
            current_meta = {}
            return

        # skip empty cases
        if not current_cmds:
            current_id = None
            current_meta = {}
            return

        if current_id in seen_ids:
            raise ValueError(
                f"Duplicate case id '{current_id}' in {command_file}"
            )

        # validate meta rules
        _validate_current_case()

        cases.append(
            CommandCase(
                case_id=current_id,
                commands=current_cmds,
                meta=current_meta,
            )
        )
        seen_ids.add(current_id)

        current_id = None
        current_cmds = []
        current_meta = {}

    with open(command_file, "r") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()

            if not stripped:
                continue

            # --------------------
            # case tag
            # --------------------
            if stripped.startswith("#") and "@case:" in stripped:
                flush_current()
                parts = stripped.split("@case:", 1)
                current_id = parts[1].strip()

                if not current_id:
                    raise ValueError(
                        f"Empty @case id at line {lineno} in {command_file}"
                    )
                continue

            # Tags must belong to an active case
            if stripped.startswith("#") and stripped.lstrip().startswith(
                "# @"
            ):
                if current_id is None:
                    raise ValueError(
                        f"Tag before any @case at line {lineno} in {command_file}: {stripped}"
                    )

                # --------------------
                # tolerances
                # --------------------
                if "@tol:" in stripped:
                    a, b = _parse_pair_tag(
                        stripped, "@tol:", lineno, command_file
                    )
                    current_meta["tol_min"] = a
                    current_meta["tol_max"] = b
                    continue

                if "@tol_ext:" in stripped:
                    a, b = _parse_pair_tag(
                        stripped, "@tol_ext:", lineno, command_file
                    )
                    current_meta["tol_ext_min"] = a
                    current_meta["tol_ext_max"] = b
                    continue

                if "@tol_abs:" in stripped:
                    a, b = _parse_pair_tag(
                        stripped, "@tol_abs:", lineno, command_file
                    )
                    current_meta["tol_abs_min"] = a
                    current_meta["tol_abs_max"] = b
                    continue

                if "@tol_res:" in stripped:
                    a, b = _parse_pair_tag(
                        stripped, "@tol_res:", lineno, command_file
                    )
                    current_meta["tol_res_min"] = a
                    current_meta["tol_res_max"] = b
                    continue

                # optional
                if "@tol_int:" in stripped:
                    a, b = _parse_pair_tag(
                        stripped, "@tol_int:", lineno, command_file
                    )
                    current_meta["tol_int_min"] = a
                    current_meta["tol_int_max"] = b
                    continue

                # optional
                if "@tol_force:" in stripped:
                    a, b = _parse_pair_tag(
                        stripped, "@tol_force:", lineno, command_file
                    )
                    current_meta["tol_force_min"] = a
                    current_meta["tol_force_max"] = b
                    continue

                # multi-line strict: exactly 2 engines per line
                if "@skip_pairs:" in stripped:
                    rhs = stripped.split("@skip_pairs:", 1)[1].strip()
                    toks = rhs.split()
                    if len(toks) != 2:
                        raise ValueError(
                            f"Invalid @skip_pairs format at line {lineno} in {command_file}: "
                            "must be exactly 2 engine names per line."
                        )
                    current_meta.setdefault("skip_pairs", []).append(
                        (toks[0], toks[1])
                    )
                    continue

                # optional bool tags
                if stripped.startswith("#") and "@need_int" in stripped:
                    current_meta["need_int"] = "1"
                    continue

                if stripped.startswith("#") and "@need_force" in stripped:
                    current_meta["need_force"] = "1"
                    continue

                # unknown tag:
                raise ValueError(
                    f"Unknown tag at line {lineno} in {command_file}: {stripped}"
                )

            # ignore other comments
            if stripped.startswith("#"):
                continue

            # command line must belong to an active case
            if current_id is None:
                raise ValueError(
                    f"Missing '# @case:' before command at line {lineno}: {stripped}"
                )

            current_cmds.append((stripped, lineno))

    # flush last active case
    flush_current()
    return cases


def parse_command_lines(line: str, prefixe: str) -> str:
    """
    Backwards-compatible helper:
    If the line starts with '<prefixe>', remove the prefix and return the rest.
    Otherwise, return the line unchanged.
    """
    return (
        line.split(maxsplit=1)[1] if line.startswith(f"{prefixe} ") else line
    )
