export type RateWindow = { kind: string; percentUsed: number; resetsAt?: string }

/** The Fable scan's result: dollar spend by Fable and by every model since the weekly window opened. */
export type Spend = { fable: number; all: number }

/** One rate-limit window as the usage service reports it. */
export type ServiceWindow = { percentUsed: number; resetsAt?: string }

/** The usage service's answer, read at `at` (epoch ms); a gauge the answer did not carry is null. */
export type ServiceReading = { at: number; five: ServiceWindow | null; week: ServiceWindow | null; fable: number | null }

export type Snapshot = {
  model: string
  rateLimits: RateWindow[]
  spend: Spend | null
  /** Milliseconds since the epoch at the last tick: the pace references and reset clocks read it. */
  now: number
}

declare module 'claude-code' {
  interface PluginState {
    'usage-line': { snapshot: Snapshot | null }
  }
}
