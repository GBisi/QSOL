from __future__ import annotations

from pathlib import Path

import pytest

from qsol.config.loader import (
    discover_config_path,
    load_config,
    materialize_instance_payload,
    resolve_combine_mode,
    resolve_failure_policy,
    resolve_selected_scenarios,
    resolve_solve_settings,
)
from qsol.config.types import (
    CombineMode,
    DefaultsConfig,
    ExecutionConfig,
    FailurePolicy,
    QsolConfig,
    ScenarioConfig,
    SelectionConfig,
    SelectionMode,
    SolveConfig,
    SolveSettings,
)


def _write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def test_load_config_parses_minimal_schema(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"

        [scenarios.base]
        problem = "Demo"

        [scenarios.base.sets]
        A = ["a1", "a2"]
        """,
    )

    config = load_config(config_path)
    assert config.schema_version == "1"
    assert list(config.scenarios.keys()) == ["base"]
    assert config.scenarios["base"].problem == "Demo"
    assert config.scenarios["base"].sets["A"] == ["a1", "a2"]


def test_discover_config_path_none_found(tmp_path: Path) -> None:
    model_path = tmp_path / "demo.qsol"
    model_path.write_text("problem Demo {}\n", encoding="utf-8")

    resolved, err = discover_config_path(model_path=model_path, explicit_config=None)
    assert resolved is None
    assert err is not None
    assert "default config was not found" in err


def test_discover_config_path_single_candidate(tmp_path: Path) -> None:
    model_path = tmp_path / "demo.qsol"
    model_path.write_text("problem Demo {}\n", encoding="utf-8")
    config_path = tmp_path / "custom.qsol.toml"
    config_path.write_text('schema_version = "1"\n[scenarios.base]\n', encoding="utf-8")

    resolved, err = discover_config_path(model_path=model_path, explicit_config=None)
    assert err is None
    assert resolved == config_path


def test_discover_config_path_prefers_same_name(tmp_path: Path) -> None:
    model_path = tmp_path / "demo.qsol"
    model_path.write_text("problem Demo {}\n", encoding="utf-8")
    same_name = tmp_path / "demo.qsol.toml"
    other = tmp_path / "other.qsol.toml"
    same_name.write_text('schema_version = "1"\n[scenarios.base]\n', encoding="utf-8")
    other.write_text('schema_version = "1"\n[scenarios.base]\n', encoding="utf-8")

    resolved, err = discover_config_path(model_path=model_path, explicit_config=None)
    assert err is None
    assert resolved == same_name


def test_discover_config_path_ambiguous_without_same_name(tmp_path: Path) -> None:
    model_path = tmp_path / "demo.qsol"
    model_path.write_text("problem Demo {}\n", encoding="utf-8")
    (tmp_path / "a.qsol.toml").write_text(
        'schema_version = "1"\n[scenarios.base]\n', encoding="utf-8"
    )
    (tmp_path / "b.qsol.toml").write_text(
        'schema_version = "1"\n[scenarios.base]\n', encoding="utf-8"
    )

    resolved, err = discover_config_path(model_path=model_path, explicit_config=None)
    assert resolved is None
    assert err is not None
    assert "ambiguous" in err


def test_discover_config_path_respects_explicit_argument(tmp_path: Path) -> None:
    model_path = tmp_path / "demo.qsol"
    model_path.write_text("problem Demo {}\n", encoding="utf-8")
    explicit = tmp_path / "chosen.qsol.toml"

    resolved, err = discover_config_path(model_path=model_path, explicit_config=explicit)
    assert err is None
    assert resolved == explicit


def test_load_config_rejects_invalid_selection_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"
        [selection]
        mode = "bad"

        [scenarios.base]
        """,
    )

    with pytest.raises(ValueError, match="selection.mode"):
        load_config(config_path)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('schema_version = "2"\n[scenarios.base]\n', "schema_version"),
        ('schema_version = "1"\n', "must declare at least one scenario"),
        ("schema_version = 1\n[scenarios.base]\n", "must be a non-empty string"),
        (
            'schema_version = "1"\nselection = 1\n[scenarios.base]\n',
            "`selection` must be a TOML table/object",
        ),
        (
            'schema_version = "1"\n[selection]\nmode = "subset"\n[scenarios.base]\n',
            "selection.mode=subset",
        ),
        (
            'schema_version = "1"\n[selection]\ndefault_scenario = ""\n[scenarios.base]\n',
            "selection.default_scenario",
        ),
        (
            'schema_version = "1"\n[selection]\nsubset = "base"\n[scenarios.base]\n',
            "selection.subset",
        ),
        (
            'schema_version = "1"\n[selection]\nsubset = [""]\n[scenarios.base]\n',
            r"selection\.subset\[0\]",
        ),
        (
            'schema_version = "1"\n[defaults.execution]\nplugins = [1]\n[scenarios.base]\n',
            r"plugins\[0\]",
        ),
        (
            'schema_version = "1"\n[defaults.solve]\nsolutions = true\n[scenarios.base]\n',
            "defaults.solve.solutions",
        ),
        (
            'schema_version = "1"\n[defaults.solve]\nsolutions = 0\n[scenarios.base]\n',
            "defaults.solve.solutions",
        ),
        (
            'schema_version = "1"\n[defaults.solve]\nenergy_min = "x"\n[scenarios.base]\n',
            "defaults.solve.energy_min",
        ),
        (
            'schema_version = "1"\n[defaults.solve]\nenergy_min = 2\nenergy_max = 1\n[scenarios.base]\n',
            "energy_min <= energy_max",
        ),
        (
            'schema_version = "1"\n[scenarios.base]\nsets = []\n',
            "scenarios.base.sets",
        ),
    ],
)
def test_load_config_rejects_invalid_shapes_and_values(
    tmp_path: Path, text: str, expected: str
) -> None:
    config_path = tmp_path / "invalid.qsol.toml"
    _write_text(config_path, text)
    with pytest.raises(ValueError, match=expected):
        load_config(config_path)


