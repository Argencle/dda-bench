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
dda-bench
```

By default it uses packaged example files:
- `DDA_commands`
- `dda_codes.json`

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
