# 作者：vick 邮箱：ykun@yk9811.com

"""Markdown 表格的唯一解析。"""

import re

_SEP = re.compile(r"^\|[\s\-:|]+\|$")


def table_rows(text):
    rows = []
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|") or _SEP.match(s):
            continue
        rows.append([c.strip().strip("`") for c in s.strip("|").split("|")])
    return rows
