const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  startRecording: () => ipcRenderer.invoke('start-recording'),
  stopRecording: () => ipcRenderer.invoke('stop-recording'),
  sendAudioChunk: (data) => ipcRenderer.invoke('send-audio-chunk', data),
  sendManualInput: (data) => ipcRenderer.invoke('send-manual-input', data),
  onTranscriptChunk: (callback) => {
    const handler = (_event, value) => callback(value);
    ipcRenderer.on('transcript-chunk', handler);
    return () => ipcRenderer.removeListener('transcript-chunk', handler);
  },
  onActionUpdate: (callback) => {
    const handler = (_event, value) => callback(value);
    ipcRenderer.on('action-update', handler);
    return () => ipcRenderer.removeListener('action-update', handler);
  },
  classifyText: (data) => ipcRenderer.invoke('classify-text', data),
  getConfig: () => ipcRenderer.invoke('get-config')
});
