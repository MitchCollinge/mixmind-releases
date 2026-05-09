const { app, BrowserWindow, ipcMain, dialog, shell, Menu, nativeImage } = require('electron')
const path   = require('path')
const { spawn, execSync, execFile } = require('child_process')
const fs     = require('fs')
const http   = require('http')

// ── Auto-updater ──────────────────────────────────────────────────────────────
let autoUpdater = null
try {
  autoUpdater = require('electron-updater').autoUpdater
  autoUpdater.autoDownload    = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.logger = require('electron').app  // silence in dev

  autoUpdater.on('update-available', (info) => {
    notifyRenderer('update-status', {
      status: 'available',
      version: info.version,
      message: `MixMind ${info.version} is downloading…`
    })
  })

  autoUpdater.on('update-downloaded', (info) => {
    notifyRenderer('update-status', {
      status: 'ready',
      version: info.version,
      message: `MixMind ${info.version} ready — will install on next restart`
    })
    // Show native dialog
    dialog.showMessageBox({
      type: 'info',
      title: 'Update Ready',
      message: `MixMind ${info.version} has been downloaded.`,
      detail: 'It will be installed next time you restart the app.',
      buttons: ['Restart Now', 'Later'],
      defaultId: 0,
    }).then(({ response }) => {
      if (response === 0) autoUpdater.quitAndInstall()
    })
  })

  autoUpdater.on('error', (e) => {
    console.log('Auto-updater error:', e.message)
  })
} catch (e) {
  console.log('electron-updater not available (dev mode):', e.message)
}

// ── Config ────────────────────────────────────────────────────────────────────
const BRIDGE_PORT    = 5005
const BRIDGE_HOST    = '127.0.0.1'
const BRIDGE_URL     = `http://${BRIDGE_HOST}:${BRIDGE_PORT}`
const PING_INTERVAL  = 3000   // ms between bridge health checks
const BRIDGE_TIMEOUT = 8000   // ms to wait for bridge to start
const MIXMIND_PROTOCOL = 'mixmind'

let mainWindow   = null
let bridgeProc   = null
let tray         = null
let bridgeReady  = false
let pingTimer    = null

// ── Resolve python path ───────────────────────────────────────────────────────
function getPythonPath() {
  const candidates = [
    'python3', 'python',
    '/usr/local/bin/python3',
    '/usr/bin/python3',
    '/opt/homebrew/bin/python3',
    path.join(process.env.HOME || '', '.pyenv/shims/python3'),
  ]
  for (const p of candidates) {
    try { execSync(`${p} --version`, { stdio: 'ignore' }); return p } catch {}
  }
  return null
}

// ── Resolve bridge script path ────────────────────────────────────────────────
function getBridgePath() {
  // In packaged app, extraResources are in process.resourcesPath
  const packed = path.join(process.resourcesPath, 'bridge.py')
  if (fs.existsSync(packed)) return packed
  // Dev mode — next to main.js
  return path.join(__dirname, 'bridge.py')
}

// ── Install Python deps ───────────────────────────────────────────────────────
function installDeps(pythonPath) {
  try {
    execSync(`${pythonPath} -c "import flask, flask_cors, pythonosc"`, { stdio: 'ignore' })
    return true // already installed
  } catch {}
  try {
    const reqPath = path.join(process.resourcesPath || __dirname, 'requirements.txt')
    execSync(`${pythonPath} -m pip install -r "${reqPath}" --quiet`, { timeout: 60000 })
    return true
  } catch (e) {
    console.error('pip install failed:', e.message)
    return false
  }
}

