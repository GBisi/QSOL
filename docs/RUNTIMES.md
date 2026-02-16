# QSOL Runtimes

QSOL runtimes execute compiled models. The runtime manages the solver process, collects results, and formats them for the user.

## 1. Available Runtimes

### `local-dimod` (Default)

Executes models locally using D-Wave's `dimod` reference samplers. This is useful for testing, debugging, and solving small instances.

*   **Plugin ID**: `local-dimod`
*   **Compatible Backends**: `dimod-cqm-v1`
*   **Solvers**:
    *   `simulated-annealing`: Heuristic solver (default). Good for larger problems but no optimality guarantee.
    *   `exact`: Enumerates all possible states. Only feasible for very small problems (< 20 variables).

#### Runtime Options

Pass these via `--runtime-option KEY=VALUE` or `-x KEY=VALUE`.

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sampler` | `string` | `simulated-annealing` | The underlying solver to use (`simulated-annealing` or `exact`). |
| `num_reads` | `int` | `10` | Number of samples to collect (only for `simulated-annealing`). |
| `seed` | `int` | `None` | Random seed for reproducibility. |

### `qiskit`

Executes models via IBM's Qiskit ecosystem. Supports QAOA on simulated fake backends and a classical NumPy eigensolver. Useful for quantum algorithm experimentation and benchmarking.

*   **Plugin ID**: `qiskit`
*   **Compatible Backends**: `dimod-cqm-v1`
*   **Algorithms**:
    *   `qaoa`: Quantum Approximate Optimization Algorithm on a fake IBM backend. Produces an OpenQASM 3 circuit export (`qaoa.qasm`).
    *   `numpy`: Classical `NumPyMinimumEigensolver` for exact ground-state computation (small problems only).

#### Installation

Qiskit dependencies are optional. Install them with:

```bash
uv sync --extra qiskit
```

#### Runtime Options

Pass these via `--runtime-option KEY=VALUE` or `-x KEY=VALUE`.

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `algorithm` | `string` | `qaoa` | Algorithm to use (`qaoa` or `numpy`). |
| `fake_backend` | `string` | `FakeManilaV2` | Qiskit fake backend for QAOA simulation. |
| `reps` | `int` | `1` | Number of QAOA repetitions (circuit depth). |
| `maxiter` | `int` | `100` | Maximum classical optimizer iterations. |
| `shots` | `int` | `1024` | Number of measurement shots. |
| `seed` | `int` | `None` | Random seed for reproducibility. |
| `optimization_level` | `int` | `1` | Qiskit transpiler optimization level (0–3). |

#### Example

```bash
uv run qsol solve model.qsol \
  --runtime qiskit \
  --out outdir/model_qiskit \
  -x algorithm=qaoa \
  -x fake_backend=FakeManilaV2 \
  -x shots=1024 \
  -x reps=2
```

## 2. Checking Compatibility

You can check which runtimes are compatible with which backends using the CLI:

```bash
qsol targets list
```

To see detailed capabilities of a runtime:

```bash
qsol targets capabilities --runtime local-dimod
```

To check if a specific model and scenario are compatible with a runtime/backend pair:

```bash
qsol targets check model.qsol --runtime local-dimod --backend dimod-cqm-v1
```
