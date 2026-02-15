from __future__ import annotations

import copy
import tomllib
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import TypeVar, cast

from qsol.config.types import (
    CombineMode,
    DefaultsConfig,
    EntryPointConfig,
    ExecutionConfig,
    FailurePolicy,
    QsolConfig,
    ScenarioConfig,
    SelectionConfig,
    SelectionMode,
    SolveConfig,
    SolveSettings,
)

E = TypeVar("E", bound=Enum)


def discover_config_path(
    *, model_path: Path, explicit_config: Path | None
) -> tuple[Path | None, str | None]:
    if explicit_config is not None:
        return explicit_config, None

    candidates = sorted(model_path.parent.glob("*.qsol.toml"))
    preferred = model_path.with_suffix(".qsol.toml")

    if not candidates:
        return (
            None,
            (
                "config file not provided and default config was not found: "
                f"{preferred}; pass `--config <path>`"
            ),
        )

    if len(candidates) == 1:
        return candidates[0], None

    if preferred in candidates:
        return preferred, None

    candidate_names = ", ".join(path.name for path in candidates)
    return (
        None,
        (
            "config file not provided and default config is ambiguous; "
            f"found: {candidate_names}; expected `{preferred.name}` or pass `--config <path>`"
        ),
    )


def load_config(path: str | Path) -> QsolConfig:
    config_path = Path(path)
    with config_path.open("rb") as f:
        payload = tomllib.load(f)

    if not isinstance(payload, Mapping):
        raise ValueError("config payload must be a TOML table/object")

    root = cast(Mapping[str, object], payload)
    schema_version = _require_str(root, "schema_version")
    if schema_version != "1":
        raise ValueError('`schema_version` must be "1"')

    selection_raw = root.get("selection", {})
    defaults_raw = root.get("defaults", {})
    entrypoint_raw = root.get("entrypoint", {})
    scenarios_raw = root.get("scenarios")

    entrypoint = _parse_entrypoint(entrypoint_raw, path="entrypoint")
    selection = _parse_selection(selection_raw, path="selection")
    defaults = _parse_defaults(defaults_raw, path="defaults")
    scenarios = _parse_scenarios(scenarios_raw, path="scenarios")

    return QsolConfig(
        schema_version=schema_version,
        entrypoint=entrypoint,
        selection=selection,
        defaults=defaults,
        scenarios=scenarios,
    )


def resolve_selected_scenarios(
    *,
    config: QsolConfig,
    cli_scenarios: Sequence[str],
    cli_all_scenarios: bool,
) -> list[str]:
    if cli_all_scenarios and cli_scenarios:
        raise ValueError("`--all-scenarios` cannot be combined with `--scenario`")

    scenario_names = list(config.scenarios.keys())
    if not scenario_names:
        raise ValueError("config must declare at least one scenario")

    if cli_all_scenarios:
        return scenario_names

    if cli_scenarios:
        return _validate_and_deduplicate_names(
            names=cli_scenarios,
            available=config.scenarios,
            path="CLI `--scenario`",
        )

    if config.entrypoint.all_scenarios:
        return scenario_names

    if config.entrypoint.scenarios:
        return _validate_and_deduplicate_names(
            names=config.entrypoint.scenarios,
            available=config.scenarios,
            path="entrypoint.scenarios",
        )

    if config.entrypoint.scenario is not None:
        if config.entrypoint.scenario not in config.scenarios:
            raise ValueError(
                f"`entrypoint.scenario` references unknown scenario `{config.entrypoint.scenario}`"
            )
        return [config.entrypoint.scenario]

    mode = config.selection.mode
    if mode is SelectionMode.all:
        return scenario_names

    if mode is SelectionMode.subset:
        if not config.selection.subset:
            raise ValueError("`selection.mode=subset` requires non-empty `selection.subset`")
        return _validate_and_deduplicate_names(
            names=config.selection.subset,
            available=config.scenarios,
            path="selection.subset",
        )

    default_scenario = config.selection.default_scenario
    if default_scenario is not None:
        if default_scenario not in config.scenarios:
            raise ValueError(
                f"`selection.default_scenario` references unknown scenario `{default_scenario}`"
            )
        return [default_scenario]

    if len(scenario_names) == 1:
        return scenario_names

    raise ValueError(
        "unable to resolve a default scenario; set `selection.default_scenario`, "
        "set `selection.mode`, or pass CLI scenario selectors"
    )


def resolve_combine_mode(*, config: QsolConfig, cli_mode: CombineMode | None) -> CombineMode:
    if cli_mode is not None:
        return cli_mode
    if config.entrypoint.combine_mode is not None:
        return config.entrypoint.combine_mode
    if config.selection.combine_mode is not None:
        return config.selection.combine_mode
    return CombineMode.intersection


