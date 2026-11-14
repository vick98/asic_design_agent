#!/usr/bin/env python3
"""NPI 设计模型真机冒烟（需在 EDA 服务器上运行，会拉起 Verdi 温进程）。

用法::

    PYTHONPATH=src python3 tests/integration/npi_smoke.py [设计文件...]

不带参数时默认用 pub_code/pubip_counter.v（工作区镜像内）。
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))

from eda_mcp.config import load as load_config  # noqa: E402
from eda_mcp.npi import connect  # noqa: E402

DEFAULT = "/path/to/workspace/pub_code/pubip_counter.v"


def main(argv):
    files = argv[1:] or [DEFAULT]
    for f in files:
        if not os.path.isfile(f):
            print("ERR: 设计文件不存在: %s" % f)
            return 2

    cfg = load_config()
    design_id = os.path.splitext(os.path.basename(files[0]))[0]
    print("== 连接/启动 daemon（设计 %s）==" % design_id)
    t0 = time.time()
    cli = connect(design_id, cfg=cfg, files=files, sv=True)
    print("   启动耗时 %.1f s，daemon pid=%s，display=%s" % (
        time.time() - t0, cli.daemon.pid(), cli.daemon.info().display))

    t1 = time.time()
    print("== ping ==", cli.ping(), "(%.3f s)" % (time.time() - t1))

    t1 = time.time()
    nodes = cli.hierarchy()
    print("== hierarchy: %d 个层次 (%.3f s) ==" % (len(nodes), time.time() - t1))
    for n in nodes[:12]:
        print("   %s%s  (%s) @%s:%s" % ("  " * n.depth, n.full, n.def_name,
                                        os.path.basename(n.file), n.line))

    for path in ("%s.reg_counter" % design_id, "%s.o_cnt_shift" % design_id,
                 "%s.clk_in" % design_id, "%s.MAX_NUM" % design_id):
        t1 = time.time()
        try:
            o = cli.object(path)
            print("== object %s (%.3f s) ==" % (path, time.time() - t1))
            print("   type=%s width=%s [%s:%s] dir=%s net=%s @%s:%s" % (
                o.type, o.width, o.left, o.right, o.direction or "-",
                o.net_type or "-", os.path.basename(o.file), o.line))
            print("   src: %s" % o.source)
        except Exception as exc:  # noqa: BLE001
            print("== object %s 失败: %s" % (path, exc))

    t1 = time.time()
    mod = cli.module(design_id)
    print("== module %s (%.3f s) counts=%s ==" % (design_id, time.time() - t1, mod["counts"]))
    for p in mod["ports"]:
        print("   port %-18s w=%-3s %s" % (p["name"], p["width"], p["direction"]))

    t1 = time.time()
    hits = cli.trace("%s.reg_counter" % design_id, "both")
    print("== trace reg_counter (%.3f s): %d 条 ==" % (time.time() - t1, len(hits)))
    for h in hits[:14]:
        print("   %-7s %-14s %s" % (h.direction, h.type, h.full))

    t1 = time.time()
    found = cli.find("*cnt*", limit=20)
    print("== find *cnt* (%.3f s): %d 条 ==" % (time.time() - t1, len(found)))
    for o in found[:8]:
        print("   %-45s w=%-3s %s" % (o.full, o.width, o.type))

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
