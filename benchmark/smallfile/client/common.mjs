// Shared by the smallfile clients: each arm's smallfile top folder and the
// folder that keeps smallfile's own output. The layerfs arm runs in the
// mounted Workspace (session.json's path), the sandbox-disk arm in the
// Sandbox container's own /tmp (overlayfs). smallfile's output, JSON result
// and per-thread logs go to the container's /tmp in both arms, so they do
// not land in the measured filesystem.
export const DISK = "/tmp/sf";
export const OUT = "/tmp/sf-out";
export const layerfsTop = (path) => `${path}/sf`;
export const armTop = (arm, path) => (arm === "layerfs" ? layerfsTop(path) : DISK);
export const SMALLFILE = "python3 /opt/smallfile/smallfile_cli.py";