def resolve_failure_policy(
    *, config: QsolConfig, cli_policy: FailurePolicy | None
) -> FailurePolicy:
    if cli_policy is not None:
        return cli_policy
    if config.entrypoint.failure_policy is not None:
        return config.entrypoint.failure_policy
    if config.selection.failure_policy is not None:
        return config.selection.failure_policy
    return FailurePolicy.run_all_fail


def resolve_solve_settings(
    *,
    config: QsolConfig,
    scenario_name: str,
    cli_solutions: int | None,
    cli_energy_min: float | None,
    cli_energy_max: float | None,
) -> SolveSettings:
    if scenario_name not in config.scenarios:
        raise ValueError(f"unknown scenario `{scenario_name}`")

    scenario = config.scenarios[scenario_name]
    defaults = config.defaults.solve

    resolved_solutions = _coalesce_int(
        cli_solutions,
        scenario.solve.solutions,
        config.entrypoint.solutions,
        defaults.solutions,
        1,
    )
    if resolved_solutions < 1:
        raise ValueError("resolved solve option `solutions` must be >= 1")

    resolved_energy_min = _coalesce_float(
        cli_energy_min,
        scenario.solve.energy_min,
        config.entrypoint.energy_min,
        defaults.energy_min,
    )
    resolved_energy_max = _coalesce_float(
        cli_energy_max,
        scenario.solve.energy_max,
        config.entrypoint.energy_max,
        defaults.energy_max,
    )
    if (
        resolved_energy_min is not None
        and resolved_energy_max is not None
        and resolved_energy_min > resolved_energy_max
    ):
        raise ValueError("resolved solve options require `energy_min <= energy_max`")

    return SolveSettings(
        solutions=resolved_solutions,
        energy_min=resolved_energy_min,
        energy_max=resolved_energy_max,
    )


def materialize_instance_payload(*, config: QsolConfig, scenario_name: str) -> dict[str, object]:
    if scenario_name not in config.scenarios:
        raise ValueError(f"unknown scenario `{scenario_name}`")

    scenario = config.scenarios[scenario_name]
    entrypoint_execution = ExecutionConfig(
        runtime=config.entrypoint.runtime,
        backend=config.entrypoint.backend,
        plugins=config.entrypoint.plugins,
    )
    execution = _merge_execution(config.defaults.execution, entrypoint_execution)
    execution = _merge_execution(execution, scenario.execution)

    payload: dict[str, object] = {
        "sets": copy.deepcopy(scenario.sets),
        "params": copy.deepcopy(scenario.params),
    }
    if scenario.problem is not None:
        payload["problem"] = scenario.problem

    execution_payload: dict[str, object] = {}
    if execution.runtime is not None:
        execution_payload["runtime"] = execution.runtime
    if execution.backend is not None:
        execution_payload["backend"] = execution.backend
    if execution.plugins:
        execution_payload["plugins"] = list(execution.plugins)
    if execution_payload:
        payload["execution"] = execution_payload

    return payload


def resolve_output_format(*, config: QsolConfig, cli_format: str | None) -> str:
    if cli_format is not None:
        return cli_format
    if config.entrypoint.output_format is not None:
        return config.entrypoint.output_format
    return "qubo"


def resolve_runtime_options(
    *,
    config: QsolConfig,
    cli_runtime_options: Mapping[str, object],
) -> dict[str, object]:
    resolved = copy.deepcopy(config.entrypoint.runtime_options)
    resolved.update(cli_runtime_options)
    return resolved


