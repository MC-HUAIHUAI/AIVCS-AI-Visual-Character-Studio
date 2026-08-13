import { useGenerationStore } from '../store/generationStore'
import { canCancel, canRetry, isTerminal, statusText } from '../core/spec/generationLogic'

function dotColor(status: string): string {
  switch (status) {
    case 'done':
      return 'var(--success)'
    case 'failed':
      return 'var(--danger)'
    case 'timed_out':
      return 'var(--warning)'
    case 'cancelled':
      return 'var(--text-faint)'
    default:
      return 'var(--accent)'
  }
}

export default function ProgressPanel(): JSX.Element {
  const jobs = useGenerationStore((s) => s.jobs)
  const activeJobId = useGenerationStore((s) => s.activeJobId)
  const clearFinished = useGenerationStore((s) => s.clearFinished)
  const cancelJob = useGenerationStore((s) => s.cancelJob)
  const retryJob = useGenerationStore((s) => s.retryJob)

  const list = Object.values(jobs).sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
  const active = activeJobId ? jobs[activeJobId] : null
  const hasFinished = list.some((j) => isTerminal(j.status))

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
              {(active.status === 'queued' || active.status === 'running') && (
                <span className="status-line__spinner" />
              )}
              <span>
                [{active.provider}] {statusText(active.status)} · {active.message}
              </span>
              <span style={{ marginLeft: 'auto', color: 'var(--text-faint)', fontWeight: 600 }}>
                {active.progress}%
                {active.durationMs != null && ` · ${(active.durationMs / 1000).toFixed(1)}s`}
              </span>
            </div>

            {(active.status === 'queued' || active.status === 'running') && (
              <div className="progress-bar">
                <div className="progress-bar__fill" style={{ width: `${active.progress}%` }} />
              </div>
            )}

            {active.status === 'failed' && active.error && (
              <div style={{ color: 'var(--danger)', fontSize: 11.5, margin: '4px 0' }}>
                {active.error}
              </div>
            )}

            <div style={{ display: 'flex', gap: 6, margin: '6px 0' }}>
              {canCancel(active.status) && (
                <button className="btn btn--sm" onClick={() => cancelJob(active.id)}>
                  取消
                </button>
              )}
              {canRetry(active.status) && (
                <button className="btn btn--sm btn--primary" onClick={() => retryJob(active.id)}>
                  重试
                </button>
              )}
            </div>

            {active.steps.length > 0 && (
              <div className="step-list">
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
            <div
              key={job.id}
              style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-dim)' }}
            >
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: dotColor(job.status) }} />
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                [{job.provider}] {statusText(job.status)}
                {job.status === 'failed' && job.error ? ` · ${job.error}` : ` · ${job.message}`}
              </span>
              <span style={{ color: 'var(--text-faint)' }}>
                {job.progress}%
                {job.durationMs != null && ` · ${(job.durationMs / 1000).toFixed(1)}s`}
              </span>
              {canRetry(job.status) && (
                <button className="btn btn--sm" onClick={() => retryJob(job.id)}>
                  重试
                </button>
              )}
            </div>
          ))}
      </div>
    </footer>
  )
}
