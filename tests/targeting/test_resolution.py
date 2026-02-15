from __future__ import annotations

from qsol.targeting.resolution import DEFAULT_BACKEND_ID, resolve_target_selection


def test_resolution_uses_instance_defaults_when_cli_missing() -> None:
    payload = {
        "execution": {
            "runtime": "local-dimod",
            "backend": "dimod-cqm-v1",
            "plugins": ["plugins.alpha:bundle"],
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
    assert resolved.plugin_specs == ("plugins.alpha:bundle",)
    assert not resolved.issues


def test_resolution_cli_overrides_instance_defaults() -> None:
    payload = {
        "execution": {
            "runtime": "runtime-from-instance",
            "backend": "backend-from-instance",
            "plugins": ["plugins.from-instance:bundle"],
        }
    }
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime="runtime-from-cli",
        cli_backend="backend-from-cli",
        cli_plugin_specs=("plugins.from-cli:bundle",),
    )

    assert resolved.selection is not None
    assert resolved.selection.runtime_id == "runtime-from-cli"
    assert resolved.selection.backend_id == "backend-from-cli"
    assert resolved.plugin_specs == ("plugins.from-instance:bundle", "plugins.from-cli:bundle")


def test_resolution_reports_missing_selection() -> None:
    resolved = resolve_target_selection(
        instance_payload={"problem": "P"},
        cli_runtime=None,
        cli_backend=None,
    )

    assert resolved.selection is None
    assert resolved.issues
    assert resolved.issues[0].code == "QSOL4006"


def test_resolution_uses_default_backend_when_instance_omits_backend() -> None:
    payload = {"execution": {"runtime": "local-dimod"}}
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime=None,
        cli_backend=None,
    )

    assert resolved.selection is not None
    assert resolved.selection.runtime_id == "local-dimod"
    assert resolved.selection.backend_id == DEFAULT_BACKEND_ID
    assert not resolved.issues


def test_resolution_uses_default_backend_when_no_backend_is_provided() -> None:
    payload = {"execution": {"runtime": "local-dimod"}}
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime="runtime-from-cli",
        cli_backend=None,
    )

    assert resolved.selection is not None
    assert resolved.selection.runtime_id == "runtime-from-cli"
    assert resolved.selection.backend_id == DEFAULT_BACKEND_ID
    assert not resolved.issues


def test_resolution_merges_and_deduplicates_plugin_specs() -> None:
    payload = {
        "execution": {
            "runtime": "local-dimod",
            "backend": "dimod-cqm-v1",
            "plugins": [
                "plugins.alpha:bundle",
                "plugins.beta:bundle",
                "plugins.alpha:bundle",
            ],
        }
    }
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime=None,
        cli_backend=None,
        cli_plugin_specs=(
            "plugins.beta:bundle",
            "plugins.gamma:bundle",
            "plugins.alpha:bundle",
        ),
    )

    assert resolved.selection is not None
    assert resolved.plugin_specs == (
        "plugins.alpha:bundle",
        "plugins.beta:bundle",
        "plugins.gamma:bundle",
    )
    assert not resolved.issues


def test_resolution_rejects_non_list_execution_plugins() -> None:
    payload = {
        "execution": {
            "runtime": "local-dimod",
            "backend": "dimod-cqm-v1",
            "plugins": "not-a-list",
        }
    }
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime=None,
        cli_backend=None,
    )

    assert resolved.selection is not None
    assert resolved.issues
    assert any(issue.code == "QSOL4009" for issue in resolved.issues)


def test_resolution_rejects_invalid_execution_plugins_entries() -> None:
    payload = {
        "execution": {
            "runtime": "local-dimod",
            "backend": "dimod-cqm-v1",
            "plugins": ["plugins.alpha:bundle", "", 1],
        }
    }
    resolved = resolve_target_selection(
        instance_payload=payload,
        cli_runtime=None,
        cli_backend=None,
        cli_plugin_specs=("plugins.beta:bundle",),
    )

    assert resolved.selection is not None
    assert resolved.plugin_specs == ("plugins.alpha:bundle", "plugins.beta:bundle")
    assert len([issue for issue in resolved.issues if issue.code == "QSOL4009"]) == 2
