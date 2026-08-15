import { app, BrowserWindow } from 'electron'
import { join } from 'node:path'
import { registerProjectHandlers } from './ipc'
import { registerSettingsHandlers } from './settings'
import { registerDemoHandlers } from './demo'
import { ensureBackend, stopBackend } from './backend'

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#0b0e14',
    title: 'AIVCS',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  })

  win.on('ready-to-show', () => {
    win.show()
  })

  // Forward renderer console messages to the terminal in development so errors
  // surface during debugging (legacy positional form for Electron 33).
  // Release builds never forward renderer output (may contain sensitive data).
  if (!app.isPackaged) {
    win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
      const tag = ['', 'log', 'warning', 'error'][level] ?? String(level)
      console.log(`[renderer:${tag}] ${message} (${sourceId}:${line})`)
    })
  }

  // electron-vite injects ELECTRON_RENDERER_URL in dev mode.
  const devUrl = process.env['ELECTRON_RENDERER_URL']
  if (devUrl) {
    win.loadURL(devUrl)
    // DevTools only in development - never in a release build.
    if (!app.isPackaged) {
      win.webContents.openDevTools({ mode: 'detach' })
    }
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(() => {
  registerProjectHandlers()
  registerSettingsHandlers()
  registerDemoHandlers()
  createWindow()
  // Packaged: ensure the bundled backend.exe is up (dev relies on npm run backend).
  if (app.isPackaged) {
    void ensureBackend()
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('will-quit', () => {
  stopBackend()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
