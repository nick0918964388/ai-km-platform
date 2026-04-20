"""
Tool registry with auto-discovery.

Each tool module in `tools/` directory must expose a module-level `REGISTER` constant
pointing to an instance of that tool. Registry imports all modules once at init
and collects these instances.

Example tool module:
    # tools/get_vehicle_info.py
    class GetVehicleInfoTool(Tool):
        definition = ToolDefinition(name="get_vehicle_info", ...)
        async def execute(self, params, user_ctx): ...

    REGISTER = GetVehicleInfoTool()
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

from app.services.maximo_tools.base import Tool, ToolDefinition, validate_tool_schema

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Auto-discover tools in a given Python package.
    Thread-safe after init (read-only lookups).
    """

    def __init__(self, tools_package: str = "app.services.maximo_tools.tools"):
        self._tools: dict[str, Tool] = {}
        self._load(tools_package)

    def _load(self, package_name: str) -> None:
        """Import every module in the package and collect REGISTER constants."""
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.warning("Tool package %s not importable yet: %s", package_name, e)
            return

        if not hasattr(package, "__path__"):
            # not a package, cannot iterate
            return

        for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}."):
            module_name = module_info.name
            # Skip underscore-prefixed modules (WIP / private / experimental)
            simple_name = module_name.rsplit(".", 1)[-1]
            if simple_name.startswith("_"):
                logger.debug("Skipping private module: %s", module_name)
                continue
            try:
                module = importlib.import_module(module_name)
            except Exception:
                logger.exception("Failed to import tool module %s", module_name)
                continue

            register = getattr(module, "REGISTER", None)
            if register is None:
                continue

            if not isinstance(register, Tool):
                logger.warning(
                    "Module %s.REGISTER is not a Tool instance (got %r), skipping",
                    module_name,
                    type(register),
                )
                continue

            name = register.definition.name
            if name in self._tools:
                logger.error(
                    "Duplicate tool name '%s' in %s; keeping first registration",
                    name,
                    module_name,
                )
                continue

            try:
                validate_tool_schema(register.definition.input_schema)
            except ValueError:
                logger.exception(
                    "Tool '%s' in %s has invalid input_schema (not flat), skipping",
                    name,
                    module_name,
                )
                continue

            self._tools[name] = register
            logger.info("Registered tool: %s", name)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def list_definitions(self) -> list[ToolDefinition]:
        """For sending to Anthropic tool_use API."""
        return [t.definition for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
