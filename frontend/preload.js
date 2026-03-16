const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  startRecording: () => ipcRenderer.invoke('start-recording'),
  stopRecording: () => ipcRenderer.invoke('stop-recording'),
  sendAudioChunk: (data) => ipcRenderer.invoke('send-audio-chunk', data),
  sendManualInput: (data) => ipcRenderer.invoke('send-manual-input', data),
  onTranscriptChunk: (callback) => ipcRenderer.on('transcript-chunk', (_event, value) => callback(value)),
  onActionUpdate: (callback) => ipcRenderer.on('action-update', (_event, value) => callback(value)),
  classifyText: (data) => ipcRenderer.invoke('classify-text', data),
  getConfig: () => ipcRenderer.invoke('get-config')
});
