from typing import Callable, Any


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]):
        self._tools[name] = fn

    def call(self, name: str, **kwargs):
        if name not in self._tools:
            raise KeyError(f"tool '{name}' not found")
        return self._tools[name](**kwargs)


registry = ToolRegistry()