def _parse_entrypoint(raw: object, *, path: str) -> EntryPointConfig:
    table = _require_mapping(raw, path)
    scenario = _parse_optional_non_empty_str(table.get("scenario"), path=f"{path}.scenario")
    scenarios = _parse_optional_name_list(table, "scenarios", path=path)
    if scenario is not None and scenarios:
        raise ValueError(f"`{path}.scenario` cannot be combined with `{path}.scenarios`")

    all_scenarios = _parse_optional_bool(table.get("all_scenarios"), path=f"{path}.all_scenarios")
    if all_scenarios and (scenario is not None or scenarios):
        raise ValueError(
            f"`{path}.all_scenarios=true` cannot be combined with `{path}.scenario(s)`"
        )

    combine_mode = _parse_optional_enum(
        table.get("combine_mode"), enum_cls=CombineMode, path=f"{path}.combine_mode"
    )
    failure_policy = _parse_optional_enum(
        table.get("failure_policy"), enum_cls=FailurePolicy, path=f"{path}.failure_policy"
    )
    out = _parse_optional_non_empty_str(table.get("out"), path=f"{path}.out")
    output_format = _parse_optional_non_empty_str(table.get("format"), path=f"{path}.format")
    runtime = _parse_optional_non_empty_str(table.get("runtime"), path=f"{path}.runtime")
    backend = _parse_optional_non_empty_str(table.get("backend"), path=f"{path}.backend")

    plugins: tuple[str, ...] | None = None
    if "plugins" in table:
        plugins = _parse_plugin_list(table.get("plugins"), path=f"{path}.plugins")

    runtime_options = _parse_optional_runtime_options(table, "runtime_options", path=path)

    solutions: int | None = None
    if "solutions" in table:
        solutions = _parse_positive_int(table.get("solutions"), path=f"{path}.solutions")

    energy_min: float | None = None
    if "energy_min" in table:
        energy_min = _parse_float(table.get("energy_min"), path=f"{path}.energy_min")

    energy_max: float | None = None
    if "energy_max" in table:
        energy_max = _parse_float(table.get("energy_max"), path=f"{path}.energy_max")

    if energy_min is not None and energy_max is not None and energy_min > energy_max:
        raise ValueError(f"`{path}` requires `energy_min <= energy_max`")

    return EntryPointConfig(
        scenario=scenario,
        scenarios=scenarios,
        all_scenarios=all_scenarios,
        combine_mode=combine_mode,
        failure_policy=failure_policy,
        out=out,
        output_format=output_format,
        runtime=runtime,
        backend=backend,
        plugins=plugins,
        runtime_options=runtime_options,
        solutions=solutions,
        energy_min=energy_min,
        energy_max=energy_max,
    )


def _parse_selection(raw: object, *, path: str) -> SelectionConfig:
    table = _require_mapping(raw, path)

    mode_raw = table.get("mode", SelectionMode.default.value)
    mode = _parse_enum(mode_raw, enum_cls=SelectionMode, path=f"{path}.mode")

    default_scenario = _parse_optional_non_empty_str(
        table.get("default_scenario"), path=f"{path}.default_scenario"
    )
    subset = _parse_optional_name_list(table, "subset", path=path)
    combine_mode = _parse_optional_enum(
        table.get("combine_mode"), enum_cls=CombineMode, path=f"{path}.combine_mode"
    )
    failure_policy = _parse_optional_enum(
        table.get("failure_policy"), enum_cls=FailurePolicy, path=f"{path}.failure_policy"
    )

    if mode is SelectionMode.subset and not subset:
        raise ValueError("`selection.mode=subset` requires non-empty `selection.subset`")

    return SelectionConfig(
        mode=mode,
        default_scenario=default_scenario,
        subset=subset,
        combine_mode=combine_mode,
        failure_policy=failure_policy,
    )


def _parse_defaults(raw: object, *, path: str) -> DefaultsConfig:
    table = _require_mapping(raw, path)
    execution = _parse_execution(table.get("execution"), path=f"{path}.execution")
    solve = _parse_solve(table.get("solve"), path=f"{path}.solve")
    return DefaultsConfig(execution=execution, solve=solve)


def _parse_scenarios(raw: object, *, path: str) -> dict[str, ScenarioConfig]:
    table = _require_mapping(raw, path)
    if not table:
        raise ValueError("`scenarios` must declare at least one scenario")

    scenarios: dict[str, ScenarioConfig] = {}
    for key, value in table.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"`{path}` keys must be non-empty strings")
        scenario_name = key.strip()
        scenario_path = f"{path}.{scenario_name}"
        scenario_table = _require_mapping(value, scenario_path)
        problem = _parse_optional_non_empty_str(
            scenario_table.get("problem"), path=f"{scenario_path}.problem"
        )

        sets = _parse_optional_mapping(scenario_table, "sets", scenario_path)
        params = _parse_optional_mapping(scenario_table, "params", scenario_path)
        execution = _parse_execution(
            scenario_table.get("execution"), path=f"{scenario_path}.execution"
        )
        solve = _parse_solve(scenario_table.get("solve"), path=f"{scenario_path}.solve")

        scenarios[scenario_name] = ScenarioConfig(
            problem=problem,
            sets=sets,
            params=params,
            execution=execution,
            solve=solve,
        )
    return scenarios


def _parse_execution(raw: object, *, path: str) -> ExecutionConfig:
    if raw is None:
        return ExecutionConfig()
    table = _require_mapping(raw, path)
    runtime = _parse_optional_non_empty_str(table.get("runtime"), path=f"{path}.runtime")
    backend = _parse_optional_non_empty_str(table.get("backend"), path=f"{path}.backend")

    plugins: tuple[str, ...] | None = None
    if "plugins" in table:
        plugins = _parse_plugin_list(table.get("plugins"), path=f"{path}.plugins")

    return ExecutionConfig(runtime=runtime, backend=backend, plugins=plugins)


