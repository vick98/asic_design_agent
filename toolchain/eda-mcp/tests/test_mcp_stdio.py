"""内置 MCP stdio 服务测试：协议握手、tools/list、tools/call、错误码。"""

import io
import json
import os
import sys
import unittest
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from eda_mcp.mcp_stdio import LATEST_PROTOCOL, StdioServer, tool_schema  # noqa: E402


def sample_tool(
    name: str,
    signals: Optional[List[str]] = None,
    cycles: int = 20,
    flag: bool = False,
) -> str:
    """示例工具：带可选参数与默认值。

    :param name: 名称
    """
    return json.dumps({"name": name, "signals": signals, "cycles": cycles, "flag": flag})


def boom() -> str:
    """总是抛错，用于验证 isError。"""
    raise RuntimeError("炸了")


class TestSchema(unittest.TestCase):
    def test_types_defaults_and_required(self):
        schema = tool_schema(sample_tool)
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["required"], ["name"])
        self.assertEqual(schema["properties"]["name"], {"type": "string"})
        self.assertEqual(schema["properties"]["signals"]["type"], "array")
        self.assertEqual(schema["properties"]["signals"]["items"], {"type": "string"})
        self.assertEqual(schema["properties"]["cycles"], {"type": "integer", "default": 20})
        self.assertEqual(schema["properties"]["flag"], {"type": "boolean", "default": False})


class TestProtocol(unittest.TestCase):
    def setUp(self):
        self.srv = StdioServer("eda-mcp", "9.9.9")
        self.srv.add_tool(sample_tool)
        self.srv.add_tool(boom)

    def _call(self, method, mid, params=None):
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        return self.srv.handle(msg)

    def test_initialize_echoes_protocol(self):
        r = self._call(
            "initialize",
            1,
            {"protocolVersion": LATEST_PROTOCOL, "capabilities": {}, "clientInfo": {}},
        )
        self.assertEqual(r["result"]["protocolVersion"], LATEST_PROTOCOL)
        self.assertEqual(r["result"]["serverInfo"]["name"], "eda-mcp")
        self.assertIn("tools", r["result"]["capabilities"])

    def test_initialize_unknown_protocol_falls_back(self):
        r = self._call("initialize", 1, {"protocolVersion": "1999-01-01"})
        self.assertEqual(r["result"]["protocolVersion"], LATEST_PROTOCOL)

    def test_notification_gets_no_reply(self):
        self.assertIsNone(
            self.srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )

    def test_tools_list(self):
        r = self._call("tools/list", 2)
        names = [t["name"] for t in r["result"]["tools"]]
        self.assertEqual(names, ["boom", "sample_tool"])
        self.assertTrue(all("inputSchema" in t for t in r["result"]["tools"]))

    def test_tools_call_ok(self):
        r = self._call("tools/call", 3, {"name": "sample_tool", "arguments": {"name": "x"}})
        payload = json.loads(r["result"]["content"][0]["text"])
        self.assertEqual(payload["name"], "x")
        self.assertEqual(payload["cycles"], 20)
        self.assertFalse(r["result"]["isError"])

    def test_tools_call_bad_arguments(self):
        r = self._call("tools/call", 3, {"name": "sample_tool", "arguments": {"nope": 1}})
        self.assertTrue(r["result"]["isError"])

    def test_tools_call_tool_error_is_reported_not_raised(self):
        r = self._call("tools/call", 3, {"name": "boom", "arguments": {}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("炸了", r["result"]["content"][0]["text"])

    def test_tools_call_unknown_tool(self):
        r = self._call("tools/call", 3, {"name": "nope", "arguments": {}})
        self.assertTrue(r["result"]["isError"])

    def test_unknown_method(self):
        r = self._call("no/such", 4)
        self.assertEqual(r["error"]["code"], -32601)

    def test_ping_and_empty_lists(self):
        self.assertEqual(self._call("ping", 5)["result"], {})
        self.assertEqual(self._call("resources/list", 6)["result"], {"resources": []})
        self.assertEqual(self._call("prompts/list", 7)["result"], {"prompts": []})

    def test_serve_forever_handles_bad_json_and_eof(self):
        stdin = io.StringIO(
            "\n"
            "not json\n"
            '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        )
        stdout = io.StringIO()
        self.assertEqual(self.srv.serve_forever(stdin, stdout), 0)
        lines = [json.loads(x) for x in stdout.getvalue().splitlines()]
        self.assertEqual(lines[0]["error"]["code"], -32700)
        self.assertIn("tools", lines[1]["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
