from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.lower.ir import GroundIR, GroundProblem, KernelIR, KProblem

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class InstanceResult:
    ground_ir: GroundIR | None
    diagnostics: list[Diagnostic]


def load_instance(path: str | Path) -> dict[str, object]:
    LOGGER.debug("Loading instance payload from %s", path)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"instance payload must be a JSON object: {path}"
        raise ValueError(msg)
    return cast(dict[str, object], payload)


def instantiate_ir(kernel: KernelIR, instance: Mapping[str, object]) -> InstanceResult:
    LOGGER.debug("Instantiating IR from instance payload")
    diagnostics: list[Diagnostic] = []
    requested_problem = instance.get("problem")

    problems: list[KProblem] = list(kernel.problems)
    if requested_problem is not None:
        problems = [p for p in problems if p.name == requested_problem]

    if not problems:
        LOGGER.error("Instance problem '%s' did not match any compiled problem", requested_problem)
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL3001",
                message="instance problem does not match any compiled problem",
                span=kernel.span,
            )
        )
        return InstanceResult(ground_ir=None, diagnostics=diagnostics)

    set_values_raw = instance.get("sets")
    set_values = cast(dict[str, object], set_values_raw) if isinstance(set_values_raw, dict) else {}
    params_raw = instance.get("params")
    params_payload = cast(dict[str, object], params_raw) if isinstance(params_raw, dict) else {}
    out: list[GroundProblem] = []

    for problem in problems:
        p_sets: dict[str, list[str]] = {}
        p_params: dict[str, object] = {}

        for decl in problem.sets:
            vals = set_values.get(decl.name)
            if vals is None:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"missing set values for `{decl.name}`",
                        span=decl.span,
                    )
                )
                continue
            if not isinstance(vals, list):
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"set `{decl.name}` must be a JSON array",
                        span=decl.span,
                    )
                )
                continue
            p_sets[decl.name] = [str(v) for v in vals]

        for pdecl in problem.params:
            provided = pdecl.name in params_payload
            if provided:
                value = params_payload[pdecl.name]
            elif pdecl.default is not None:
                value = pdecl.default
            else:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2201",
                        message=f"missing value for param `{pdecl.name}`",
                        span=pdecl.span,
                    )
                )
                continue

            if pdecl.indices:
                if not isinstance(value, dict):
                    if not provided and pdecl.default is not None:
                        value = _expand_indexed_default(pdecl.default, list(pdecl.indices), p_sets)
                    else:
                        diagnostics.append(
                            Diagnostic(
                                severity=Severity.ERROR,
                                code="QSOL2201",
                                message=f"param `{pdecl.name}` expects indexed object",
                                span=pdecl.span,
                            )
                        )
                        continue
                shape_ok = _check_shape(value, list(pdecl.indices), p_sets)
                if not shape_ok:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2201",
                            message=f"param `{pdecl.name}` shape does not match index sets",
                            span=pdecl.span,
                        )
                    )
                    continue

            p_params[pdecl.name] = value

        out.append(
            GroundProblem(
                span=problem.span,
                name=problem.name,
                set_values=p_sets,
                params=p_params,
                finds=problem.finds,
                constraints=problem.constraints,
                objectives=problem.objectives,
            )
        )

    if any(d.is_error for d in diagnostics):
        LOGGER.error("Instance instantiation failed with %s diagnostics", len(diagnostics))
        return InstanceResult(ground_ir=None, diagnostics=diagnostics)
    LOGGER.info("Instance instantiation completed for %s problem(s)", len(out))
    return InstanceResult(
        ground_ir=GroundIR(span=kernel.span, problems=tuple(out)), diagnostics=diagnostics
    )


def _check_shape(value: object, dims: list[str], sets: dict[str, list[str]]) -> bool:
    if not dims:
        return not isinstance(value, dict)
    if not isinstance(value, dict):
        return False

    dim = dims[0]
    expected = sorted(sets.get(dim, []))
    keys = sorted(str(k) for k in value.keys())
    if expected and keys != expected:
        return False
    return all(_check_shape(v, dims[1:], sets) for v in value.values())


def _expand_indexed_default(
    default_value: object, dims: list[str], sets: dict[str, list[str]]
) -> object:
    if not dims:
        return default_value

    dim = dims[0]
    elems = sorted(sets.get(dim, []))
    return {elem: _expand_indexed_default(default_value, dims[1:], sets) for elem in elems}