// ── Start Python bridge ───────────────────────────────────────────────────────
function startBridge() {
  const python = getPythonPath()
  if (!python) {
    dialog.showErrorBox('Python not found',
      'MixMind needs Python 3. Install it from python.org and relaunch the app.')
    return
  }

  const depsOk = installDeps(python)
  if (!depsOk) {
    dialog.showErrorBox('Dependency error',
      'Could not install required Python packages (flask, python-osc).\nRun: pip install flask flask-cors python-osc')
  }

  const bridgePath = getBridgePath()
  console.log(`Starting bridge: ${python} ${bridgePath}`)

  bridgeProc = spawn(python, [bridgePath], {
    env: { ...process.env, FLASK_ENV: 'production' },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  bridgeProc.stdout.on('data', d => console.log('[bridge]', d.toString().trim()))
  bridgeProc.stderr.on('data', d => console.error('[bridge]', d.toString().trim()))
  bridgeProc.on('exit', (code) => {
    console.log('Bridge exited with code', code)
    bridgeReady = false
    notifyRenderer('bridge-status', { ok: false })
  })

  // Poll until bridge responds
  waitForBridge()
}

function waitForBridge(elapsed = 0) {
  if (elapsed > BRIDGE_TIMEOUT) {
    console.error('Bridge failed to start in time')
    notifyRenderer('bridge-status', { ok: false, error: 'Bridge timed out' })
    return
  }
  pingBridgeHttp((ok) => {
    if (ok) {
      bridgeReady = true
      notifyRenderer('bridge-status', { ok: true })
      startPingLoop()
    } else {
      setTimeout(() => waitForBridge(elapsed + 500), 500)
    }
  })
}

function pingBridgeHttp(cb) {
  const req = http.get(`${BRIDGE_URL}/ping`, { timeout: 1500 }, (res) => {
    cb(res.statusCode === 200)
  })
  req.on('error', () => cb(false))
  req.on('timeout', () => { req.destroy(); cb(false) })
}

function startPingLoop() {
  clearInterval(pingTimer)
  pingTimer = setInterval(() => {
    pingBridgeHttp((ok) => {
      if (bridgeReady !== ok) {
        bridgeReady = ok
        notifyRenderer('bridge-status', { ok })
      }
    })
  }, PING_INTERVAL)
}

// ── IPC — renderer calls bridge via main process ──────────────────────────────
ipcMain.handle('bridge-call', async (event, { endpoint, method = 'POST', body = {} }) => {
  return new Promise((resolve) => {
    // For GET requests, append body as query string
    let path = endpoint
    if (method === 'GET' && body && Object.keys(body).length) {
      path += '?' + new URLSearchParams(body).toString()
    }

    const payload = method !== 'GET' ? JSON.stringify(body) : ''
    const options = {
      hostname: BRIDGE_HOST,
      port:     BRIDGE_PORT,
      path,
      method,
      headers: method !== 'GET' ? {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(payload),
      } : {},
      timeout: 60000,
    }

    const req = http.request(options, (res) => {
      let data = ''
      res.on('data', chunk => data += chunk)
      res.on('end', () => {
        try { resolve({ ok: true, ...JSON.parse(data) }) }
        catch { resolve({ ok: false, error: 'Invalid JSON' }) }
      })
    })

    req.on('error', (e) => resolve({ ok: false, error: e.message }))
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, error: 'Timeout' }) })
    if (method !== 'GET') req.write(payload)
    req.end()
  })
})

ipcMain.handle('get-bridge-status', () => ({ ok: bridgeReady }))

ipcMain.handle('open-external', (event, url) => shell.openExternal(url))

ipcMain.handle('store-get', (event, key) => {
  try {
    const p = path.join(app.getPath('userData'), 'config.json')
    if (!fs.existsSync(p)) return null
    const cfg = JSON.parse(fs.readFileSync(p, 'utf8'))
    return cfg[key] ?? null
  } catch { return null }
})

ipcMain.handle('store-set', (event, key, value) => {
  try {
    const p = path.join(app.getPath('userData'), 'config.json')
    const cfg = fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : {}
    cfg[key] = value
    fs.writeFileSync(p, JSON.stringify(cfg, null, 2))
    return true
  } catch { return false }
})

// ── Notify renderer ───────────────────────────────────────────────────────────
function notifyRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}

// ── mixmind:// URL scheme (open/focus app from Ableton Remote Script or OS) ─
function registerMixmindProtocol() {
  try {
    if (process.defaultApp) {
      if (process.argv.length >= 2) {
        app.setAsDefaultProtocolClient(MIXMIND_PROTOCOL, process.execPath, [path.resolve(process.argv[1])])
      }
    } else {
      app.setAsDefaultProtocolClient(MIXMIND_PROTOCOL)
    }
  } catch (e) {
    console.warn('mixmind:// registration:', e.message)
  }
}

