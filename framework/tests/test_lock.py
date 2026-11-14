# 作者：vick 邮箱：ykun@yk9811.com

"""写权限台账（文件锁）的行为测试。

台账是**协调机制，不是强制机制**：主持者授予/续期/撤销，成员写前自查。
这里钉住的是可观察行为：

- 授予后文件与目录前缀都能命中；只授予一个文件不覆盖整个目录；
- 与他人有效条目相交即拒绝，并在报错里点名持有者与任务（主持者据此排队协调）；
- 超时即自动释放、条目被清掉，登记表里不留残渣；要继续写必须重新申请；
- 登记表只有一份文件，授予多次也不积累文件；
- 命令行面的退出码：check 命中 0、未命中 1、冲突 1。
"""

import json
import os
import shutil
import time
import unittest

from framework.locks import (
    LockError, cancel, check, grant, listing, normalize, overlaps, registry_path, renew,
    request, revoke, waiting,
)

from .util import RepoTest, cli

SHORT_TTL = 0.02          # 约 1.2 秒
SHORT_WAIT = 1.4


class LockLedgerTests(RepoTest):
    def setUp(self):
        shutil.rmtree(os.path.join(self.root, "locks"), ignore_errors=True)

    def test_grant_covers_directory_prefix_and_single_file(self):
        grant(self.root, "甲", "行7", ["rtl/", "spec_doc/x_spec.md"],
              note="行 7 逐模块收敛")
        self.assertTrue(check(self.root, "甲", "rtl/a.sv")[0])
        self.assertTrue(check(self.root, "甲", "rtl/sub/b.sv")[0])
        self.assertTrue(check(self.root, "甲", "spec_doc/x_spec.md")[0])
        allowed, why = check(self.root, "甲", "rules/team.md")
        self.assertFalse(allowed)
        self.assertIn("不含", why)

    def test_single_file_grant_does_not_cover_the_whole_directory(self):
        grant(self.root, "甲", "行7", ["rtl/a.sv"])
        self.assertTrue(check(self.root, "甲", "rtl/a.sv")[0])
        self.assertFalse(check(self.root, "甲", "rtl/")[0])
        self.assertFalse(check(self.root, "甲", "rtl/b.sv")[0])

    def test_conflict_with_another_member_is_rejected_with_holder_named(self):
        grant(self.root, "甲", "行7-RTL", ["rtl/"])
        with self.assertRaises(LockError) as ctx:
            grant(self.root, "乙", "行8-顶层", ["rtl/demo_top.sv"])
        message = str(ctx.exception)
        self.assertIn("路径冲突", message)
        self.assertIn("甲", message)
        self.assertIn("行7-RTL", message)

    def test_same_member_accumulates_paths_and_keeps_every_task_name(self):
        grant(self.root, "甲", "行7", ["rtl/"])
        row = grant(self.root, "甲", "行8", ["testbench/"])
        self.assertEqual(row["tasks"], ["行7", "行8"])
        self.assertEqual(row["paths"], ["rtl/", "testbench/"])

    def test_expired_entry_is_released_and_leaves_no_residue(self):
        grant(self.root, "甲", "行7", ["rtl/"], ttl_minutes=SHORT_TTL)
        time.sleep(SHORT_WAIT)
        rows, dropped = listing(self.root)
        self.assertEqual(rows, [])
        self.assertEqual([item["member"] for item in dropped], ["甲"])
        self.assertFalse(check(self.root, "甲", "rtl/a.sv")[0])
        with open(registry_path(self.root), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["locks"], [])

    def test_renew_extends_ttl_and_expired_entry_must_be_requested_again(self):
        grant(self.root, "甲", "行7", ["rtl/"])
        row = renew(self.root, "甲", 5)
        self.assertEqual(row["ttl_minutes"], 5.0)
        grant(self.root, "乙", "行8", ["testbench/"], ttl_minutes=SHORT_TTL)
        time.sleep(SHORT_WAIT)
        with self.assertRaises(LockError) as ctx:
            renew(self.root, "乙")
        self.assertIn("没有有效写权限", str(ctx.exception))

    def test_revoke_narrows_one_path_then_drops_the_entry(self):
        grant(self.root, "甲", "行7", ["rtl/", "spec_doc/"])
        revoke(self.root, "甲", "rtl/")
        self.assertFalse(check(self.root, "甲", "rtl/a.sv")[0])
        self.assertTrue(check(self.root, "甲", "spec_doc/x_spec.md")[0])
        revoke(self.root, "甲")
        self.assertFalse(check(self.root, "甲", "spec_doc/x_spec.md")[0])

    def test_registry_stays_a_single_file(self):
        for index in range(5):
            grant(self.root, "成员%d" % index, "任务%d" % index, ["mod%d/" % index])
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "locks"))),
                         ["registry.json"])

    def test_normalize_and_overlap_edges(self):
        self.assertEqual(normalize(self.root, "rules"), "rules/")
        self.assertEqual(normalize(self.root, "./rtl/a.sv"), "rtl/a.sv")
        self.assertTrue(overlaps("rtl/", "rtl/a.sv"))
        self.assertTrue(overlaps("rtl/", "rtl/sub/"))
        self.assertFalse(overlaps("rtl/a.sv", "rtl/b.sv"))
        with self.assertRaises(LockError):
            normalize(self.root, "../outside.md")


