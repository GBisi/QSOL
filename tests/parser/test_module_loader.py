from __future__ import annotations

from pathlib import Path

from qsol.diag.source import Span
from qsol.parse import ast
from qsol.parse.module_loader import ModuleLoader
from qsol.parse.parser import parse_to_ast


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def test_module_loader_resolves_from_importer_directory_before_cwd(tmp_path: Path) -> None:
    importer_dir = tmp_path / "importer"
    cwd_dir = tmp_path / "cwd"
    root_model = importer_dir / "root.qsol"

    _write(
        root_model,
        """
use mylib.graph.unknowns;

problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(
        importer_dir / "mylib" / "graph" / "unknowns.qsol",
        """
unknown FromImporter(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x in A) = s.has(x); }
}
""",
    )
    _write(
        cwd_dir / "mylib" / "graph" / "unknowns.qsol",
        """
unknown FromCwd(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x in A) = s.has(x); }
}
""",
    )

    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=cwd_dir).resolve(program, root_filename=str(root_model))

    assert not any(diag.is_error for diag in result.diagnostics)
    imported_unknowns = [item for item in result.program.items if isinstance(item, ast.UnknownDef)]
    assert imported_unknowns
    assert imported_unknowns[0].name == "FromImporter"


def test_module_loader_falls_back_to_cwd_for_user_modules(tmp_path: Path) -> None:
    importer_dir = tmp_path / "importer"
    cwd_dir = tmp_path / "cwd"
    root_model = importer_dir / "root.qsol"

    _write(
        root_model,
        """
use mylib.base;

problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(
        cwd_dir / "mylib" / "base.qsol",
        """
unknown Base(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x in A) = s.has(x); }
}
""",
    )

    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=cwd_dir).resolve(program, root_filename=str(root_model))

    assert not any(diag.is_error for diag in result.diagnostics)
    imported_unknowns = [item for item in result.program.items if isinstance(item, ast.UnknownDef)]
    assert imported_unknowns
    assert imported_unknowns[0].name == "Base"


def test_module_loader_resolves_stdlib_modules() -> None:
    program = parse_to_ast(
        """
use stdlib.permutation;

problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
        filename="root.qsol",
    )
    result = ModuleLoader().resolve(program, root_filename="root.qsol")
    assert not any(diag.is_error for diag in result.diagnostics)
    imported_unknown_names = [
        item.name for item in result.program.items if isinstance(item, ast.UnknownDef)
    ]
    assert "Permutation" in imported_unknown_names
    assert "BijectiveMapping" in imported_unknown_names


def test_module_loader_reports_missing_module(tmp_path: Path) -> None:
    root_model = tmp_path / "root.qsol"
    _write(
        root_model,
        """
use mylib.missing;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=tmp_path).resolve(program, root_filename=str(root_model))
    assert any(diag.code == "QSOL2001" for diag in result.diagnostics)


def test_module_loader_reports_cycles(tmp_path: Path) -> None:
    root_model = tmp_path / "root.qsol"
    _write(
        root_model,
        """
use mylib.a;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(
        tmp_path / "mylib" / "a.qsol",
        """
use mylib.b;
unknown AType(X) {
  rep { s : Subset(X); }
  laws { must true; }
  view { predicate has(x in X) = s.has(x); }
}
""",
    )
    _write(
        tmp_path / "mylib" / "b.qsol",
        """
use mylib.a;
unknown BType(X) {
  rep { s : Subset(X); }
  laws { must true; }
  view { predicate has(x in X) = s.has(x); }
}
""",
    )
    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=tmp_path).resolve(program, root_filename=str(root_model))
    assert any(diag.code == "QSOL2101" and "cycle" in diag.message for diag in result.diagnostics)


def test_module_loader_rejects_problem_blocks_in_imported_modules(tmp_path: Path) -> None:
    root_model = tmp_path / "root.qsol"
    _write(
        root_model,
        """
use mylib.invalid;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(
        tmp_path / "mylib" / "invalid.qsol",
        """
problem Invalid {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=tmp_path).resolve(program, root_filename=str(root_model))
    assert any(
        diag.code == "QSOL2101" and "problem" in diag.message.lower() for diag in result.diagnostics
    )


def test_module_loader_deduplicates_repeated_module_imports(tmp_path: Path) -> None:
    root_model = tmp_path / "root.qsol"
    _write(
        root_model,
        """
use mylib.shared;
use mylib.shared;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(
        tmp_path / "mylib" / "shared.qsol",
        """
unknown Shared(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x in A) = s.has(x); }
}
""",
    )
    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=tmp_path).resolve(program, root_filename=str(root_model))

    unknown_names = [item.name for item in result.program.items if isinstance(item, ast.UnknownDef)]
    assert unknown_names.count("Shared") == 1


def test_module_loader_reports_import_read_failure(tmp_path: Path, monkeypatch) -> None:
    root_model = tmp_path / "root.qsol"
    broken_module = tmp_path / "mylib" / "broken.qsol"
    _write(
        root_model,
        """
use mylib.broken;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(
        broken_module,
        """
unknown Broken(A) {
  rep { s : Subset(A); }
  laws { must true; }
  view { predicate has(x in A) = s.has(x); }
}
""",
    )
    real_read_text = Path.read_text
    broken_module_resolved = broken_module.resolve()

    def _patched_read_text(path: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if path.resolve() == broken_module_resolved:
            raise OSError("simulated read failure")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _patched_read_text)
    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=tmp_path).resolve(program, root_filename=str(root_model))
    assert any(diag.code == "QSOL4003" for diag in result.diagnostics)


def test_module_loader_propagates_parse_errors_from_imported_module(tmp_path: Path) -> None:
    root_model = tmp_path / "root.qsol"
    _write(
        root_model,
        """
use mylib.bad;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
    )
    _write(tmp_path / "mylib" / "bad.qsol", "unknown Broken(")

    program = parse_to_ast(root_model.read_text(encoding="utf-8"), filename=str(root_model))
    result = ModuleLoader(cwd=tmp_path).resolve(program, root_filename=str(root_model))
    assert any(diag.code == "QSOL1001" for diag in result.diagnostics)


def test_module_loader_rejects_invalid_module_path_shape(tmp_path: Path) -> None:
    loader = ModuleLoader(cwd=tmp_path)
    root_model = tmp_path / "root.qsol"
    span = Span(
        start_offset=0,
        end_offset=0,
        line=1,
        col=1,
        end_line=1,
        end_col=1,
        filename=str(root_model),
    )

    resolved = loader._resolve_module_path(  # noqa: SLF001
        "mylib..broken", importer_file=root_model, use_span=span
    )
    assert resolved is None
    assert any(
        diag.code == "QSOL2001" and "invalid module path" in diag.message
        for diag in loader._diagnostics
    )  # noqa: SLF001


def test_module_loader_rejects_bare_stdlib_import() -> None:
    program = parse_to_ast(
        """
use stdlib;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
        filename="root.qsol",
    )
    result = ModuleLoader().resolve(program, root_filename="root.qsol")
    assert any(
        diag.code == "QSOL2001" and "use stdlib" in diag.message for diag in result.diagnostics
    )


def test_module_loader_reports_unknown_stdlib_module() -> None:
    program = parse_to_ast(
        """
use stdlib.this_module_does_not_exist;
problem P {
  set A;
  find S : Subset(A);
  must true;
}
""",
        filename="root.qsol",
    )
    result = ModuleLoader().resolve(program, root_filename="root.qsol")
    assert any(
        diag.code == "QSOL2001" and "unknown stdlib module" in diag.message
        for diag in result.diagnostics
    )
