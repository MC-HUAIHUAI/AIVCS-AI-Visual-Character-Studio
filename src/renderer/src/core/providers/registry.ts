import type { AIImage3DProvider } from './aiProvider'
import { MockImage3DProvider } from './mockProvider'
import { BackendImage3DProvider, LocalLowPower3DProvider } from './httpProvider'

/**
 * Registered AI providers. The default is the local mock so Demo Mode works
 * with zero network/API dependencies.
 */
export const providers: AIImage3DProvider[] = [
  new MockImage3DProvider(),
  new BackendImage3DProvider(),
  new LocalLowPower3DProvider()
]

export function getProvider(id: string): AIImage3DProvider {
  return providers.find((p) => p.id === id) ?? providers[0]
}

export function getDefaultProviderId(): string {
  return providers[0].id
}