def test_load_config_parses_optional_selection_enum_values(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"
        [selection]
        combine_mode = "union"
        failure_policy = "best-effort"

        [scenarios.base]
        """,
    )

    config = load_config(config_path)
    assert config.selection.combine_mode is CombineMode.union
    assert config.selection.failure_policy is FailurePolicy.best_effort


def test_resolve_selected_scenarios_uses_default_and_cli_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"
        [selection]
        default_scenario = "base"

        [scenarios.base]
        [scenarios.alt]
        """,
    )
    config = load_config(config_path)

    default_selected = resolve_selected_scenarios(
        config=config, cli_scenarios=(), cli_all_scenarios=False
    )
    assert default_selected == ["base"]

    cli_selected = resolve_selected_scenarios(
        config=config,
        cli_scenarios=("alt", "base"),
        cli_all_scenarios=False,
    )
    assert cli_selected == ["alt", "base"]


def test_resolve_selected_scenarios_cli_all_and_deduplicates() -> None:
    config = QsolConfig(
        schema_version="1",
        scenarios={
            "base": ScenarioConfig(),
            "stress": ScenarioConfig(),
        },
    )

    selected_all = resolve_selected_scenarios(
        config=config, cli_scenarios=(), cli_all_scenarios=True
    )
    assert selected_all == ["base", "stress"]

    selected_dedup = resolve_selected_scenarios(
        config=config,
        cli_scenarios=("base", "base", "stress"),
        cli_all_scenarios=False,
    )
    assert selected_dedup == ["base", "stress"]


def test_resolve_selected_scenarios_rejects_conflicting_or_unknown_inputs() -> None:
    config = QsolConfig(
        schema_version="1",
        scenarios={
            "base": ScenarioConfig(),
            "stress": ScenarioConfig(),
        },
    )

    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_selected_scenarios(
            config=config,
            cli_scenarios=("base",),
            cli_all_scenarios=True,
        )

    with pytest.raises(ValueError, match="unknown scenario"):
        resolve_selected_scenarios(
            config=config,
            cli_scenarios=("missing",),
            cli_all_scenarios=False,
        )


def test_resolve_selected_scenarios_rejects_unresolvable_defaults() -> None:
    empty = QsolConfig(schema_version="1", scenarios={})
    with pytest.raises(ValueError, match="at least one scenario"):
        resolve_selected_scenarios(config=empty, cli_scenarios=(), cli_all_scenarios=False)

    subset_mode = QsolConfig(
        schema_version="1",
        selection=SelectionConfig(mode=SelectionMode.subset, subset=()),
        scenarios={"base": ScenarioConfig()},
    )
    with pytest.raises(ValueError, match="selection.mode=subset"):
        resolve_selected_scenarios(config=subset_mode, cli_scenarios=(), cli_all_scenarios=False)

    unknown_default = QsolConfig(
        schema_version="1",
        selection=SelectionConfig(default_scenario="missing"),
        scenarios={"base": ScenarioConfig()},
    )
    with pytest.raises(ValueError, match="default_scenario"):
        resolve_selected_scenarios(
            config=unknown_default, cli_scenarios=(), cli_all_scenarios=False
        )

    ambiguous = QsolConfig(
        schema_version="1",
        scenarios={"a": ScenarioConfig(), "b": ScenarioConfig()},
    )
    with pytest.raises(ValueError, match="unable to resolve a default scenario"):
        resolve_selected_scenarios(config=ambiguous, cli_scenarios=(), cli_all_scenarios=False)


