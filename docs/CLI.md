# QSOL CLI Reference

The `qsol` command-line interface provides tools for inspecting, compiling, and running QSOL models.

## Global Options

These options apply to most commands:

- `--no-color, -n`: Disable ANSI color output.
- `--log-level, -l [debug|info|warning|error]`: Set CLI log verbosity (default: `warning`).
- `--help, -h`: Show help message and exit.

## Core Commands

### `qsol build`

Compiles a model and scenario, generating backend artifacts (e.g., CQM/BQM files).

**Usage:**
```bash
qsol build [OPTIONS] FILE
```

**Key Options:**
- `--config, -c PATH`: Path to the TOML configuration file (defaults to `model.qsol.toml`).
- `--out, -o PATH`: Output directory for artifacts (required).
- `--runtime, -u ID`: Target runtime ID (e.g., `local-dimod`).
- `--backend, -b ID`: Target backend ID (e.g., `dimod-cqm-v1`).
- `--plugin, -p MODULE:ATTR`: Load extra plugins.

### `qsol solve`

Compiles, runs, and exports solve results for a model and scenario.

**Usage:**
```bash
qsol solve [OPTIONS] FILE
```

**Key Options:**
- `--config, -c PATH`: Path to configuration file.
- `--out, -o PATH`: Output directory (defaults to `outdir/<model_name>`).
- `--runtime, -u ID`: Runtime ID (default: `local-dimod` if configured).
- `--backend, -b ID`: Backend ID (default: `dimod-cqm-v1` if configured).
- `--solutions N`: Number of best unique solutions to return.
- `--energy-min FLOAT`: Filter solutions with energy less than this value.
- `--energy-max FLOAT`: Filter solutions with energy greater than this value.
- `--runtime-option, -x KEY=VALUE`: Pass runtime-specific options (e.g., `-x num_reads=100`).

## Inspection Commands

Tools for debugging and understanding how QSOL parses and processes your model.

### `qsol inspect parse`

Parses a QSOL model and prints the Abstract Syntax Tree (AST).

**Usage:**
```bash
qsol inspect parse [OPTIONS] FILE
```
- `--json, -j`: Print output as JSON.

### `qsol inspect check`

Runs frontend checks (parse, resolve, typecheck, validate) without generating backend code.

**Usage:**
```bash
qsol inspect check [OPTIONS] FILE
```

### `qsol inspect lower`

Lowers a QSOL model to symbolic kernel IR. This shows the intermediate representation before instantiation with data.

**Usage:**
```bash
qsol inspect lower [OPTIONS] FILE
```
- `--json, -j`: Print output as JSON.

## Target Commands

Tools for exploring available runtimes and backends.

### `qsol targets list`

Lists all discovered runtime and backend plugins.

**Usage:**
```bash
qsol targets list
```

### `qsol targets capabilities`

Shows detailed capabilities for a specific runtime and backend, and checks their compatibility.

**Usage:**
```bash
qsol targets capabilities --runtime ID [OPTIONS]
```

### `qsol targets check`

Checks if a specific model and scenario are supported by a selected target pair.

**Usage:**
```bash
qsol targets check [OPTIONS] FILE
```
