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

    seen_ids: set[Optional[str]] = set()

    def flush_current() -> None:
        nonlocal current_id, current_cmds, current_meta
        cases.append(
            CommandCase(
                case_id=current_id, commands=current_cmds, meta=current_meta
            )
        )
        seen_ids.add(current_id)
        current_id = None
        current_cmds = []
        current_meta = {}

    with open(command_file, "r") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()

            # ignore blank lines
            if not stripped:
                continue

            # case tag
            if stripped.startswith("#") and "@case:" in stripped:
                # flush previous case
                flush_current()
                # parse id
                # accept forms:
                #   # @case: foo
                #   #@case:foo
                parts = stripped.split("@case:", 1)
                case_id = parts[1].strip()
                current_id = case_id
                continue

            # ignore other comments
            if stripped.startswith("#"):
                continue
            current_cmds.append((stripped, lineno))

    # flush last
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
