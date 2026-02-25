# Configuration Guide

This document describes how to configure `dda-bench`:
- command input file: `DDA_commands`
- engine config file: `dda_codes.json`

## Quick Start

1. Create starter files in current directory:

```bash
dda-bench --init
```

This creates:
- `DDA_commands`
- `dda_codes.json`
- `bin/` with support files (`diel/*`, `*.dat`, `*.par`)

2. Edit `dda_codes.json` to point to your real executables and options.

3. Run:

```bash
dda-bench
```

If files are not in current directory, provide paths explicitly:

```bash
dda-bench --commands /path/to/DDA_commands --code-config /path/to/dda_codes.json
```

## 1. `DDA_commands` format

The file is split into cases. A case starts with:

```text
# @case: <case_id>
```

All non-empty, non-comment lines after that are commands for this case, until the next `# @case:`.

### 1.1 Required tags per case

You must define:
- residual tolerance: `# @tol_res: <min> <max>`
- and one of:
  - shared ext/abs tolerance: `# @tol: <min> <max>`
  - or separate tolerances:
    - `# @tol_ext: <min> <max>`
    - `# @tol_abs: <min> <max>`

You cannot mix `@tol` with `@tol_ext/@tol_abs`.

### 1.2 Optional tags

Optional per-case tags:
- `# @need_int`
- `# @need_force`
- `# @need_torque`
- `# @need_mueller`
- `# @tol_int: <min> <max>`
- `# @tol_force: <min> <max>`
- `# @tol_torque: <min> <max>`
- `# @tol_mueller: <min> <max>`

If `@need_*` is set, the matching `@tol_*` is required.

### 1.3 Skip pair comparisons

To skip a specific engine pair in one case, use exactly one pair per line:

```text
# @skip_pairs: adda ddscat
# @skip_pairs: ifdda ddscat
```

Rules:
- exactly 2 engine names per line
- names must match keys from `dda_codes.json`

### 1.4 Example case

```text
# @case: sphere_ldr_qmr
# @tol: 11 16
# @tol_res: 11 16
adda -lambda 0.5 -shape sphere -size 0.2 -iter qmr -m 1.3 0.07
ifdda -lambda 500 -object sphere 100 -methodeit QMRCLA -epsmulti 1.69 0.2
```

## 2. `dda_codes.json` format

Top-level structure:

```json
{
  "engine_name": {
    "detect_substrings": ["..."],
    "exe": "path/to/executable",
    "env": {"VAR": "value-or-path"},
    "prepare": [...],
    "outputs": {...},
    "int_field": {...},
    "mueller": {...},
    "aeff": {...},
    "lambda": {...},
    "extra_files": ["glob_or_path"],
    "cleanup": {...}
  }
}
```

### 2.1 Engine identification and command building

- `detect_substrings`: list of substrings used to detect engine from each command line.
- `exe`: executable path prepended to command args.
  - If relative, it is resolved from current working directory where `dda-bench` is launched.
- `env` (optional): env vars injected for this engine.
  - Relative values are also resolved from current working directory.

Example:

```json
"adda": {
  "detect_substrings": ["adda"],
  "exe": "bin/adda"
}
```

Command line:

```text
adda -lambda 0.5 -shape sphere ...
```

### 2.2 `prepare` actions

`prepare` is a list of steps executed in each run directory before command execution.

Supported actions:
- `symlink`
- `copy_file`
- `copy_env_file`

Example:

```json
"prepare": [
  {
    "action": "symlink",
    "src": "bin/shape.dat",
    "dst": "shape.dat",
    "when_contains": " -shape read "
  },
  {
    "action": "copy_env_file",
    "env_key": "DDSCAT_PAR",
    "dst": "ddscat.par",
    "set_env_to_dst": true
  }
]
```

`when_contains` can be a string or list of strings.

Field details:
- `src`: source path (absolute or relative to launch directory)
- `dst`: destination path relative to run directory (`outputs/<case>/<engine>/`)
- `when_contains`:
  - string: run this step only if substring is present in command line
  - list: run this step if any substring matches

`copy_env_file` details:
- `env_key`: environment variable containing a file path
- `dst`: destination filename in run directory
- `set_env_to_dst`:
  - `true`: update env var to copied local file
  - `false`: keep env var unchanged

### 2.3 Scalar outputs (`outputs`)

For scalar quantities (`Cext`, `Cabs`, `Qext`, `Qabs`, `residual1`, etc.):

```json
"outputs": {
  "Cext": {
    "type": "text",
    "pattern": "Cext\\s*=\\s*(?P<value>[0-9.eE+-]+)",
    "unit_factor": 1.0,
    "take_last": true
  },
  "Cpr": {
    "type": "text_vec3_norm",
    "pattern": "... (?P<x>...) ... (?P<y>...) ... (?P<z>...) ...",
    "unit_factor": 1e-12
  }
}
```

Supported scalar `type`:
- `text` (expects regex group `value`)
- `text_vec3_norm` (expects regex groups `x`, `y`, `z`)

Scalar behavior:
- `pattern` is required
- `unit_factor` defaults to `1.0`
- `take_last` defaults to `false`
- lookup order:
  1. stdout
  2. each path/pattern from `extra_files`

Regex requirements:
- `text`: must define `(?P<value>...)`
- `text_vec3_norm`: must define `(?P<x>...)`, `(?P<y>...)`, `(?P<z>...)`

### 2.4 Array outputs (`int_field`, `mueller`, etc.)

Array-like quantities are configured with types:
- `hdf5`
- `csv`
- `csv_columns`
- `text_table_columns`

Common source selection:
- `source: "stdout"`
- `source: "run_dir"` + `path`
- `source: "run_dir_glob"` + `pattern`

Optional:
- `select: "last_run"` (for glob matches)
- `transforms`: `filter_nonzero`, `divide_by_quantity`, `square`

Per-type required fields:
- `hdf5`: `dataset`
- `csv`: `sep`, `column`
- `csv_columns`: `sep`, `columns` (list)
- `text_table_columns`: `header_pattern`, `value_start_index`, `value_count`

### 2.5 `aeff` and `lambda`

Used to derive/align quantities (`C*`/`Q*`, force/torque comparisons).

`aeff` supports:
- direct pattern extraction
- or reconstruction from dipole count + mesh size patterns

`lambda` supports standard scalar extraction fields (`pattern`, `unit_factor`, etc.).

### 2.6 `extra_files`

Additional files to scan when a scalar pattern is not found in stdout.

```json
"extra_files": ["w000r000.avg", "ddscat.log_000", "run*/*.log"]
```

Details:
- relative patterns are evaluated in each run directory
- absolute paths are accepted
- first successful regex match is used

### 2.7 `cleanup`

Used only when `--clean` is enabled.

```json
"cleanup": {
  "remove_names": ["shape.dat", "ddscat.par"],
  "remove_globs": ["run*"]
}
```