// Shared by the fsx clients: each arm's base folder. The layerfs arm runs
// in the mounted Workspace (session.json's path), the sandbox-disk arm in
// the Sandbox container's own /tmp (overlayfs).
export const DISK = "/tmp/fsx";
export const layerfsBase = (path) => `${path}/fsx`;
export const armBase = (arm, path) => (arm === "layerfs" ? layerfsBase(path) : DISK);
