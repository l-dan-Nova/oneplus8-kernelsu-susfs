#!/usr/bin/env python3
"""让自编译内核能加载原厂 vendor .ko（OnePlus 8T OOS11 / 4.19 non-GKI）。

背景：原厂 .ko 的 vermagic 带 "modversions" token，只有内核 CONFIG_MODVERSIONS=y
时内核自身 vermagic 才带同一 token、same_magic() 才能逐字匹配，所以 MODVERSIONS 必须保留。
但原厂 .ko 的符号 CRC 由原厂构建的 genksyms 生成，本次自编译若个别 CRC 不一致，
check_version() 命中 bad_version 会 return 0 拒绝加载。本脚本把该拒绝改成放行(return 1)
并保留 pr_warn 告警；模块签名问题另由 Configure 关闭 MODULE_SIG_FORCE/MODULE_SIG 解决。

用法: python3 patch_module_crc.py <kernel_source_dir>
  <kernel_source_dir> 为内核源码根（含 kernel/module.c 的上一级，即 CI 里 cd kernel 后的 pwd）。
幂等：已打过补丁则直接报 OK；锚点异常则非零退出，让 CI 早失败。
"""
import sys
import pathlib

OLD = (
    "bad_version:\n"
    '\tpr_warn("%s: disagrees about version of symbol %s\\n",\n'
    "\t       info->name, symname);\n"
    "\treturn 0;\n"
)
NEW = (
    "bad_version:\n"
    '\tpr_warn("%s: disagrees about version of symbol %s (tolerated)\\n",\n'
    "\t       info->name, symname);\n"
    "\treturn 1; /* KSU build: tolerate vendor .ko CRC mismatch */\n"
)
MARK = "tolerate vendor .ko CRC mismatch"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: patch_module_crc.py <kernel_source_dir>")
    kd = pathlib.Path(sys.argv[1])
    p = kd / "kernel" / "module.c"
    if not p.exists():
        sys.exit(f"FATAL: not found: {p}")
    s = p.read_text()
    if MARK in s:
        print("already patched, skip:", p)
        return
    n = s.count(OLD)
    if n != 1:
        sys.exit(f"FATAL: bad_version anchor count={n}, expected 1 in {p}")
    p.write_text(s.replace(OLD, NEW))
    print("patched check_version bad_version -> return 1 (tolerate CRC):", p)


if __name__ == "__main__":
    main()
