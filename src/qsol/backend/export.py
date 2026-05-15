from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import dimod

from qsol.backend.dimod_codegen import CodegenResult
from qsol.lower.ir import BackendArtifacts

LOGGER = logging.getLogger(__name__)


def export_artifacts(
    outdir: str | Path, output_format: str, codegen_result: CodegenResult
) -> BackendArtifacts:
    out = Path(outdir)
    LOGGER.debug("Ensuring output directory exists: %s", out)
    out.mkdir(parents=True, exist_ok=True)

    cqm_path = out / "model.cqm"
    bqm_path = out / "model.bqm"
    LOGGER.debug("Writing CQM artifact to %s", cqm_path)
    with cqm_path.open("wb") as fp:
        cqm_file = codegen_result.cqm.to_file()
        cqm_file.seek(0)
        fp.write(cqm_file.read())
    LOGGER.debug("Writing BQM artifact to %s", bqm_path)
    with bqm_path.open("wb") as fp:
        bqm_file = codegen_result.bqm.to_file()
        bqm_file.seek(0)
        fp.write(bqm_file.read())

    varmap_path = out / "varmap.json"
    LOGGER.debug("Writing variable map artifact to %s", varmap_path)
    varmap_path.write_text(
        json.dumps(codegen_result.varmap, indent=2, sort_keys=True), encoding="utf-8"
    )

    format_path = out / ("qubo.json" if output_format == "qubo" else "ising.json")
    payload = (
        _to_qubo_json(codegen_result.bqm)
        if output_format == "qubo"
        else _to_ising_json(codegen_result.bqm)
    )
    LOGGER.debug("Writing model payload (%s) to %s", output_format, format_path)
    format_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    explain_path = out / "explain.json"
    LOGGER.debug("Writing diagnostics explanation to %s", explain_path)
    explain_path.write_text(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "code": d.code,
                        "message": d.message,
                        "line": d.span.line,
                        "col": d.span.col,
                    }
                    for d in codegen_result.diagnostics
                ]
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    stats = dimod_model_stats(cqm=codegen_result.cqm, bqm=codegen_result.bqm)

    LOGGER.info("Artifacts exported to %s", out)
    return BackendArtifacts(
        cqm_path=str(cqm_path),
        bqm_path=str(bqm_path),
        format_path=str(format_path),
        varmap_path=str(varmap_path),
        explain_path=str(explain_path),
        stats=stats,
    )


def dimod_model_stats(
    *,
    cqm: dimod.ConstrainedQuadraticModel,
    bqm: dimod.BinaryQuadraticModel,
) -> dict[str, float | int]:
    cqm_binary = 0
    cqm_integer = 0
    for variable in cqm.variables:
        vartype = cqm.vartype(variable)
        if vartype == dimod.BINARY:
            cqm_binary += 1
        elif vartype == dimod.INTEGER:
            cqm_integer += 1

    converted_bqm_variables = int(len(bqm.variables))
    converted_bqm_interactions = int(len(bqm.quadratic))
    return {
        "cqm_binary_variables": cqm_binary,
        "cqm_integer_variables": cqm_integer,
        "converted_bqm_variables": converted_bqm_variables,
        "converted_bqm_interactions": converted_bqm_interactions,
        "num_variables": converted_bqm_variables,
        "num_interactions": converted_bqm_interactions,
        "num_constraints": int(len(cqm.constraints)),
    }


def _to_qubo_json(bqm: Any) -> dict[str, object]:
    qubo, offset = bqm.to_qubo()
    entries = [
        {"u": str(u), "v": str(v), "bias": bias}
        for (u, v), bias in sorted(qubo.items(), key=lambda x: (str(x[0][0]), str(x[0][1])))
    ]
    return {"offset": float(offset), "terms": entries}


def _to_ising_json(bqm: Any) -> dict[str, object]:
    h, j, offset = bqm.to_ising()
    h_entries = [{"v": str(k), "bias": v} for k, v in sorted(h.items(), key=lambda x: str(x[0]))]
    j_entries = [
        {"u": str(u), "v": str(v), "bias": bias}
        for (u, v), bias in sorted(j.items(), key=lambda x: (str(x[0][0]), str(x[0][1])))
    ]
    return {"offset": float(offset), "h": h_entries, "j": j_entries}
