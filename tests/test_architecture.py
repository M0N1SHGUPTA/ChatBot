"""
Keeps the layout in PROJECT_ARCHITECTURE.md honest by reading imports (no project code runs).

    models.py                    stdlib only
    ingestion / retrieval        independent pipelines: neither imports the other
    pipelines, chat, leads       never import the API, CLI or container (those sit on top)
"""
import ast
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
STDLIB = set(sys.stdlib_module_names) | {"__future__"}
TOP_LEVEL = {"app.api", "app.cli", "app.container"}

# package -> app modules it must not import
BANNED = {
    "ingestion": TOP_LEVEL | {"app.retrieval", "app.chat", "app.leads"},
    "retrieval": TOP_LEVEL | {"app.ingestion", "app.chat", "app.leads"},
    "vectorstore": TOP_LEVEL | {"app.ingestion", "app.retrieval", "app.chat", "app.leads"},
    "chat": TOP_LEVEL | {"app.ingestion", "app.retrieval"},
    "leads": TOP_LEVEL | {"app.ingestion", "app.retrieval"},
}


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _cases():
    for pkg in BANNED:
        for f in sorted((APP / pkg).rglob("*.py")):
            yield pytest.param(pkg, f, id=f"{pkg}/{f.name}")


@pytest.mark.parametrize("pkg,path", list(_cases()))
def test_package_imports(pkg, path):
    bad = [m for m in _imports(path) if any(m == b or m.startswith(b + ".") for b in BANNED[pkg])]
    assert not bad, f"{path.relative_to(APP)} must not import: {bad}"


def test_models_are_stdlib_only():
    bad = [m for m in _imports(APP / "models.py") if m.split(".")[0] not in STDLIB]
    assert not bad, f"models.py must only import the standard library: {bad}"


def test_no_legacy_modules():
    legacy_top = {"config", "ingestion", "vector_store", "rag_pipeline", "conversational_rag", "leads_manager"}
    legacy_app = {"app.domain", "app.ports", "app.adapters", "app.services", "app.content", "app.core",
                  "app.entrypoints"}
    for f in APP.rglob("*.py"):
        hits = [m for m in _imports(f)
                if m.split(".")[0] in legacy_top or any(m == p or m.startswith(p + ".") for p in legacy_app)]
        assert not hits, f"{f.relative_to(APP)} imports removed modules {hits}"
