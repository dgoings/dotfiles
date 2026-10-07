export type RateWindow = { kind: string; percentUsed: number; resetsAt?: string }

/** The Fable scan's result: dollar spend by Fable and by every model since the weekly window opened. */
export type Spend = { fable: number; all: number }

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
