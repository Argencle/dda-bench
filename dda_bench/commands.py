from typing import List, Tuple


def read_command_pairs(command_file: str) -> List[Tuple[Tuple[str, str], int]]:
    """
    Read command-lines from an input file and return them with the line number
    of the first command in each pair.
    """
    lines = []
    line_indices = []
    with open(command_file, "r") as f:
        for idx, line in enumerate(f, start=1):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
                line_indices.append(idx)

    if len(lines) % 2 != 0:
        raise ValueError("Command file must have an even number of lines.")

    return [
        ((lines[i], lines[i + 1]), line_indices[i])
        for i in range(0, len(lines), 2)
    ]


def parse_command_lines(line: str, prefixe: str) -> str:
    """
    If the line starts with 'adda' or 'ifdda', remove the prefix and return
    the rest. Otherwise, return the line unchanged.
    """
    return line.split(maxsplit=1)[1] if line.startswith(f"{prefixe}") else line
