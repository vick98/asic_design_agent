"""eda-mcp —— EDA 工具链的 MCP 服务。

独立包：不依赖工作区内的任何路径，可迁移到任意 EDA 服务器。
核心波形通路（FFR/FSDB）只依赖包内编译的 ``fsdbq`` 与 Python 3 标准库。
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
