"""Each adapter must fail at import time with an install hint when its extra
is missing. The framework is blocked through ``sys.modules`` so these tests
run whether or not the extra is installed."""

from __future__ import annotations

import importlib
import importlib.util
import sys

import pytest

CASES = [
    ("precleared.langchain", ["langchain_core", "langchain_core.tools"], "precleared[langchain]"),
    ("precleared.crewai", ["crewai", "crewai.tools", "crewai_tools"], "precleared[crewai]"),
    ("precleared.llamaindex", ["llama_index", "llama_index.core", "llama_index.core.tools"], "precleared[llamaindex]"),
    ("precleared.openai_agents", ["agents", "agents.tool"], "precleared[openai-agents]"),
]


@pytest.mark.parametrize("module, blocked, hint", CASES, ids=[c[0] for c in CASES])
def test_adapter_import_fails_with_install_hint_when_extra_missing(monkeypatch, module, blocked, hint):
    for name in blocked:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.delitem(sys.modules, module, raising=False)

    with pytest.raises(ImportError) as info:
        importlib.import_module(module)

    message = str(info.value)
    assert module in message
    assert f"pip install '{hint}'" in message
    assert module not in sys.modules


def test_core_package_imports_without_any_framework(monkeypatch):
    """The core client must not pull in pydantic or any framework."""
    for name in ("pydantic", "langchain_core", "crewai", "crewai_tools", "llama_index", "agents"):
        monkeypatch.setitem(sys.modules, name, None)
    for name in [m for m in list(sys.modules) if m == "precleared" or m.startswith("precleared.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    pkg = importlib.import_module("precleared")
    tools = importlib.import_module("precleared._tools")
    assert pkg.Precleared is not None
    assert tools.PreclearedTools is not None


def _installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@pytest.mark.parametrize(
    "module, framework",
    [
        ("precleared.langchain", "langchain_core"),
        ("precleared.crewai", "crewai"),
        ("precleared.llamaindex", "llama_index.core"),
        ("precleared.openai_agents", "agents"),
    ],
)
def test_adapter_imports_when_extra_installed(module, framework):
    if not _installed(framework):
        pytest.skip(f"{framework} is not installed")
    mod = importlib.import_module(module)
    assert callable(mod.precleared_tools)
