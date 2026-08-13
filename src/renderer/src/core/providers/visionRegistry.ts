import type { AIVisionProvider } from './visionProvider'
import { MockVisionProvider } from './mockVisionProvider'
import { VisionHttpProvider } from './visionHttpProvider'

/**
 * Registered vision providers. Only the Mock is registered in Phase 2.1;
 * DeepSeek and other real providers can be added here later without touching
 * the UI or the rest of the pipeline.
 */
export const visionProviders: AIVisionProvider[] = [
  new MockVisionProvider(),
  new VisionHttpProvider()
]

export function getVisionProvider(id: string): AIVisionProvider {
  return visionProviders.find((p) => p.id === id) ?? visionProviders[0]
}

export function getDefaultVisionProviderId(): string {
  return visionProviders[0].id
}
