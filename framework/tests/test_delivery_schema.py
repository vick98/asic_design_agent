# 作者：vick 邮箱：ykun@yk9811.com

"""交付 IR 的 JSON 契约与 ircheck 的必填字段常量必须同源。

`framework/delivery_schema.json` 是给外部交付方看的说明性契约；
实际校验在 `framework/ircheck.py`。两边字段一旦漂移，这个用例失败。
"""

import json
import os
import unittest

import framework.ircheck as ircheck
from framework.tests.util import RepoTest, checkout_root


class DeliverySchemaTests(RepoTest):
    def _schema(self):
        path = os.path.join(checkout_root(), "framework", "delivery_schema.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_required_fields_match_ircheck(self):
        schema = self._schema()
        self.assertEqual(tuple(schema["required"]), ircheck.REQUIRED_TOP)
        self.assertEqual(tuple(schema["module_required"]), ircheck.REQUIRED_MODULE)
        self.assertEqual(tuple(schema["port_required"]), ircheck.REQUIRED_PORT)
        self.assertEqual(tuple(schema["memory_required"]), ircheck.REQUIRED_MEMORY)

    def test_schema_has_title_and_notes(self):
        schema = self._schema()
        self.assertTrue(schema.get("title"))
        self.assertTrue(schema.get("notes"))


if __name__ == "__main__":
    unittest.main()
