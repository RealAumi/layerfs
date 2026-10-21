// Inspect/clear generated Cargo children; direct binaries and helpers stay put.
import fs from 'node:fs';
import crypto from 'node:crypto';
const root = '/target';
const generated = ['incremental', 'deps', 'build', '.fingerprint', 'examples'];
const [mode, planPath] = process.argv.slice(2);
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
function fileHash(path) {
  const h = crypto.createHash('sha256'), block = Buffer.alloc(1024 * 1024);
  const fd = fs.openSync(path, 'r');
  try { let n; while ((n = fs.readSync(fd, block, 0, block.length, null))) h.update(block.subarray(0, n)); }
  finally { fs.closeSync(fd); }
  return h.digest('hex');
}
function snapshot(path) {
  const h = crypto.createHash('sha256'); let entries = 0, allocated = 0;
  function walk(item) {
    const s = fs.lstatSync(item, {bigint: true});
    if (!(s.isFile() || s.isDirectory() || s.isSymbolicLink())) throw Error(`Special cache file: ${item}`);
    const row = [item.slice(path.length), s.dev, s.ino, s.mode, s.size, s.mtimeNs, s.ctimeNs,
      s.isSymbolicLink() ? fs.readlinkSync(item) : null].map(v => typeof v === 'bigint' ? String(v) : v);
    h.update(JSON.stringify(row) + '\n'); entries++; allocated += Number(s.blocks) * 512;
    if (s.isDirectory()) for (const name of fs.readdirSync(item).sort()) walk(`${item}/${name}`);
  }
  walk(path); return {sha256: h.digest('hex'), entries, allocated_bytes: allocated};
}
function binaries() {
  const result = {};
  for (const folder of [root, `${root}/debug`, `${root}/release`]) {
    if (!fs.existsSync(folder)) continue;
    for (const name of fs.readdirSync(folder).sort()) {
      const path = `${folder}/${name}`, s = fs.lstatSync(path);
      if (s.isFile()) result[path] = {sha256: fileHash(path), mode: s.mode, uid: s.uid, gid: s.gid};
      else if (s.isSymbolicLink()) result[path] = {target: fs.readlinkSync(path)};
    }
  }
  return result;
}
if (!fs.lstatSync(`${root}/.rustc_info.json`).isFile()) throw Error('Missing Cargo target metadata');
for (const profile of ['debug', 'release']) {
  const path = `${root}/${profile}`;
  if (fs.existsSync(path) && (!fs.lstatSync(path).isDirectory() || fs.lstatSync(path).isSymbolicLink()))
    throw Error(`Invalid Cargo profile: ${path}`);
}
if (mode === 'plan') {
  const children = {};
  for (const profile of ['debug', 'release']) for (const name of generated) {
    const path = `${root}/${profile}/${name}`;
    if (!fs.existsSync(path)) continue;
    const s = fs.lstatSync(path);
    if (!s.isDirectory() || s.isSymbolicLink()) throw Error(`Invalid generated child: ${path}`);
    children[path] = snapshot(path);
  }
  console.log(JSON.stringify({version: 1, children, preserved_direct_files: binaries()}));
} else if (mode === 'apply') {
  const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
  if (plan.version !== 1) throw Error('Unsupported cache plan');
  for (const [path, expected] of Object.entries(plan.children)) {
    if (!['debug', 'release'].some(p => generated.some(n => path === `${root}/${p}/${n}`))) throw Error('Invalid selection');
    if (JSON.stringify(snapshot(path)) !== JSON.stringify(expected)) throw Error(`Cache changed: ${path}`);
  }
  if (JSON.stringify(binaries()) !== JSON.stringify(plan.preserved_direct_files)) throw Error('Direct files changed');
  // Validate every sibling first: unlinking hard links changes other ctimes.
  for (const path of Object.keys(plan.children)) fs.rmSync(path, {recursive: true});
  if (Object.keys(plan.children).some(p => fs.existsSync(p))) throw Error('Generated child remains');
  if (JSON.stringify(binaries()) !== JSON.stringify(plan.preserved_direct_files)) throw Error('Direct binary preservation failed');
  console.log(JSON.stringify({removed_cache_paths: Object.keys(plan.children), preserved_direct_files: plan.preserved_direct_files}));
} else throw Error('Use plan or apply');
