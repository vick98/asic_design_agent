# 作者：vick 邮箱：ykun@yk9811.com

"""数据根。优先环境变量 ADF_ROOT，否则为本仓库。"""

import os


def project_root():
    override = os.environ.get("ADF_ROOT", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
