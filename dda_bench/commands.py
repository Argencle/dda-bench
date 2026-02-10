from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class CommandCase:
    """
    A test case identified by an explicit '# @case: <id>'
    tag in the commands file.
    """

    case_id: Optional[str]
    commands: List[Tuple[str, int]]
    meta: Dict[str, str]


def read_command_cases(command_file: str) -> List[CommandCase]:
    """
    Read the file and return a list of cases.

    Syntax:
      - '# @case: <id>' starts a new case
      - non-empty, non-# lines are commands belonging to the current case
      - other comments '# ...' are ignored
      - blank lines are ignored
    """
    cases: List[CommandCase] = []

    current_id: Optional[str] = None
    current_cmds: List[Tuple[str, int]] = []
    current_meta: Dict[str, str] = {}

    seen_ids: set[str] = set()

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

            # case tag
            if stripped.startswith("#") and "@case:" in stripped:
                flush_current()
                parts = stripped.split("@case:", 1)
                current_id = parts[1].strip()

                if not current_id:
                    raise ValueError(
                        f"Empty @case id at line {lineno} in {command_file}"
                    )

                continue

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
