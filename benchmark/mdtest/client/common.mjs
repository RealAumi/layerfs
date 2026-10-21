// Shared by the mdtest clients: each arm's base folder. The layerfs arm runs
// in the mounted Workspace (session.json's path), the sandbox-disk arm in
// the Sandbox container's own /tmp (overlayfs).
export const DISK = "/tmp/md";
export const layerfsBase = (path) => `${path}/md`;
export const armBase = (arm, path) => (arm === "layerfs" ? layerfsBase(path) : DISK);
