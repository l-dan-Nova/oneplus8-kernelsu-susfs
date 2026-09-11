#!/usr/bin/env python3
# Apply official KernelSU v0.9.5 non-GKI manual hooks to a 4.19 kernel tree.
# Reference: tiann/KernelSU@v0.9.5 website/docs/guide/how-to-integrate-for-non-gki.md
# Idempotent: safe to re-run; aborts non-zero if any anchor is missing (no silent skip).
import sys, os

MARK = "/* KSU-NONGKI-MANUAL */"

def read(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.readlines()

def write(p, lines):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)

def idx_of(lines, sub, start=0):
    hits = [i for i in range(start, len(lines)) if sub in lines[i]]
    if len(hits) != 1:
        raise SystemExit(f"[KSUGRAFT] anchor not unique/found ({len(hits)}): {sub!r}")
    return hits[0]

def scope_idx(lines, scope_sub, anchor_sub):
    s = idx_of(lines, scope_sub)
    hits = [i for i in range(s, len(lines)) if anchor_sub in lines[i]]
    if not hits:
        raise SystemExit(f"[KSUGRAFT] in-scope anchor missing after {scope_sub!r}: {anchor_sub!r}")
    return hits[0]

def block(text):
    # text uses leading tabs; ensure each line ends with newline
    out = []
    for ln in text.strip("\n").split("\n"):
        out.append(ln.replace("    ", "\t", 1) if ln.startswith("    ") else ln)
    return [l + "\n" for l in out]

def process(path, ops):
    lines = read(path)
    if any(MARK in l for l in lines):
        print(f"[KSUGRAFT] already patched, skip: {path}")
        return
    # apply from bottom to top so indices stay valid
    todo = []
    for op in ops:
        todo.append(op)
    for op in sorted(todo, key=lambda o: -o["at"]):
        lines[op["at"]:op["at"]] = op["lines"]
    write(path, lines)
    print(f"[KSUGRAFT] patched: {path} ({len(ops)} insertions)")

