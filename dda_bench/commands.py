from typing import List, Tuple


def read_command_groups(
    command_file: str,
) -> List[List[Tuple[str, int]]]:
    """
    Read the file and return a list of groups.
    A group = consecutive non-empty, non-# lines.
    A blank line or '# ...' starts a new group.
    """
    groups: List[List[Tuple[str, int]]] = []
    current: List[Tuple[str, int]] = []

    with open(command_file, "r") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                if current:
                    groups.append(current)
                    current = []
                continue
            current.append((stripped, lineno))

    if current:
        groups.append(current)

    return groups


def parse_command_lines(line: str, prefixe: str) -> str:
    """
    If the line starts with 'adda' or 'ifdda', remove the prefix and return
    the rest. Otherwise, return the line unchanged.
    """
    return line.split(maxsplit=1)[1] if line.startswith(f"{prefixe}") else line
