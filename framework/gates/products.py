# 作者：vick 邮箱：ykun@yk9811.com

"""子系统产物文件的唯一列表。docs、numeric 与 marks 都从这里取。

`info_input/` 下只认 `<sys>_info_overview.md`，其余原始资料是输入原文，闸门不检查。
"""

import os

DOC_FOLDERS = ("info_input", "flow_doc", "plan_doc", "spec_doc")
SKIP_SUFFIX = ("_status.md", "_decision.md", "_signoff.md")


def sys_name_of(sys_root):
    return os.path.basename(os.path.abspath(sys_root).rstrip(os.sep))


def doc_paths(sys_root):
    """返回 {相对路径: 绝对路径}，只含要进闸门的 Markdown 产物。"""
    name = sys_name_of(sys_root)
    overview = "info_input/%s_info_overview.md" % name
    found = {}
    for folder in DOC_FOLDERS:
        base = os.path.join(sys_root, folder)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, files in os.walk(base):
            dirnames[:] = sorted(item for item in dirnames if item != "__pycache__")
            for fn in sorted(files):
                if not fn.endswith(".md") or fn.endswith(SKIP_SUFFIX):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), sys_root).replace(os.sep, "/")
                if folder == "info_input" and rel != overview:
                    continue
                found[rel] = os.path.join(dirpath, fn)
    return found


def doc_texts(sys_root):
    """返回 {相对路径: 正文}。"""
    out = {}
    for rel, path in doc_paths(sys_root).items():
        with open(path, encoding="utf-8", errors="replace") as fh:
            out[rel] = fh.read()
    return out
