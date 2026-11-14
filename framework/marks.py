# 作者：vick 邮箱：ykun@yk9811.com

"""收割产物里的走查标记（按原文直接入库，不再进 T 队列）。

走查标记（`mark:`、`@@`）是开发者亲手写的输入。收割时直接按原文入库：
来源记 `mark:<文件>:<行>`，类别（方向/数值/记录）由主持者判定，停点决定
D 号的阶段号与级联起点。同一处只算一条——已入库的标记不再重复收割。

收割上限可配置：读 `state["thresholds"]["marks_cap"]`，缺省不限（一次把待收割的
标记全部入库）。上限只是防止一次事务过大，不是口径的一部分。
"""

import re

from framework.engine import EngineError, commit_decision
from framework.state import load_state, sys_dir

MARK = re.compile(r"mark:|@@")


def list_marks(root, name):
    """扫产物文档里的走查标记；同一处只算一条。"""
    from framework.gates.products import doc_paths
    found = []
    base = sys_dir(root, name)
    for rel, path in sorted(doc_paths(base).items()):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for index, line in enumerate(fh, 1):
                if MARK.search(line):
                    found.append("%s:%d %s" % (rel, index, line.strip()))
    return found


def mark_source(line):
    """标记行 → 入库来源串 `mark:<文件>:<行>`。"""
    return "mark:" + line.split(" ", 1)[0]


def mark_text(line):
    """标记行 → 裁决正文：去掉"文件:行"定位前缀与标记本身，保留开发者原话。"""
    body = line.split(" ", 1)[1] if " " in line else line
    return re.sub(r"^(?:mark:|@@)\s*", "", body).strip()


def marks_cap(state):
    """收割上限：`state["thresholds"]["marks_cap"]`，缺省/0/负数表示不限。"""
    value = (state.get("thresholds") or {}).get("marks_cap")
    if value in (None, ""):
        return None
    try:
        cap = int(value)
    except (TypeError, ValueError):
        raise EngineError("thresholds.marks_cap 必须是正整数或留空，收到 %r" % value)
    return cap if cap > 0 else None


def marks_plan(root, name):
    """返回 (待收割, 已收割) 的标记行。已收割 = 已有裁决的 source 指向它。"""
    state = load_state(root, name)
    done = {row.get("source") for rows in state["decisions"].values() for row in rows}
    fresh, known = [], []
    for line in list_marks(root, name):
        (known if mark_source(line) in done else fresh).append(line)
    return fresh, known


def harvest_marks(root, name, kind, stop, cap=None):
    """按原文直接入库，返回 [(D号, 标记行)]；一次最多 cap 条。

    cap 缺省读 state 的 thresholds.marks_cap，缺省不限。传 cap=<int> 可覆盖
    （测试/调用方显式限流用）。
    """
    state = load_state(root, name)
    if cap is None:
        cap = marks_cap(state)
    fresh, _known = marks_plan(root, name)
    lines = fresh if cap is None else fresh[:cap]
    out = []
    for line in lines:
        did = commit_decision(root, name, content=mark_text(line), kind=kind,
                              source=mark_source(line), stop=int(stop), pick="mark")
        out.append((did, line))
    return out
