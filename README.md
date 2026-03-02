# dda-bench

[![DOI](https://zenodo.org/badge/1087276820.svg)](https://doi.org/10.5281/zenodo.18801224)
[![PyPI](https://img.shields.io/pypi/v/dda-bench.svg)](https://pypi.org/project/dda-bench/)

Benchmark tool for cross comparison of DDA codes.

## Install (Users)

```bash
pip install dda-bench
```

## Install (Development)

```bash
git clone https://github.com/Argencle/dda-bench.git
cd dda-bench
pip install -e .
```

## Important

This package does not ship external DDA solvers.
You must provide executables and point your config to valid paths.

Full configuration reference:
- [`docs/configuration.md`](docs/configuration.md)

## Paper Context

This repository is linked to, and was developed as part of, a benchmark paper.

The dataset used for that paper is available in:
- [`https://github.com/Argencle/data-dda-benchmark-paper.git`](https://github.com/Argencle/data-dda-benchmark-paper.git)

To reproduce the equivalent parameter agreement between codes reported in Appendix C of the paper, [patches](https://github.com/Argencle/data-dda-benchmark-paper/tree/main/patches) from that data repository must be applied to ADDA and DDSCAT before running `dda-bench`.

The corresponding benchmark command set is provided in:
- [`dda_bench/examples/DDA_commands`](dda_bench/examples/DDA_commands)

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