def _parse_solve(raw: object, *, path: str) -> SolveConfig:
    if raw is None:
        return SolveConfig()
    table = _require_mapping(raw, path)

    solutions: int | None = None
    if "solutions" in table:
        solutions = _parse_positive_int(table.get("solutions"), path=f"{path}.solutions")

    energy_min: float | None = None
    energy_max: float | None = None
    if "energy_min" in table:
        energy_min = _parse_float(table.get("energy_min"), path=f"{path}.energy_min")
    if "energy_max" in table:
        energy_max = _parse_float(table.get("energy_max"), path=f"{path}.energy_max")
    if energy_min is not None and energy_max is not None and energy_min > energy_max:
        raise ValueError(f"`{path}` requires `energy_min <= energy_max`")

    return SolveConfig(solutions=solutions, energy_min=energy_min, energy_max=energy_max)


def _merge_execution(defaults: ExecutionConfig, scenario: ExecutionConfig) -> ExecutionConfig:
    runtime = scenario.runtime if scenario.runtime is not None else defaults.runtime
    backend = scenario.backend if scenario.backend is not None else defaults.backend
    plugins = scenario.plugins if scenario.plugins is not None else defaults.plugins
    return ExecutionConfig(runtime=runtime, backend=backend, plugins=plugins)


def _validate_and_deduplicate_names(
    *,
    names: Sequence[str],
    available: Mapping[str, ScenarioConfig],
    path: str,
) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in available:
            raise ValueError(f"{path} references unknown scenario `{name}`")
        if name in seen:
            continue
        seen.add(name)
        resolved.append(name)
    return resolved


def _require_mapping(raw: object, path: str) -> Mapping[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"`{path}` must be a TOML table/object")
    return cast(Mapping[str, object], raw)


def _require_str(table: Mapping[str, object], key: str) -> str:
    raw = table.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"`{key}` must be a non-empty string")
    return raw.strip()


def _parse_optional_non_empty_str(raw: object, *, path: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"`{path}` must be a non-empty string when provided")
    return raw.strip()


def _parse_optional_bool(raw: object, *, path: str) -> bool:
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise ValueError(f"`{path}` must be a boolean when provided")
    return raw


def _parse_optional_mapping(
    table: Mapping[str, object], key: str, root_path: str
) -> dict[str, object]:
    if key not in table:
        return {}
    raw = table.get(key)
    if not isinstance(raw, Mapping):
        raise ValueError(f"`{root_path}.{key}` must be a TOML table/object")
    return {str(k): copy.deepcopy(v) for k, v in raw.items()}


def _parse_optional_name_list(
    table: Mapping[str, object], key: str, *, path: str
) -> tuple[str, ...]:
    if key not in table:
        return ()
    raw = table.get(key)
    if not isinstance(raw, list):
        raise ValueError(f"`{path}.{key}` must be an array of non-empty strings")
    values: list[str] = []
    for idx, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"`{path}.{key}[{idx}]` must be a non-empty string")
        values.append(value.strip())
    return tuple(values)


def _parse_plugin_list(raw: object, *, path: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"`{path}` must be an array of non-empty plugin specs")
    values: list[str] = []
    for idx, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"`{path}[{idx}]` must be a non-empty plugin spec string")
        values.append(value.strip())
    return tuple(values)


def _parse_optional_runtime_options(
    table: Mapping[str, object], key: str, *, path: str
) -> dict[str, object]:
    if key not in table:
        return {}
    raw = table.get(key)
    if not isinstance(raw, Mapping):
        raise ValueError(f"`{path}.{key}` must be a TOML table/object")

    runtime_options: dict[str, object] = {}
    for option_key, option_value in raw.items():
        normalized_key = str(option_key).strip()
        if not normalized_key:
            raise ValueError(f"`{path}.{key}` keys must be non-empty strings")
        runtime_options[normalized_key] = copy.deepcopy(option_value)
    return runtime_options


def _parse_positive_int(raw: object, *, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"`{path}` must be an integer")
    if raw < 1:
        raise ValueError(f"`{path}` must be >= 1")
    return raw


def _parse_float(raw: object, *, path: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"`{path}` must be a number")
    return float(raw)


def _parse_enum(raw: object, *, enum_cls: type[E], path: str) -> E:
    if not isinstance(raw, str):
        raise ValueError(f"`{path}` must be a string")
    try:
        return enum_cls(raw)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValueError(f"`{path}` must be one of: {allowed}") from exc


def _parse_optional_enum(raw: object, *, enum_cls: type[E], path: str) -> E | None:
    if raw is None:
        return None
    return _parse_enum(raw, enum_cls=enum_cls, path=path)


def _coalesce_int(*values: int | None) -> int:
    for value in values:
        if value is not None:
            return value
    raise ValueError("no integer fallback value was provided")


def _coalesce_float(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None
