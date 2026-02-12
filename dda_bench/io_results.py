import csv
import json
from pathlib import Path
from typing import Any


def write_case_results(
    case_id: str | None,
    per_engine_values: dict[str, dict[str, float]],
    output_dir: str,
) -> None:
    if not case_id:
        case_id = "unknown_case"

    case_dir = Path(output_dir) / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    out = case_dir / "results.json"
    data: dict[str, Any] = {"case": case_id, "engines": {}}

    for eng, vals in per_engine_values.items():
        data["engines"][eng] = dict(vals)

    out.write_text(json.dumps(data, indent=2))


def write_summary_csv(output_dir: str, csv_path: str) -> None:
    out = Path(output_dir)
    rows: list[dict[str, Any]] = []

    for result_file in out.glob("*/results.json"):
        data = json.loads(result_file.read_text())
        case_id = data.get("case", "unknown_case")

        for eng, vals in data.get("engines", {}).items():
            row = {"case": case_id, "engine": eng, **vals}
            rows.append(row)

    if not rows:
        return

    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
