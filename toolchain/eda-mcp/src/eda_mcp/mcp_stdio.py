"""零依赖的最小 MCP stdio 服务实现。

**为什么需要它**：EDA 服务器常常既没有 pip / ensurepip，也不能联网。官方
`mcp` SDK 会拖进 pydantic-core / starlette / uvicorn 等约 30 MB 依赖（还含
平台相关的 .so），在 air-gap 机器上很难落地。而 MCP 的 stdio 传输本身只是
**逐行 JSON-RPC 2.0**，用标准库实现约 200 行即可。

本模块实现 MCP 的 stdio 子集：

* ``initialize`` / ``notifications/initialized`` / ``ping``
* ``tools/list`` / ``tools/call``
* ``resources/list`` / ``prompts/list``（返回空，声明本服务不提供）

已装官方 SDK 时 :mod:`eda_mcp.server` 会优先用 SDK（并因此支持 HTTP 传输）；
未装则自动回落到本实现。
"""

from __future__ import annotations

import inspect
import json
import sys
import traceback
import typing
from typing import Any, Callable, Dict, List, Optional

__all__ = ["StdioServer", "tool_schema", "LATEST_PROTOCOL"]

LATEST_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = (
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)

_JSON_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _json_type(ann: Any) -> Dict[str, Any]:
    """把 Python 注解映射成 JSON Schema 片段。"""
    if ann is inspect.Parameter.empty or ann is Any:
        return {}
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)

    if origin is typing.Union:  # Optional[T] / Union[T, None]
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _json_type(non_none[0])
        return {}
    if origin in (list, List):
        item = _json_type(args[0]) if args else {}
        return {"type": "array", "items": item or {}}
    if origin is dict:
        return {"type": "object"}
    if ann in _JSON_TYPES:
        return {"type": _JSON_TYPES[ann]}
    if isinstance(ann, type):
        for py, js in _JSON_TYPES.items():
            if issubclass(ann, py):
                return {"type": js}
    return {}


def tool_schema(fn: Callable[..., Any]) -> Dict[str, Any]:
    """由函数签名 + docstring 生成 MCP ``inputSchema``。"""
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001 - 注解可解析失败时退化为宽松 schema
        hints = {}

    props: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        ann = hints.get(name, param.annotation)
        schema = _json_type(ann)
        if param.default is not inspect.Parameter.empty:
            if param.default is not None:
                schema = dict(schema, default=param.default)
        else:
            required.append(name)
        props[name] = schema

    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _describe(fn: Callable[..., Any]) -> str:
    doc = inspect.getdoc(fn) or ""
    if not doc:
        return fn.__name__
    lines = [ln.strip() for ln in doc.splitlines()]
    # 第一段（到空行为止）作为说明；跳过纯签名行
    out: List[str] = []
    for ln in lines:
        if not ln and out:
            break
        if ln.startswith((":param", ":return", "Args:", "Returns:", "参数", "返回")):
            break
        out.append(ln)
    return " ".join(out).strip() or fn.__name__


class StdioServer:
    """最小 MCP 服务端（逐行 JSON-RPC 2.0 over stdio）。"""

    def __init__(self, name: str = "eda-mcp", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self._tools: Dict[str, Callable[..., Any]] = {}
        self.protocol = LATEST_PROTOCOL

    # ---- 注册 ----
    def tool(self, fn: Optional[Callable[..., Any]] = None):
        """``@srv.tool`` / ``@srv.tool()`` / ``srv.tool(fn)`` 三种写法都支持。"""
        if fn is None:
            return self
        if not callable(fn):
            raise TypeError("tool() 需要可调用对象")
        self._tools[fn.__name__] = fn
        return fn

    def add_tool(self, fn: Callable[..., Any]) -> None:
        self._tools[fn.__name__] = fn

    # ---- 协议 ----
    def _tools_list(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "description": _describe(fn),
                "inputSchema": tool_schema(fn),
            }
            for name, fn in sorted(self._tools.items())
        ]

    def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        fn = self._tools.get(name)
        if fn is None:
            return {
                "content": [{"type": "text", "text": "未知工具: %s" % name}],
                "isError": True,
            }
        try:
            result = fn(**(arguments or {}))
        except TypeError as exc:
            return {
                "content": [{"type": "text", "text": "参数错误: %s" % exc}],
                "isError": True,
            }
        except Exception as exc:  # noqa: BLE001 - 工具错误要回给客户端而不是崩服务
            detail = traceback.format_exc() if _debug() else "%s: %s" % (type(exc).__name__, exc)
            return {"content": [{"type": "text", "text": detail}], "isError": True}
        if isinstance(result, str):
            text = result
        else:
            text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def handle(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理一条 JSON-RPC 消息；返回 None 表示这是通知、不应答。"""
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}

        if mid is None and method is not None:
            # 通知：initialized / cancelled / progress 等一律静默
            if method == "notifications/initialized":
                pass
            return None

        if method == "initialize":
            want = params.get("protocolVersion")
            self.protocol = want if want in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL
            return _ok(
                mid,
                {
                    "protocolVersion": self.protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": self.version},
                    "instructions": (
                        "EDA 工具链服务：Verdi NPI 设计查询 / FSDB 波形（FFR，无需 Verdi·License·X）"
                        "/ WaveDrom 时序图 / VCS 仿真 / DC·PT。"
                    ),
                },
            )
        if method == "ping":
            return _ok(mid, {})
        if method == "tools/list":
            return _ok(mid, {"tools": self._tools_list()})
        if method == "tools/call":
            name = params.get("name") or ""
            return _ok(mid, self._call_tool(name, params.get("arguments") or {}))
        if method == "resources/list":
            return _ok(mid, {"resources": []})
        if method == "resources/templates/list":
            return _ok(mid, {"resourceTemplates": []})
        if method == "prompts/list":
            return _ok(mid, {"prompts": []})
        if method == "logging/setLevel":
            return _ok(mid, {})
        return _err(mid, -32601, "Method not found: %s" % method)

    # ---- 主循环 ----
    def run(self, transport: str = "stdio", **kwargs: Any) -> int:
        """与官方 SDK 对齐的入口（内置实现只支持 stdio）。"""
        if transport not in ("stdio",):
            raise ValueError("内置零依赖实现只支持 stdio，收到: %s" % transport)
        return self.serve_forever()

    def serve_forever(self, stdin=None, stdout=None) -> int:
        fin = stdin if stdin is not None else sys.stdin
        fout = stdout if stdout is not None else sys.stdout
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                _write(fout, _err(None, -32700, "Parse error"))
                continue
            try:
                reply = self.handle(msg)
            except Exception as exc:  # noqa: BLE001
                reply = _err(msg.get("id"), -32603, "Internal error: %s" % exc)
            if reply is not None:
                _write(fout, reply)
        return 0


def _debug() -> bool:
    import os

    return bool(os.environ.get("EDA_MCP_DEBUG"))


def _ok(mid: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _write(fout, payload: Dict[str, Any]) -> None:
    # MCP stdio：每条消息一行，且不得含内嵌换行
    fout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    fout.flush()