def test_resolve_selected_scenarios_honors_config_mode_all() -> None:
    config = QsolConfig(
        schema_version="1",
        selection=SelectionConfig(mode=SelectionMode.all),
        scenarios={"a": ScenarioConfig(), "b": ScenarioConfig()},
    )

    selected = resolve_selected_scenarios(config=config, cli_scenarios=(), cli_all_scenarios=False)
    assert selected == ["a", "b"]


def test_materialize_instance_payload_merges_execution_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"

        [defaults.execution]
        runtime = "local-dimod"
        backend = "dimod-cqm-v1"
        plugins = ["plugins.default:bundle"]

        [scenarios.base]
        problem = "Demo"

        [scenarios.base.sets]
        A = ["a1"]

        [scenarios.base.execution]
        runtime = "custom-runtime"
        plugins = ["plugins.scenario:bundle"]
        """,
    )
    config = load_config(config_path)
    payload = materialize_instance_payload(config=config, scenario_name="base")
    assert payload["problem"] == "Demo"
    execution = payload["execution"]
    assert isinstance(execution, dict)
    assert execution["runtime"] == "custom-runtime"
    assert execution["backend"] == "dimod-cqm-v1"
    assert execution["plugins"] == ["plugins.scenario:bundle"]


def test_materialize_instance_payload_rejects_unknown_scenario(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"
        [scenarios.base]
        """,
    )
    config = load_config(config_path)

    with pytest.raises(ValueError, match="unknown scenario"):
        materialize_instance_payload(config=config, scenario_name="missing")


def test_resolve_combine_mode_and_failure_policy_precedence() -> None:
    config = QsolConfig(
        schema_version="1",
        selection=SelectionConfig(
            combine_mode=CombineMode.union,
            failure_policy=FailurePolicy.best_effort,
        ),
        scenarios={"base": ScenarioConfig()},
    )

    assert resolve_combine_mode(config=config, cli_mode=None) is CombineMode.union
    assert (
        resolve_combine_mode(config=config, cli_mode=CombineMode.intersection)
        is CombineMode.intersection
    )
    assert resolve_failure_policy(config=config, cli_policy=None) is FailurePolicy.best_effort
    assert (
        resolve_failure_policy(config=config, cli_policy=FailurePolicy.fail_fast)
        is FailurePolicy.fail_fast
    )


def test_resolve_solve_settings_precedence(tmp_path: Path) -> None:
    config_path = tmp_path / "demo.qsol.toml"
    _write_text(
        config_path,
        """
        schema_version = "1"

        [defaults.solve]
        solutions = 2
        energy_max = 10

        [scenarios.base]

        [scenarios.base.solve]
        solutions = 5
        energy_min = -2
        """,
    )
    config = load_config(config_path)

    settings = resolve_solve_settings(
        config=config,
        scenario_name="base",
        cli_solutions=None,
        cli_energy_min=None,
        cli_energy_max=None,
    )
    assert settings == SolveSettings(solutions=5, energy_min=-2.0, energy_max=10.0)

    cli_settings = resolve_solve_settings(
        config=config,
        scenario_name="base",
        cli_solutions=3,
        cli_energy_min=-1.0,
        cli_energy_max=1.0,
    )
    assert cli_settings == SolveSettings(solutions=3, energy_min=-1.0, energy_max=1.0)


def test_resolve_solve_settings_rejects_invalid_resolved_values() -> None:
    config = QsolConfig(
        schema_version="1",
        defaults=DefaultsConfig(
            execution=ExecutionConfig(),
            solve=SolveConfig(),
        ),
        scenarios={
            "base": ScenarioConfig(
                solve=SolveConfig(solutions=0),
            )
        },
    )

    with pytest.raises(ValueError, match="unknown scenario"):
        resolve_solve_settings(
            config=config,
            scenario_name="missing",
            cli_solutions=None,
            cli_energy_min=None,
            cli_energy_max=None,
        )

    with pytest.raises(ValueError, match="solutions"):
        resolve_solve_settings(
            config=config,
            scenario_name="base",
            cli_solutions=None,
            cli_energy_min=None,
            cli_energy_max=None,
        )

    valid_config = QsolConfig(
        schema_version="1",
        scenarios={"base": ScenarioConfig()},
    )
    with pytest.raises(ValueError, match="energy_min <= energy_max"):
        resolve_solve_settings(
            config=valid_config,
            scenario_name="base",
            cli_solutions=None,
            cli_energy_min=2.0,
            cli_energy_max=1.0,
        )
