import type { ViewportManager } from './ViewportManager'

/**
 * Lightweight singleton bridge between the React layer and the imperative
 * Three.js viewport. The Viewport component registers its manager here so that
 * generation flows and panels can drive the scene without prop drilling.
 */
let current: ViewportManager | null = null

export function setViewportManager(manager: ViewportManager | null): void {
  current = manager
}

export function getViewportManager(): ViewportManager | null {
  return current
}