def main():
    root = sys.argv[1]
    def P(*a): return os.path.join(root, *a)

    # ---- fs/exec.c : extern before do_execveat_common ; call before its return ----
    p = P("fs", "exec.c"); L = read(p)
    i_sig = idx_of(L, "static int do_execveat_common(int fd, struct filename *filename,")
    i_ret = scope_idx(L, "static int do_execveat_common(int fd, struct filename *filename,",
                      "__do_execve_file(fd, filename, argv, envp, flags, NULL)")
    exec_ext = MARK + "\n" + "\n".join([
        "#ifdef CONFIG_KSU",
        "extern bool ksu_execveat_hook __read_mostly;",
        "extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr, void *argv,",
        "\t\t\tvoid *envp, int *flags);",
        "extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,",
        "\t\t\t\t void *argv, void *envp, int *flags);",
        "#endif", ""])
    exec_call = "\n".join([
        "#ifdef CONFIG_KSU",
        "\tif (unlikely(ksu_execveat_hook))",
        "\t\tksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);",
        "\telse",
        "\t\tksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);",
        "#endif", ""])
    process(p, [
        {"at": i_sig, "lines": [l + "\n" for l in exec_ext.split("\n")]},
        {"at": i_ret, "lines": [l + "\n" for l in exec_call.split("\n")]},
    ])

    # ---- fs/open.c ----
    p = P("fs", "open.c"); L = read(p)
    i_sig = idx_of(L, "long do_faccessat(int dfd, const char __user *filename, int mode)")
    i_lf = scope_idx(L, "long do_faccessat(int dfd, const char __user *filename, int mode)",
                     "unsigned int lookup_flags = LOOKUP_FOLLOW;")
    open_ext = MARK + "\n" + "\n".join([
        "#ifdef CONFIG_KSU",
        "extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode,",
        "\t\t\t int *flags);",
        "#endif", ""])
    open_call = "\n".join([
        "#ifdef CONFIG_KSU",
        "\tksu_handle_faccessat(&dfd, &filename, &mode, NULL);",
        "#endif", ""])
    process(p, [
        {"at": i_sig, "lines": [l + "\n" for l in open_ext.split("\n")]},
        {"at": i_lf + 1, "lines": [l + "\n" for l in open_call.split("\n")]},
    ])

    # ---- fs/stat.c ----
    p = P("fs", "stat.c"); L = read(p)
    i_sig = idx_of(L, "int vfs_statx(int dfd, const char __user *filename, int flags,")
    i_lf = idx_of(L, "unsigned int lookup_flags = LOOKUP_FOLLOW | LOOKUP_AUTOMOUNT;")
    stat_ext = MARK + "\n" + "\n".join([
        "#ifdef CONFIG_KSU",
        "extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);",
        "#endif", ""])
    stat_call = "\n".join([
        "#ifdef CONFIG_KSU",
        "\tksu_handle_stat(&dfd, &filename, &flags);",
        "#endif", ""])
    process(p, [
        {"at": i_sig, "lines": [l + "\n" for l in stat_ext.split("\n")]},
        {"at": i_lf + 1, "lines": [l + "\n" for l in stat_call.split("\n")]},
    ])

    # ---- fs/read_write.c ----
    p = P("fs", "read_write.c"); L = read(p)
    i_sig = idx_of(L, "ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)")
    i_ret = scope_idx(L, "ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)",
                      "ssize_t ret;")
    rw_ext = MARK + "\n" + "\n".join([
        "#ifdef CONFIG_KSU",
        "extern bool ksu_vfs_read_hook __read_mostly;",
        "extern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,",
        "\t\t\tsize_t *count_ptr, loff_t **pos);",
        "#endif", ""])
    rw_call = "\n".join([
        "#ifdef CONFIG_KSU",
        "\tif (unlikely(ksu_vfs_read_hook))",
        "\t\tksu_handle_vfs_read(&file, &buf, &count, &pos);",
        "#endif", ""])
    process(p, [
        {"at": i_sig, "lines": [l + "\n" for l in rw_ext.split("\n")]},
        {"at": i_ret + 1, "lines": [l + "\n" for l in rw_call.split("\n")]},
    ])

    # ---- fs/devpts/inode.c ----
    p = P("fs", "devpts", "inode.c"); L = read(p)
    i_sig = idx_of(L, "void *devpts_get_priv(struct dentry *dentry)")
    i_chk = scope_idx(L, "void *devpts_get_priv(struct dentry *dentry)",
                      "if (dentry->d_sb->s_magic != DEVPTS_SUPER_MAGIC)")
    dp_ext = MARK + "\n" + "\n".join([
        "#ifdef CONFIG_KSU",
        "extern int ksu_handle_devpts(struct inode*);",
        "#endif", ""])
    dp_call = "\n".join([
        "#ifdef CONFIG_KSU",
        "\tksu_handle_devpts(dentry->d_inode);",
        "#endif", ""])
    process(p, [
        {"at": i_sig, "lines": [l + "\n" for l in dp_ext.split("\n")]},
        {"at": i_chk, "lines": [l + "\n" for l in dp_call.split("\n")]},
    ])

    # ---- drivers/input/input.c ----
    p = P("drivers", "input", "input.c"); L = read(p)
    i_sig = idx_of(L, "static void input_handle_event(struct input_dev *dev,")
    i_disp = idx_of(L, "int disposition = input_get_disposition(dev, type, code, &value);")
    in_ext = MARK + "\n" + "\n".join([
        "#ifdef CONFIG_KSU",
        "extern bool ksu_input_hook __read_mostly;",
        "extern int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code, int *value);",
        "#endif", ""])
    in_call = "\n".join([
        "#ifdef CONFIG_KSU",
        "\tif (unlikely(ksu_input_hook))",
        "\t\tksu_handle_input_handle_event(&type, &code, &value);",
        "#endif", ""])
    process(p, [
        {"at": i_sig, "lines": [l + "\n" for l in in_ext.split("\n")]},
        {"at": i_disp + 1, "lines": [l + "\n" for l in in_call.split("\n")]},
    ])

    print("[KSUGRAFT] all official v0.9.5 non-GKI hooks applied.")

if __name__ == "__main__":
    main()