function handleDeepLinkArgv(argv) {
  if (!argv || !argv.length) return
  const hit = argv.find((a) => typeof a === 'string' && a.startsWith(`${MIXMIND_PROTOCOL}://`))
  if (hit) focusMainWindow()
}

function focusMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  } else {
    createWindow()
  }
}

const gotSingleInstanceLock = app.requestSingleInstanceLock()
if (!gotSingleInstanceLock) {
  app.quit()
  process.exit(0)
}

app.on('second-instance', (event, commandLine) => {
  event.preventDefault()
  handleDeepLinkArgv(commandLine)
  focusMainWindow()
})

if (process.platform === 'darwin') {
  app.on('open-url', (event, url) => {
    event.preventDefault()
    if (typeof url === 'string' && url.startsWith(`${MIXMIND_PROTOCOL}://`)) focusMainWindow()
  })
}

registerMixmindProtocol()

// ── Create window ─────────────────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width:           980,
    height:          720,
    minWidth:        780,
    minHeight:       560,
    backgroundColor: '#080808',
    titleBarStyle:   'hiddenInset',  // macOS — clean look
    frame:           process.platform !== 'darwin',
    webPreferences: {
      preload:             path.join(__dirname, 'preload.js'),
      contextIsolation:    true,
      nodeIntegration:     false,
    },
    show: false,  // show after ready-to-show
  })

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))

  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  mainWindow.on('closed', () => { mainWindow = null })

  // Remove default menu
  Menu.setApplicationMenu(buildMenu())
}

function buildMenu() {
  const template = [
    {
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'quit' }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' }, { role: 'redo' }, { type: 'separator' },
        { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { type: 'separator' },
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'toggleDevTools' }
      ]
    }
  ]
  return Menu.buildFromTemplate(template)
}

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow()
  handleDeepLinkArgv(process.argv)
  startBridge()

  // Check for updates 5 seconds after launch (only in packaged app)
  if (app.isPackaged && autoUpdater) {
    setTimeout(() => {
      autoUpdater.checkForUpdatesAndNotify().catch(e =>
        console.log('Update check failed:', e.message)
      )
    }, 5000)
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// IPC — renderer can trigger update install
ipcMain.handle('install-update', () => {
  if (autoUpdater) autoUpdater.quitAndInstall()
})

ipcMain.handle('check-for-updates', async () => {
  if (!autoUpdater || !app.isPackaged) {
    return { available: false, message: 'Running in dev mode' }
  }
  try {
    const result = await autoUpdater.checkForUpdates()
    return { available: !!result, version: result?.updateInfo?.version }
  } catch (e) {
    return { available: false, message: e.message }
  }
})

ipcMain.handle('get-version', () => app.getVersion())

ipcMain.handle('focus-app-window', () => {
  focusMainWindow()
  return true
})

/** Open Ableton Live (macOS / common install paths). */
ipcMain.handle('open-ableton-live', async () => {
  if (process.platform !== 'darwin') {
    return { ok: false, error: 'Use Start Menu on Windows to launch Live' }
  }
  const candidates = [
    'Ableton Live 12 Suite',
    'Ableton Live 12 Standard',
    'Ableton Live 11 Suite',
    'Ableton Live 12',
  ]
  return new Promise((resolve) => {
    const tryOpen = (i) => {
      if (i >= candidates.length) {
        resolve({ ok: false, error: 'Could not find Ableton Live via open -a' })
        return
      }
      execFile('/usr/bin/open', ['-a', candidates[i]], (err) => {
        if (err) tryOpen(i + 1)
        else resolve({ ok: true, app: candidates[i] })
      })
    }
    tryOpen(0)
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  clearInterval(pingTimer)
  if (bridgeProc) {
    bridgeProc.kill('SIGTERM')
    bridgeProc = null
  }
})
