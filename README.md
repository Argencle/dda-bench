## dda-bench

Benchmark tool for cross comparison of DDA codes.

## Install

```bash
pip install dda-bench
```

## Important

This package does not ship external DDA solvers.
You must provide executables and point your config to valid paths.

### Run benchmark/comparison

```bash
dda-bench --init
```

This creates starter files in current directory:
- `DDA_commands`
- `dda_codes.json`
- `bin/`

The starter `dda_codes.json` points to executables under `bin/`.
`--init` copies only `bin/diel/*` and `bin/*.dat`/`bin/*.par` support files, not solver executables.

Then run:

```bash
dda-bench
```

`dda-bench` without options expects:
- `./DDA_commands`
- `./dda_codes.json`

Override with your own files:

```bash
dda-bench --commands /path/to/DDA_commands --code-config /path/to/dda_codes.json
```

Other options:

```bash
dda-bench --output outputs --omp 1 --clean
```

## Output

The command writes:
- `dda_bench.log`
- `dda_bench.errors.log`
- per-case `results.json` under output directory
- `summary.csv` in output directory
