# 作者：vick 邮箱：ykun@yk9811.com

"""交付 IR 的最小结构校验。只使用标准库。"""

REQUIRED_TOP = (
    "schema_version", "sys_name", "ports", "memory", "modules",
    "module_details", "flow_nodes",
)
REQUIRED_MODULE = (
    "name", "kind", "spec_path", "ports", "connections", "logic_blocks",
    "tests", "memory", "fixed_point",
)
REQUIRED_PORT = ("name", "direction", "width", "clock", "description")
REQUIRED_MEMORY = ("segments", "total_words", "peak_words", "addr_bits")


def validate_ir(data):
    errors = []
    if not isinstance(data, dict):
        return ["根必须是对象"]
    for key in REQUIRED_TOP:
        if key not in data:
            errors.append("缺少 %s" % key)
    memory = data.get("memory")
    if isinstance(memory, dict):
        for key in REQUIRED_MEMORY:
            if key not in memory:
                errors.append("memory 缺少 %s" % key)
    for item in data.get("module_details") or []:
        if not isinstance(item, dict):
            errors.append("module_details 项必须是对象")
            continue
        for key in REQUIRED_MODULE:
            if key not in item:
                errors.append("%s 缺少 %s" % (item.get("name"), key))
        for port in item.get("ports") or []:
            for key in REQUIRED_PORT:
                if key not in port:
                    errors.append("端口 %s 缺少 %s" % (port.get("name"), key))
    return errors
