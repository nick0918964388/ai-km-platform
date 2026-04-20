"""
Unit tests for ToolRegistry auto-discovery.

Strategy: inject fake packages into sys.modules at test-time using a helper that
creates real Python module objects (types.ModuleType) with the required attributes.
No real `tools/` filesystem I/O is needed — we never touch the actual tools directory.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sys
import types
import pytest

from app.services.maximo_tools.base import Tool, ToolDefinition, ToolResult, UserContext
from app.services.maximo_tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str, input_schema: dict | None = None) -> Tool:
    """Build a minimal concrete Tool instance for testing."""

    schema = input_schema if input_schema is not None else {
        "type": "object",
        "properties": {"asset_num": {"type": "string"}},
    }

    class _TestTool(Tool):
        definition = ToolDefinition(
            name=name,
            description=f"Test tool {name}",
            input_schema=schema,
        )

        async def execute(self, params: dict, user_ctx: UserContext) -> ToolResult:
            return ToolResult(success=True)

    return _TestTool()


def _pkg_name(base: str) -> str:
    """Derive a child module name from a base package name."""
    return f"{base}.tool_module"


# ---------------------------------------------------------------------------
# monkeypatch pkgutil.iter_modules for controlled fake-package discovery
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cleanup_fake_modules():
    """Ensure no test pollution in sys.modules after each test."""
    before = set(sys.modules.keys())
    yield
    after = set(sys.modules.keys())
    for name in after - before:
        if name.startswith("_fake_tools_"):
            sys.modules.pop(name, None)


def build_registry_with_modules(
    monkeypatch,
    modules: dict[str, dict],   # {short_name: {attr: value, ...}}
    pkg_prefix: str = "_fake_tools_test",
) -> ToolRegistry:
    """
    Helper: inject fake modules and return a ToolRegistry pointed at them.

    `modules` maps short module names to attribute dicts.
    A `REGISTER` key with a Tool value will be discovered.
    A missing `REGISTER` key means the module has no constant.
    """
    import pkgutil

    pkg_name = pkg_prefix
    child_names = []

    # 1. Create package
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = []
    pkg.__package__ = pkg_name
    sys.modules[pkg_name] = pkg

    # 2. Create child modules
    for short, attrs in modules.items():
        full_name = f"{pkg_name}.{short}"
        mod = types.ModuleType(full_name)
        mod.__package__ = pkg_name
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[full_name] = mod
        child_names.append(full_name)

    # 3. Patch pkgutil.iter_modules to return our fake children
    import pkgutil as _pkgutil

    original_iter = _pkgutil.iter_modules

    def fake_iter_modules(path, prefix=""):
        # Only intercept calls for our fake package
        if path is pkg.__path__:
            for full_name in child_names:
                yield pkgutil.ModuleInfo(None, full_name, False)
        else:
            yield from original_iter(path, prefix)

    monkeypatch.setattr(_pkgutil, "iter_modules", fake_iter_modules)

    return ToolRegistry(tools_package=pkg_name)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestToolRegistryEmptyPackage:
    def test_empty_package_zero_tools(self, monkeypatch):
        registry = build_registry_with_modules(monkeypatch, {}, pkg_prefix="_fake_tools_empty")
        assert len(registry) == 0
        assert registry.list_tools() == []
        assert registry.list_definitions() == []
        assert registry.names() == []


class TestToolRegistrySingleTool:
    def test_single_tool_registered(self, monkeypatch):
        tool = _make_tool("get_vehicle_info")
        registry = build_registry_with_modules(
            monkeypatch,
            {"get_vehicle_info": {"REGISTER": tool}},
            pkg_prefix="_fake_tools_single",
        )

        assert len(registry) == 1
        assert "get_vehicle_info" in registry

    def test_get_returns_correct_instance(self, monkeypatch):
        tool = _make_tool("get_vehicle_info")
        registry = build_registry_with_modules(
            monkeypatch,
            {"get_vehicle_info": {"REGISTER": tool}},
            pkg_prefix="_fake_tools_get",
        )

        result = registry.get("get_vehicle_info")
        assert result is tool

    def test_get_unknown_name_returns_none(self, monkeypatch):
        tool = _make_tool("get_vehicle_info")
        registry = build_registry_with_modules(
            monkeypatch,
            {"get_vehicle_info": {"REGISTER": tool}},
            pkg_prefix="_fake_tools_get_none",
        )

        assert registry.get("nonexistent") is None


class TestToolRegistryModuleWithoutRegister:
    def test_module_without_register_skipped_no_error(self, monkeypatch):
        tool = _make_tool("real_tool")
        registry = build_registry_with_modules(
            monkeypatch,
            {
                "has_register": {"REGISTER": tool},
                "no_register": {"SOME_CONST": 42},   # no REGISTER
            },
            pkg_prefix="_fake_tools_no_reg",
        )

        # Only the module with REGISTER is loaded
        assert len(registry) == 1
        assert "real_tool" in registry

    def test_module_with_none_register_skipped(self, monkeypatch):
        registry = build_registry_with_modules(
            monkeypatch,
            {"explicit_none": {"REGISTER": None}},
            pkg_prefix="_fake_tools_none_reg",
        )
        assert len(registry) == 0


class TestToolRegistryRegisterNotToolInstance:
    def test_register_is_dict_skipped_with_warning(self, monkeypatch, caplog):
        registry = build_registry_with_modules(
            monkeypatch,
            {"bad_module": {"REGISTER": {"not": "a tool"}}},
            pkg_prefix="_fake_tools_bad_dict",
        )
        assert len(registry) == 0
        # Warning should mention the module
        assert any("not a Tool instance" in r.message for r in caplog.records)

    def test_register_is_string_skipped_with_warning(self, monkeypatch, caplog):
        registry = build_registry_with_modules(
            monkeypatch,
            {"string_module": {"REGISTER": "im_not_a_tool"}},
            pkg_prefix="_fake_tools_bad_str",
        )
        assert len(registry) == 0
        assert any("not a Tool instance" in r.message for r in caplog.records)

    def test_register_is_class_not_instance_skipped(self, monkeypatch, caplog):
        """REGISTER points to the class itself, not an instance."""

        class UninstantiatedTool(Tool):
            definition = ToolDefinition(
                name="uninstantiated",
                description="not an instance",
                input_schema={},
            )

            async def execute(self, params, user_ctx):
                return ToolResult(success=True)

        registry = build_registry_with_modules(
            monkeypatch,
            {"class_register": {"REGISTER": UninstantiatedTool}},  # class, not instance
            pkg_prefix="_fake_tools_class_reg",
        )
        assert len(registry) == 0
        assert any("not a Tool instance" in r.message for r in caplog.records)


class TestToolRegistryDuplicateToolName:
    def test_duplicate_name_first_wins(self, monkeypatch, caplog):
        tool_a = _make_tool("foo")
        tool_b = _make_tool("foo")  # same name

        registry = build_registry_with_modules(
            monkeypatch,
            {
                "module_a": {"REGISTER": tool_a},
                "module_b": {"REGISTER": tool_b},
            },
            pkg_prefix="_fake_tools_dup",
        )

        assert len(registry) == 1
        # First registration wins
        assert registry.get("foo") is tool_a
        # Error logged for duplicate
        assert any("Duplicate tool name" in r.message for r in caplog.records)


class TestToolRegistryInvalidInputSchema:
    def test_schema_with_ref_skipped_others_unaffected(self, monkeypatch, caplog):
        bad_schema = {
            "type": "object",
            "properties": {"field": {"$ref": "#/definitions/SomeType"}},
        }
        bad_tool = _make_tool("bad_schema_tool", input_schema=bad_schema)
        good_tool = _make_tool("good_tool")

        registry = build_registry_with_modules(
            monkeypatch,
            {
                "bad_module": {"REGISTER": bad_tool},
                "good_module": {"REGISTER": good_tool},
            },
            pkg_prefix="_fake_tools_schema",
        )

        # bad_tool rejected, good_tool passes
        assert len(registry) == 1
        assert "good_tool" in registry
        assert "bad_schema_tool" not in registry

    def test_schema_with_defs_skipped(self, monkeypatch):
        bad_schema = {
            "type": "object",
            "$defs": {"MyType": {"type": "string"}},
        }
        bad_tool = _make_tool("defs_tool", input_schema=bad_schema)

        registry = build_registry_with_modules(
            monkeypatch,
            {"defs_module": {"REGISTER": bad_tool}},
            pkg_prefix="_fake_tools_defs",
        )
        assert len(registry) == 0


class TestToolRegistryModuleImportException:
    def test_crashing_module_does_not_affect_others(self, monkeypatch):
        """
        Simulate an ImportError-raising module by making importlib.import_module
        raise for the crash module while leaving the good module unaffected.
        """
        good_tool = _make_tool("healthy_tool")
        pkg_name = "_fake_tools_crash"

        # Create package
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = []
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg

        # Create good module in sys.modules so patched import can return it
        good_mod = types.ModuleType(f"{pkg_name}.good_module")
        good_mod.__package__ = pkg_name
        good_mod.REGISTER = good_tool
        sys.modules[f"{pkg_name}.good_module"] = good_mod

        crash_full = f"{pkg_name}.crash_module"
        child_names = [crash_full, f"{pkg_name}.good_module"]

        original_import = importlib.import_module

        def patched_import(name, *args, **kwargs):
            if name == crash_full:
                raise RuntimeError("Simulated import failure")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(importlib, "import_module", patched_import)

        original_iter = pkgutil.iter_modules

        def fake_iter(path, prefix=""):
            if path is pkg.__path__:
                for full in child_names:
                    yield pkgutil.ModuleInfo(None, full, False)
            else:
                yield from original_iter(path, prefix)

        monkeypatch.setattr(pkgutil, "iter_modules", fake_iter)

        registry = ToolRegistry(tools_package=pkg_name)

        # The crashing module is skipped; the good module is loaded
        assert len(registry) == 1
        assert "healthy_tool" in registry

        # cleanup
        sys.modules.pop(pkg_name, None)
        sys.modules.pop(f"{pkg_name}.good_module", None)


class TestToolRegistryAPICompleteness:
    def _make_registry_with_two_tools(self, monkeypatch) -> ToolRegistry:
        tool_a = _make_tool("tool_alpha")
        tool_b = _make_tool("tool_beta")
        return build_registry_with_modules(
            monkeypatch,
            {
                "mod_a": {"REGISTER": tool_a},
                "mod_b": {"REGISTER": tool_b},
            },
            pkg_prefix="_fake_tools_api",
        )

    def test_list_tools_returns_all(self, monkeypatch):
        registry = self._make_registry_with_two_tools(monkeypatch)
        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t.definition.name for t in tools}
        assert names == {"tool_alpha", "tool_beta"}

    def test_list_definitions_returns_tool_definitions(self, monkeypatch):
        registry = self._make_registry_with_two_tools(monkeypatch)
        definitions = registry.list_definitions()
        assert len(definitions) == 2
        assert all(isinstance(d, ToolDefinition) for d in definitions)
        names = {d.name for d in definitions}
        assert names == {"tool_alpha", "tool_beta"}

    def test_names_returns_list_of_strings(self, monkeypatch):
        registry = self._make_registry_with_two_tools(monkeypatch)
        result = registry.names()
        assert isinstance(result, list)
        assert set(result) == {"tool_alpha", "tool_beta"}

    def test_contains_present_name(self, monkeypatch):
        registry = self._make_registry_with_two_tools(monkeypatch)
        assert "tool_alpha" in registry
        assert "tool_beta" in registry

    def test_contains_absent_name(self, monkeypatch):
        registry = self._make_registry_with_two_tools(monkeypatch)
        assert "nonexistent" not in registry

    def test_len_returns_count(self, monkeypatch):
        registry = self._make_registry_with_two_tools(monkeypatch)
        assert len(registry) == 2

    def test_len_empty(self, monkeypatch):
        registry = build_registry_with_modules(
            monkeypatch, {}, pkg_prefix="_fake_tools_len_empty"
        )
        assert len(registry) == 0


class TestToolRegistryUnimportablePackage:
    def test_nonexistent_package_gives_empty_registry(self):
        """Default package doesn't exist yet — should log warning and not crash."""
        # No monkeypatching — the real package path won't exist if tools/ is empty
        # We just call with a clearly nonexistent package name
        registry = ToolRegistry(tools_package="_absolutely_nonexistent_package_xyz")
        assert len(registry) == 0


class TestToolRegistryUnderscorePrefixSkipped:
    def test_underscore_prefixed_module_skipped(self, monkeypatch):
        """
        Modules with underscore prefix (e.g. _wip_tool.py) must be silently skipped
        even when they expose a valid REGISTER constant.
        """
        valid_tool = _make_tool("published_tool")
        wip_tool = _make_tool("wip_tool")

        registry = build_registry_with_modules(
            monkeypatch,
            {
                "published_module": {"REGISTER": valid_tool},
                "_wip_tool": {"REGISTER": wip_tool},         # underscore prefix → skip
                "_experimental_tool": {"REGISTER": wip_tool}, # also underscore → skip
            },
            pkg_prefix="_fake_tools_underscore",
        )

        # Only the non-prefixed module is registered
        assert len(registry) == 1
        assert "published_tool" in registry
        assert "wip_tool" not in registry

    def test_non_underscore_module_not_skipped(self, monkeypatch):
        """Sanity check: normal module name is NOT skipped."""
        tool = _make_tool("normal_tool")
        registry = build_registry_with_modules(
            monkeypatch,
            {"normal_module": {"REGISTER": tool}},
            pkg_prefix="_fake_tools_normal",
        )
        assert len(registry) == 1
        assert "normal_tool" in registry
