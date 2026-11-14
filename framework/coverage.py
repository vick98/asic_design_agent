# 作者：vick 邮箱：ykun@yk9811.com

"""覆盖率阈值与 cov_gate.txt 的规则。

生效顺序：框架默认 → 剖面 `coverage_defaults` → 子系统 `testbench/cov_gate.txt`。
`cov_gate.txt` 只能上调；下调的每一项都要有规则号 `COV`、指向已入库裁决的豁免，
否则该次覆盖率判 fail。
"""

import os

DEFAULTS = {"line": 80.0, "cond": 70.0, "fsm": 80.0, "tgl": 60.0}


def profile_limits(profile):
    merged = dict(DEFAULTS)
    merged.update((profile or {}).get("coverage_defaults") or {})
    return merged


def gate_overrides(sys_root):
    """读 testbench/cov_gate.txt。"""
    out = {}
    if not sys_root:
        return out
    path = os.path.join(sys_root, "testbench", "cov_gate.txt")
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text or text.startswith("#") or "=" not in text:
                continue
            key, value = text.split("=", 1)
            key = key.strip().lower()
            try:
                out[key] = float(value.strip().rstrip("%"))
            except ValueError as exc:
                del exc
                continue
    return out


def _waived(key, waivers):
    for item in waivers or []:
        if str(item.get("rule")) != "COV":
            continue
        where = str(item.get("where") or "")
        if where in (key, "*", ""):
            return True
    return False


def audit(profile, sys_root="", waivers=None):
    """返回 (生效阈值, 未豁免的下调项)。"""
    base = profile_limits(profile)
    effective = dict(base)
    unwaived = []
    for key, value in sorted(gate_overrides(sys_root).items()):
        if key not in base:
            continue
        if value < base[key]:
            if _waived(key, waivers):
                effective[key] = value
            else:
                unwaived.append((key, value, base[key]))
        else:
            effective[key] = value
    return effective, unwaived


def limits(profile, sys_root="", waivers=None):
    """生效阈值。未豁免的下调项不生效，按默认值继续判。"""
    return audit(profile, sys_root=sys_root, waivers=waivers)[0]
