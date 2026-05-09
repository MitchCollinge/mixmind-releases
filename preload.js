const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('mixmind', {
  // Call the local OSC bridge
  bridgeCall: (endpoint, method = 'POST', body = {}) =>
    ipcRenderer.invoke('bridge-call', { endpoint, method, body }),

  // Get bridge connection status
  getBridgeStatus: () =>
    ipcRenderer.invoke('get-bridge-status'),

  // Listen for bridge status updates pushed from main
  onBridgeStatus: (cb) =>
    ipcRenderer.on('bridge-status', (event, data) => cb(data)),

  // Persistent config storage
  store: {
    get: (key)        => ipcRenderer.invoke('store-get', key),
    set: (key, value) => ipcRenderer.invoke('store-set', key, value),
  },

  // Open URLs in default browser
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // Auto-updater
  getVersion:       ()  => ipcRenderer.invoke('get-version'),
  focusAppWindow:   ()  => ipcRenderer.invoke('focus-app-window'),
  openAbletonLive:  ()  => ipcRenderer.invoke('open-ableton-live'),
  checkForUpdates:  ()  => ipcRenderer.invoke('check-for-updates'),
  installUpdate:    ()  => ipcRenderer.invoke('install-update'),
  onUpdateStatus:   (cb) => ipcRenderer.on('update-status', (event, data) => cb(data)),
})
