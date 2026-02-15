from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from qsol.diag.diagnostic import Diagnostic, Severity
from qsol.diag.source import Span
from qsol.parse import ast
from qsol.parse.parser import ParseFailure, parse_to_ast


@dataclass(slots=True)
class ModuleLoadResult:
    program: ast.Program
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass(slots=True)
class ModuleLoader:
    cwd: Path = field(default_factory=Path.cwd)
    _loaded: set[Path] = field(default_factory=set)
    _active: list[Path] = field(default_factory=list)
    _diagnostics: list[Diagnostic] = field(default_factory=list)

    def resolve(self, program: ast.Program, *, root_filename: str) -> ModuleLoadResult:
        imported_items: list[ast.TopItem] = []
        root_path = self._normalize_root_filename(root_filename)

        for item in program.items:
            if not isinstance(item, ast.UseStmt):
                continue
            imported_items.extend(
                self._load_module(item.module, importer_file=root_path, use_span=item.span)
            )

        local_items = [item for item in program.items if not isinstance(item, ast.UseStmt)]
        merged = replace(program, items=[*imported_items, *local_items])
        return ModuleLoadResult(program=merged, diagnostics=list(self._diagnostics))

    def _load_module(
        self, module: str, *, importer_file: Path, use_span: Span
    ) -> list[ast.TopItem]:
        resolved = self._resolve_module_path(module, importer_file=importer_file, use_span=use_span)
        if resolved is None:
            return []

        if resolved in self._loaded:
            return []

        if resolved in self._active:
            cycle_path = " -> ".join([*(str(path) for path in self._active), str(resolved)])
            self._diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2101",
                    message=f"import cycle detected while loading `{module}`",
                    span=use_span,
                    notes=[f"cycle: {cycle_path}"],
                    help=["Break the cycle by removing one `use` edge."],
                )
            )
            return []

        self._active.append(resolved)
        try:
            try:
                source_text = resolved.read_text(encoding="utf-8")
            except OSError as exc:
                self._diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL4003",
                        message=f"failed to read imported module `{module}`",
                        span=use_span,
                        notes=[str(exc), f"path={resolved}"],
                    )
                )
                return []

            try:
                imported_program = parse_to_ast(source_text, filename=str(resolved))
            except ParseFailure as exc:
                self._diagnostics.append(exc.diagnostic)
                return []

            imported_items: list[ast.TopItem] = []
            module_items: list[ast.TopItem] = []
            for item in imported_program.items:
                if isinstance(item, ast.UseStmt):
                    imported_items.extend(
                        self._load_module(item.module, importer_file=resolved, use_span=item.span)
                    )
                elif isinstance(item, (ast.UnknownDef, ast.PredicateDef, ast.FunctionDef)):
                    module_items.append(item)
                else:
                    self._diagnostics.append(
                        Diagnostic(
                            severity=Severity.ERROR,
                            code="QSOL2101",
                            message=(
                                f"imported module `{module}` contains unsupported top-level item "
                                "(`problem` blocks are not allowed)"
                            ),
                            span=item.span,
                            help=[
                                "Imported modules may contain only `use`, `unknown`, "
                                "`predicate`, and `function` top-level items."
                            ],
                        )
                    )

            self._loaded.add(resolved)
            return [*imported_items, *module_items]
        finally:
            self._active.pop()

    def _resolve_module_path(
        self, module: str, *, importer_file: Path, use_span: Span
    ) -> Path | None:
        parts = tuple(part.strip() for part in module.split("."))
        if not parts or any(not part for part in parts):
            self._diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="QSOL2001",
                    message=f"invalid module path `{module}` in `use` statement",
                    span=use_span,
                    help=[
                        "Use dotted module names like `stdlib.permutation` or `mylib.graph.unknowns`."
                    ],
                )
            )
            return None

        if parts[0] == "stdlib":
            if len(parts) == 1:
                self._diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2001",
                        message="`use stdlib` must include a module name",
                        span=use_span,
                        help=[
                            "Use a concrete stdlib module, for example `use stdlib.permutation;`."
                        ],
                    )
                )
                return None
            stdlib_root = Path(__file__).resolve().parents[1] / "stdlib"
            target = stdlib_root.joinpath(*parts[1:]).with_suffix(".qsol")
            if not target.exists() or not target.is_file():
                self._diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="QSOL2001",
                        message=f"unknown stdlib module `{module}`",
                        span=use_span,
                        notes=[f"path={target}"],
                        help=["Check the stdlib module name and installed QSOL version."],
                    )
                )
                return None
            return target.resolve()

        rel_module_path = Path(*parts).with_suffix(".qsol")
        candidates = [importer_file.parent / rel_module_path, self.cwd / rel_module_path]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

        self._diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="QSOL2001",
                message=f"unknown module `{module}`",
                span=use_span,
                notes=[f"searched={', '.join(str(path) for path in candidates)}"],
                help=[
                    "Ensure module path maps to `<module>.qsol` in importer directory or current working directory."
                ],
            )
        )
        return None

    def _normalize_root_filename(self, filename: str) -> Path:
        root = Path(filename)
        if root.is_absolute():
            return root
        return (self.cwd / root).resolve()


def resolve_use_modules(program: ast.Program, *, root_filename: str) -> ModuleLoadResult:
    loader = ModuleLoader()
    return loader.resolve(program, root_filename=root_filename)


__all__ = ["ModuleLoadResult", "ModuleLoader", "resolve_use_modules"]
