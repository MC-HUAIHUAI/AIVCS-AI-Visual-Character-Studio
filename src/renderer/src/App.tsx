import { useEffect } from 'react'
import TitleBar from './components/TitleBar'
import AssetsPanel from './components/AssetsPanel'
import Viewport from './components/Viewport'
import AIAssistantPanel from './components/AIAssistantPanel'
import ProgressPanel from './components/ProgressPanel'
import SettingsDialog from './components/SettingsDialog'
import Portrait2DPanel from './components/Portrait2DPanel'
import { useUIStore } from './store/uiStore'

export default function App(): JSX.Element {
  const checkBackend = useUIStore((s) => s.checkBackend)

  useEffect(() => {
    checkBackend()
    const timer = setInterval(() => {
      checkBackend()
    }, 8000)
    return () => clearInterval(timer)
  }, [checkBackend])

  return (
    <div className="app">
      <TitleBar />
      <div className="app__body">
        <AssetsPanel />
        <Viewport />
        <AIAssistantPanel />
      </div>
      <ProgressPanel />
      <SettingsDialog />
      <Portrait2DPanel />
    </div>
  )
}
