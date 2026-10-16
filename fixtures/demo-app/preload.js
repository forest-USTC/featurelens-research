import { contextBridge, ipcRenderer } from 'electron';
contextBridge.exposeInMainWorld('knowledge', {
  ask: (question, documents) => ipcRenderer.invoke('knowledge:ask', question, documents)
});
