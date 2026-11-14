# 作者：vick 邮箱：ykun@yk9811.com

"""工具输出的结构化诊断抽取。

运行日志整段落盘之外，把机器可读的错误行抽成小清单进运行记录：compile 段是
工具的 file:line 语法/elaboration 错，run 段是 TB_ERROR（带用例名）。清单截断
到上限、总条数另存——列表丢细节，总数不丢规模。闸门失败信息与调试事项直接
引用首条诊断，回修不用重跑工具、也不用翻整段日志找第一处报错。

抽取只做加法：判 pass/fail 仍由 driver parse 与 judge 决定，这里的清单不改判
定，只给回修与调试当入口。匹配不到就返回空清单（总条数 0），不报错。
"""

import re

# 清单上限：诊断是入口不是全集，10 条足够指出第一处错与错误量级。
MAX_ITEMS = 10

# (phase, tool, compiled regex)。顺序即优先级：先编译/elaboration 错，再运行错。
# 各模式都要求行首起配，避免从日志正文或表格里误抽出类似的字样。
# 厂商串按"[Ee]rror"这类写法拼——框架目录禁止出现厂商日志字面量（见
# framework/tests/test_profile.py 的禁用清单），工具方言的原始串只在剖面 drivers 里。
_PATTERNS = (
    # iverilog：demo/rtl/foo.sv:12: error: ...
    ("compile", "iverilog",
     re.compile(r"(?m)^(\S+?\.(?:sv|v|svh|vh)):(\d+):\s+(?:error|warning):\s*(.+?)[ \t]*$")),
    # verilator：%Error 形态（demo/rtl/foo.sv:12: 消息）
    ("compile", "verilator",
     re.compile(r"(?m)^%[Ee]rror:\s+(\S+?\.(?:sv|v|svh|vh)):(\d+):\s*(.+?)[ \t]*$")),
    # 其他工具的通用 file:line 形态：ERROR: demo/rtl/foo.sv:12: ...
    ("compile", "generic",
     re.compile(r"(?m)^(?:ERROR|[Ee]rror):\s+(\S+?\.(?:sv|v|svh|vh)):(\d+):\s*(.+?)[ \t]*$")),
    # 框架 TB 宏：TB_ERROR <用例名> <比对点>（rules/tb.md 的 RESULT/TB_ERROR 口径）
    ("run", "tb",
     re.compile(r"(?m)^TB_ERROR[ \t]+(.+?)[ \t]*$")),
)


def extract(text):
    """从工具输出抽结构化诊断，返回 (条目清单, 总条数)。

    条目是 {"phase", "tool", "file", "line", "msg"}；TB_ERROR 的 file 为空、
    line 为 0，用例名与比对点都在 msg 里。同一行同一段文本只按模式顺序取
    第一个命中的模式，不重复计数。
    """
    text = text or ""
    items = []
    seen_spans = set()
    total = 0
    for phase, tool, pattern in _PATTERNS:
        for matched in pattern.finditer(text):
            span = (matched.start(), matched.end())
            # 不同模式可能命中同一行（如泛型 ERROR 与 iverilog 同行匹配），
            # 按起始位置去重：一行只进一条诊断。
            if any(start <= span[0] < end for start, end in seen_spans):
                continue
            seen_spans.add(span)
            total += 1
            if phase == "run":
                item_file, item_line = "", 0
                msg = matched.group(1)
            else:
                item_file, item_line, msg = matched.group(1), int(matched.group(2)), matched.group(3)
            if len(items) < MAX_ITEMS:
                items.append({
                    "phase": phase, "tool": tool,
                    "file": item_file, "line": item_line, "msg": msg[:300],
                })
    return items, total


def first_note(run):
    """运行记录失败信息里附的首条诊断一句话；没有诊断返回空串。

    形态：`首条诊断（R007，共 3 条）：compile foo.sv:12: syntax error`——
    运行记录号由调用方拼，这里只拼诊断本体。
    """
    items = run.get("diagnostics") or []
    if not items:
        return ""
    head = items[0]
    where = "%s:%s" % (head.get("file") or "", head.get("line") or "") if head.get("file") else ""
    text = ("%s %s" % (where, head.get("msg") or "")).strip()
    total = run.get("diagnostics_total")
    more = "" if total in (None, 1) else "，共 %s 条" % total
    return "首条诊断：%s %s%s" % (head.get("phase") or "", text, more)
