// Diagnostic, after a run: minimal repros of the LayerFS-only failure
// classes a run found, each a few pjdfstest calls in a fresh directory, run
// once per arm with one sandbox.exec (layerfs: <path>/pjd/repro, then
// sandbox-disk: /tmp/pjd/repro). repro.jsonl gets each arm's output; the
// lines print `case: result` so the two arms read side by side. Not part of
// a measured run; use it on a smoke run's Sandbox (run.sh repro RUN).
//
//   repro.mjs
import { append, exec, lfs, session } from "../../common/session.mjs";

const P = "/opt/pjdfstest/pjdfstest";
const CASES = [
  ["mkfifo", `${P} mkfifo f 0644`],
  ["bind (AF_UNIX socket)", `${P} bind s`],
  ["mknod S_IFIFO", `${P} mknod m f 0644 0 0`],
  ["mkfifo on an existing file (EEXIST expected)", `${P} create e 0644 >/dev/null; ${P} mkfifo e 0644`],
  ["create mode 04777", `${P} create su 04777`],
  ["create mode 02777", `${P} create sg 02777`],
  ["chmod 06555 on own file", `${P} create a 0644 >/dev/null; ${P} chmod a 06555`],
  ["chmod 06555 on own directory", `${P} mkdir d 0755 >/dev/null; ${P} chmod d 06555`],
  ["chmod 01700 (sticky) on own file", `${P} create b 0644 >/dev/null; ${P} chmod b 01700`],
  ["utimensat atime=1900000000 mtime=1950000000, then lstat atime,mtime",
    `${P} create t 0644 >/dev/null; ${P} open . O_RDONLY : utimensat 0 t 1900000000 0 1950000000 0 0 >/dev/null; ${P} lstat t atime,mtime`],
  ["ctime before,after chmod 0600 (1 s apart)", `${P} create c 0644 >/dev/null; a=$(${P} stat c ctime); sleep 1; ${P} chmod c 0600 >/dev/null; echo $a,$(${P} stat c ctime)`],
  ["ctime before,after link (1 s apart)", `${P} create l 0644 >/dev/null; a=$(${P} stat l ctime); sleep 1; ${P} link l l2 >/dev/null; echo $a,$(${P} stat l ctime)`],
  ["ctime before,after unlink of the other link (1 s apart)", `a=$(${P} stat l ctime); sleep 1; ${P} unlink l2 >/dev/null; echo $a,$(${P} stat l ctime)`],
  ["ctime of a multiply linked target before,after rename onto it (1 s apart)",
    `${P} create s1 0644 >/dev/null; ${P} create d1 0644 >/dev/null; ${P} link d1 dl >/dev/null; a=$(${P} stat dl ctime); sleep 1; ${P} rename s1 d1 >/dev/null; echo $a,$(${P} stat dl ctime),nlink=$(${P} stat dl nlink)`],
];
const script = (root) =>
  [`set -u; rm -rf ${root}/pjd/repro; mkdir -p ${root}/pjd/repro && cd ${root}/pjd/repro || exit 3`,
    ...CASES.map(([name, cmd]) => `printf '%s: %s\\n' ${JSON.stringify(name)} "$( { ${cmd}; } 2>&1 | tr '\\n' ' ')"`)].join("\n");

const { path } = session();
for (const [arm, root] of [["layerfs", path], ["sandbox-disk", "/tmp"]]) {
  const r = await exec(path, script(root));
  append("repro.jsonl", { arm, root, ...r });
}
await lfs.close();
