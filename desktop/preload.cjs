const { contextBridge, ipcRenderer } = require("electron");
// One narrow request channel; no filesystem, shell, or general IPC access.
contextBridge.exposeInMainWorld(
  "surge",
  Object.freeze({
    request: (method, args = {}) =>
      ipcRenderer.invoke("surge:request", method, args),
  }),
);
