from __future__ import annotations

from qsol.targeting.resolution import resolve_target_selection


def test_resolution_uses_instance_defaults_when_cli_missing() -> None:
    payload = {
        "execution": {
            "runtime": "local-dimod",
            "backend": "dimod-cqm-v1",
        }
    }
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime=None,
        cli_backend=None,
    )

    assert resolved.selection is not None
    assert resolved.selection.runtime_id == "local-dimod"
    assert resolved.selection.backend_id == "dimod-cqm-v1"
    assert not resolved.issues


def test_resolution_cli_overrides_instance_defaults() -> None:
    payload = {
        "execution": {
            "runtime": "runtime-from-instance",
            "backend": "backend-from-instance",
        }
    }
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime="runtime-from-cli",
        cli_backend="backend-from-cli",
    )

    assert resolved.selection is not None
    assert resolved.selection.runtime_id == "runtime-from-cli"
    assert resolved.selection.backend_id == "backend-from-cli"


def test_resolution_reports_missing_selection() -> None:
    resolved = resolve_target_selection(
        instance_payload={"problem": "P"},
        cli_runtime=None,
        cli_backend=None,
    )

    assert resolved.selection is None
    assert resolved.issues
    assert resolved.issues[0].code == "QSOL4006"


def test_resolution_handles_partial_instance_defaults() -> None:
    payload = {"execution": {"runtime": "local-dimod"}}
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime=None,
        cli_backend=None,
    )

    assert resolved.selection is None
    assert resolved.issues
    assert resolved.issues[0].code == "QSOL4006"
