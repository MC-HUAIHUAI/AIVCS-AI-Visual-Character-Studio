/// <reference types="vite/client" />

import type { AivcsApi } from '@shared/ipc'

declare global {
  interface Window {
    aivcs: AivcsApi
  }
}

export {}
