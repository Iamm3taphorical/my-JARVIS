from __future__ import annotations

from typing import Any

from modules.tools.registry import LocalToolRegistry


class CommandRouter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.registry = LocalToolRegistry(config)

    def handle(self, text: str) -> str | None:
        return self.registry.handle(text)

    def describe_tools(self) -> str:
        return self.registry.describe()
