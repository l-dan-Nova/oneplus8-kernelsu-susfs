#!/usr/bin/env python3
# Backport stpcpy into a 4.19 vendor kernel that lacks it.
# clang lowers chained strcpy/sprintf into stpcpy calls (GCC does not), and the
# OnePlus SM8250 R_11 lib/string.c + linux/string.h have no stpcpy, which makes
# the final link fail with: ld.lld/bfd: undefined symbol: stpcpy.
# Idempotent: re-running changes nothing. CWD must be the kernel source root.
import io, os, sys

IMPL = """#ifndef __HAVE_ARCH_STPCPY
/**
 * stpcpy - copy a string from src to dest returning a pointer to the new end
 * @dest: Where to copy to
 * @src:  Where to copy from
 */
char *stpcpy(char *__restrict__ dest, const char *__restrict__ src)
{
	while ((*dest++ = *src++) != '\\0')
		/* nothing */;
	return --dest;
}
EXPORT_SYMBOL(stpcpy);
#endif
"""

DECL = """#ifndef __HAVE_ARCH_STPCPY
extern char *stpcpy(char *__restrict__ dest, const char *__restrict__ src);
#endif
"""


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def insert_after(path, anchor, block, marker):
    s = read(path)
    if marker in s:
        print("[stpcpy] already present in", path); return
    n = s.count(anchor)
    if n != 1:
        print("FATAL: anchor %r count=%d in %s (expect 1)" % (anchor, n, path)); sys.exit(1)
    s = s.replace(anchor, anchor + "\n" + block.rstrip("\n"), 1)
    write(path, s); print("[stpcpy] patched (after anchor):", path)


def insert_before(path, anchor, block, marker):
    s = read(path)
    if marker in s:
        print("[stpcpy] already present in", path); return
    n = s.count(anchor)
    if n != 1:
        print("FATAL: anchor %r count=%d in %s (expect 1)" % (anchor, n, path)); sys.exit(1)
    s = s.replace(anchor, block.rstrip("\n") + "\n\n" + anchor, 1)
    write(path, s); print("[stpcpy] patched (before anchor):", path)


def main():
    sc = "lib/string.c"
    sh = "include/linux/string.h"
    for p in (sc, sh):
        if not os.path.isfile(p):
            print("FATAL: missing", p); sys.exit(1)
    # impl: place BEFORE the strncpy block so it sits at top level (not inside
    # the __HAVE_ARCH_STRCPY #ifndef that ends right after EXPORT_SYMBOL(strcpy)).
    insert_before(sc, "#ifndef __HAVE_ARCH_STRNCPY", IMPL, "char *stpcpy(")
    # decl: place at top level, right BEFORE the strncpy guard (i.e. after the
    # strcpy block's #endif), so it is not nested inside __HAVE_ARCH_STRCPY.
    insert_before(sh, "#ifndef __HAVE_ARCH_STRNCPY", DECL, "extern char *stpcpy")
    # verify, exactly once each
    c, h = read(sc), read(sh)
    if c.count("char *stpcpy(char *__restrict__ dest") != 1:
        print("FATAL: stpcpy impl not inserted exactly once"); sys.exit(1)
    if h.count("extern char *stpcpy") != 1:
        print("FATAL: stpcpy decl not inserted exactly once"); sys.exit(1)
    # must NOT be nested inside the STRCPY guard: impl must appear after its #endif
    idx_impl = c.index("char *stpcpy(")
    idx_strncpy = c.index("#ifndef __HAVE_ARCH_STRNCPY")
    if not (idx_impl < idx_strncpy):
        print("FATAL: stpcpy impl misplaced"); sys.exit(1)
    print("[stpcpy] backport OK")


if __name__ == "__main__":
    main()
