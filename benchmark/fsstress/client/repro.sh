#!/usr/bin/env bash
# Minimal repros of the operations fsstress saw fail only on layerfs, with
# standard tools (util-linux fallocate, coreutils ln) or a few lines of
# Python for the syscalls and ioctls that have no tool in the image. Sent
# through sandbox.exec by repro.mjs; prints one line per probe:
#   probe|exit|output
#
#   repro.sh DIR      (DIR must not exist)
set -u
dir=$1
mkdir "$dir" && cd "$dir" || exit 2
run() { local name=$1 out status; shift; out=$("$@" 2>&1); status=$?; echo "$name|$status|${out//$'\n'/ }"; }
py() { python3 -c "import array, ctypes, fcntl, os, struct; $1"; }
head -c 65536 /dev/zero >f
cp f g
run fallocate fallocate -o 0 -l 1048576 f
run fallocate-keep-size fallocate -n -o 1048576 -l 65536 f
run fallocate-punch-hole fallocate -p -o 0 -l 4096 f
run fallocate-zero-range fallocate -z -o 0 -l 4096 f
run fallocate-collapse-range fallocate -c -o 0 -l 4096 f
run fallocate-insert-range fallocate -i -o 0 -l 4096 f
run setxattr py 'os.setxattr("f", "user.k", b"v")'
run getxattr py 'print(os.getxattr("f", "user.k"))'
run listxattr py 'print(os.listxattr("f"))'
run removexattr py 'os.removexattr("f", "user.k")'
touch a b
run rename-exchange py 'libc = ctypes.CDLL(None, use_errno=True); r = libc.renameat2(-100, b"a", -100, b"b", 2); e = ctypes.get_errno(); print("ok" if r == 0 else f"renameat2(RENAME_EXCHANGE): [Errno {e}] {os.strerror(e)}"); raise SystemExit(r != 0)'
ln -s f s
run link-file ln f f2
run link-symlink ln s s2
run stat-symlink stat -c '%U:%G %a %h %F' s
run ioctl-getflags py 'fcntl.ioctl(open("f", "rb"), 0x80086601, array.array("l", [0]))'
run ioctl-fiemap py 'fcntl.ioctl(open("f", "rb"), 0xC020660B, bytearray(struct.pack("QQIIII", 0, 2**64 - 1, 0, 0, 0, 0)))'
run ioctl-fsgetxattr py 'fcntl.ioctl(open("f", "rb"), 0x801C581F, bytearray(28))'
run ioctl-resvsp64 py 'fcntl.ioctl(open("f", "r+b"), 0x4030582A, bytearray(struct.pack("hhiqqiI", 0, 0, 0, 0, 4096, 0, 0) + bytes(16)))'
run ioctl-dedupe-range py 'd = open("g", "r+b"); b = bytearray(struct.pack("QQHHI", 0, 4096, 1, 0, 0) + struct.pack("qQQiI", d.fileno(), 0, 0, 0, 0)); fcntl.ioctl(open("f", "rb"), 0xC0189436, b); print("ioctl ok; range status", struct.unpack_from("i", b, 24 + 24)[0])'