class LockCliTests(RepoTest):
    """命令行面用真进程验：退出码与 stderr 是真结论。"""

    def setUp(self):
        shutil.rmtree(os.path.join(self.root, "locks"), ignore_errors=True)

    def test_grant_check_conflict_exit_codes(self):
        granted = cli(self.root, "lock", "grant", "--to", "甲", "--task", "行7",
                      "--paths", "rtl/", "--ttl", "60")
        self.assertEqual(granted.returncode, 0, granted.stderr)

        hit = cli(self.root, "lock", "check", "--to", "甲", "--path", "rtl/a.sv")
        self.assertEqual(hit.returncode, 0, hit.stderr)
        self.assertIn("已授予", hit.stdout)

        miss = cli(self.root, "lock", "check", "--to", "甲", "--path", "rules/team.md")
        self.assertEqual(miss.returncode, 1)
        self.assertIn("未授予", miss.stdout)

        clash = cli(self.root, "lock", "grant", "--to", "乙", "--task", "行8",
                    "--paths", "rtl/demo_top.sv")
        self.assertEqual(clash.returncode, 1)
        self.assertIn("路径冲突", clash.stderr)

    def test_list_reports_board_and_auto_release(self):
        cli(self.root, "lock", "grant", "--to", "甲", "--task", "行7",
            "--paths", "rtl/", "--ttl", "60")
        out = cli(self.root, "lock", "list")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("甲", out.stdout)
        self.assertIn("rtl/", out.stdout)

        cli(self.root, "lock", "grant", "--to", "乙", "--task", "行8",
            "--paths", "testbench/", "--ttl", str(SHORT_TTL))
        time.sleep(SHORT_WAIT)
        expired = cli(self.root, "lock", "list")
        self.assertEqual(expired.returncode, 0, expired.stderr)
        self.assertIn("已自动释放", expired.stdout)
        self.assertIn("乙", expired.stdout)

    def test_revoked_member_must_ask_again(self):
        cli(self.root, "lock", "grant", "--to", "甲", "--task", "行7", "--paths", "rtl/")
        gone = cli(self.root, "lock", "revoke", "--to", "甲")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        after = cli(self.root, "lock", "check", "--to", "甲", "--path", "rtl/a.sv")
        self.assertEqual(after.returncode, 1)

    def test_broken_registry_is_reported_not_crashed(self):
        os.makedirs(os.path.join(self.root, "locks"), exist_ok=True)
        with open(registry_path(self.root), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        out = cli(self.root, "lock", "list")
        self.assertEqual(out.returncode, 1)
        self.assertIn("不是合法 JSON", out.stderr)


class LockQueueTests(RepoTest):
    """等待队列：成员排队申请、主持者按先后授予，队列标出被谁挡住。"""

    def setUp(self):
        shutil.rmtree(os.path.join(self.root, "locks"), ignore_errors=True)

    def test_request_only_queues_and_does_not_grant(self):
        request(self.root, "乙", "行8", ["testbench/"])
        self.assertFalse(check(self.root, "乙", "testbench/a.sv")[0])
        rows, _ = waiting(self.root)
        self.assertEqual([row["member"] for row in rows], ["乙"])
        self.assertEqual(rows[0]["blocked_by"], [])

    def test_queue_order_is_first_request_first_served(self):
        request(self.root, "乙", "行8", ["rtl/"])
        time.sleep(0.01)
        request(self.root, "丙", "行9", ["rtl/"])
        rows, _ = waiting(self.root)
        self.assertEqual([row["member"] for row in rows], ["乙", "丙"])

    def test_grant_consumes_the_pending_request(self):
        request(self.root, "乙", "行8", ["testbench/"])
        grant(self.root, "乙", "行8", ["testbench/"])
        self.assertEqual(waiting(self.root)[0], [])
        self.assertTrue(check(self.root, "乙", "testbench/a.sv")[0])

    def test_request_while_already_holding_is_rejected(self):
        grant(self.root, "甲", "行7", ["rtl/"])
        with self.assertRaises(LockError) as ctx:
            request(self.root, "甲", "行7", ["rtl/a.sv"])
        self.assertIn("不必排队", str(ctx.exception))

    def test_cancel_removes_the_queue_entry(self):
        request(self.root, "乙", "行8", ["rtl/"])
        cancel(self.root, "乙")
        self.assertEqual(waiting(self.root)[0], [])

    def test_waiting_names_the_blocking_holder_and_clears_after_release(self):
        grant(self.root, "甲", "行7-RTL", ["rtl/"])
        request(self.root, "乙", "行8", ["rtl/demo_top.sv"])
        self.assertEqual(waiting(self.root)[0][0]["blocked_by"], ["甲"])
        revoke(self.root, "甲")
        self.assertEqual(waiting(self.root)[0][0]["blocked_by"], [])

    def test_accumulated_paths_keep_the_original_queue_position(self):
        request(self.root, "乙", "行8", ["rtl/"])
        time.sleep(0.01)
        request(self.root, "丙", "行9", ["rules/"])
        request(self.root, "乙", "行8", ["spec_doc/"])
        rows, _ = waiting(self.root)
        self.assertEqual([row["member"] for row in rows], ["乙", "丙"])
        self.assertEqual(rows[0]["paths"], ["rtl/", "spec_doc/"])

    def test_cli_request_then_list_shows_queue_and_blocking_holder(self):
        cli(self.root, "lock", "grant", "--to", "甲", "--task", "行7", "--paths", "rtl/")
        queued = cli(self.root, "lock", "request", "--to", "乙", "--task", "行8",
                     "--paths", "rtl/demo_top.sv")
        self.assertEqual(queued.returncode, 0, queued.stderr)
        out = cli(self.root, "lock", "list")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("等待队列", out.stdout)
        self.assertIn("等 甲", out.stdout)

        free = cli(self.root, "lock", "request", "--to", "丙", "--task", "行9",
                   "--paths", "testbench/")
        self.assertEqual(free.returncode, 0, free.stderr)
        self.assertIn("可立即授予", cli(self.root, "lock", "list").stdout)

        gone = cli(self.root, "lock", "cancel", "--to", "乙")
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertNotIn("等 甲", cli(self.root, "lock", "list").stdout)


if __name__ == "__main__":
    unittest.main()
