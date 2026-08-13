import { useGenerationStore } from '../store/generationStore'

export default function ProgressPanel(): JSX.Element {
  const jobs = useGenerationStore((s) => s.jobs)
  const activeJobId = useGenerationStore((s) => s.activeJobId)
  const clearFinished = useGenerationStore((s) => s.clearFinished)

  const list = Object.values(jobs).sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
  const active = activeJobId ? jobs[activeJobId] : null
  const hasFinished = list.some((j) => j.status !== 'running')

  return (
    <footer className="progress-panel">
      <div className="progress-panel__head">
        <span className="panel__title">
          <span className="panel__dot" />
          生成进度
        </span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {hasFinished && (
            <button className="btn btn--ghost btn--sm" onClick={clearFinished}>
              清除历史
            </button>
          )}
        </div>
      </div>

      <div className="progress-panel__body">
        {list.length === 0 && (
          <div className="empty-hint">
            暂无生成任务。在右侧配置角色后点击「生成角色」。
          </div>
        )}

        {active && (
          <div>
            <div className="status-line" style={{ marginBottom: 6 }}>
              {active.status === 'running' && <span className="status-line__spinner" />}
              <span>
                [{active.provider}] {active.message}
              </span>
              <span style={{ marginLeft: 'auto', color: 'var(--text-faint)', fontWeight: 600 }}>
                {active.progress}%
              </span>
            </div>
            <div className="progress-bar">
              <div className="progress-bar__fill" style={{ width: `${active.progress}%` }} />
            </div>
            {active.steps.length > 0 && (
              <div className="step-list" style={{ marginTop: 8 }}>
                {active.steps.map((step) => (
                  <div key={step.index} className={`step step--${step.status}`}>
                    <span className="step__icon">
                      {step.status === 'done' ? '✓' : step.status === 'failed' ? '!' : ''}
                    </span>
                    <span className="step__label">{step.label}</span>
                    <span className="step__status">
                      {step.status === 'done' ? '完成' : step.status === 'running' ? '进行中' : step.status === 'failed' ? '失败' : '等待中'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {list
          .filter((j) => j.id !== activeJobId)
          .map((job) => (
            <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-dim)' }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background:
                    job.status === 'done' ? 'var(--success)' : job.status === 'failed' ? 'var(--danger)' : 'var(--warning)'
                }}
              />
              <span>
                [{job.provider}] {job.status === 'failed' ? job.error ?? 'Failed' : job.message}
              </span>
              <span style={{ marginLeft: 'auto', color: 'var(--text-faint)' }}>{job.progress}%</span>
            </div>
          ))}
      </div>
    </footer>
  )
}
