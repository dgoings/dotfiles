# usage-line

A Claude Code mod that draws, in the band above the prompt:

```
Fable 5.1 | 5h 24%/60% (resets 15:00) | 7d 44%/50% | Fable ~36%
```

- the model, as `/model` shows it;
- the 5-hour and 7-day rate-limit windows, the same numbers `/usage` shows, coloured
  green under 50%, yellow under 80%, red from 80%;
- after each, dim, the **pace reference**: the elapsed share of the window, i.e. where
  usage would sit if the whole allowance were burned evenly. Usage above it is running
  hot; below it is banked room;
- an **estimate** of the Fable share of the weekly limit (the third bar `/usage` draws as
  "Current week (Fable)"). The tilde marks it as a local estimate, not a figure the API
  reported.

The rate-limit figures are pushed by the engine (`session.measure`), so nothing is
polled. A one-minute tick keeps the pace references and reset clock moving between
turns.

## Loading

The mod is stowed to `~/.claude/mods/usage-line` and named in the `env` block of
`~/.claude/settings.json`:

```json
"env": { "CLAUDE_CODE_PLUGIN_DIRS": "~/.claude/mods/usage-line" }
```

Edits to the folder hot-reload in an interactive session. `claude plugin validate`,
`claude plugin test` and `tsc -p` (once the engine has laid `.claude-plugin/types/`)
check it.

## The Fable estimate

`rate_limits` carries no per-model buckets, so the Fable bar is reconstructed from the
local transcripts under `~/.claude/projects`.

Cost, not token count, is the basis. Raw input+output is under 1% of the tokens
actually metered (cache reads outnumber it ~100:1), so a token-based estimate tracks
nothing useful.

The estimate is a *ratio*, not a dollar budget. The transcripts give Fable spend and
all-model spend since the weekly reset; the API reports the exact all-model percentage:

    fable% = 7d% x (fable spend / all spend) / fableShare

The dollar amounts cancel, which is the point: the weekly allowance is never
hardcoded, so a plan change, a limits promo or a price change recalibrates on the next
render instead of silently drifting. Only the ratio of Fable to non-Fable spend has to
be right, and only the sub-limit fraction below is a fixed assumption.

Counting only local transcripts still biases this, but far less than a fixed budget
did: usage from another device is missing from both numerator and denominator, so a
machine used similarly for Fable and non-Fable work largely cancels its own bias out. A
machine used lopsidedly does not, and the residual bias is folded into the constant
rather than modelled.

One API response can appear many times in the transcripts: streaming writes a row per
progress snapshot, and resuming or forking a session copies the whole transcript into a
new file. Rows are folded by message id (input and cache counts once, the largest
output) before pricing; summing them inflated cache reads by the row count and
corrupted every calibration made before the fix.

### `fableShare`

The Fable sub-limit as a fraction of the plan's weekly allowance, a `userConfig`
option (default `0.40`): set it in `/config` or under `pluginConfigs` in settings. It is
plan-level, which rests on one assumption: the Fable/non-Fable usage mix is roughly
similar across this account's machines. The `/usage` percentages are account-global;
the transcript scan is local to one machine.

**Calibration recipe.** Compare against `/usage` while the 7d bar itself is accurate,
then:

    new = current x (rendered fable % / usage fable %)

Recalibrate after a plan change or limits promo change, and prefer readings late in the
weekly window: `/usage` rounds to whole percents, so small bars make the correction
factor noisy.

**Calibration log** ($200 Max plan; promo status unverified):

- 2026-08-08: four readings implied a share near 1.0, i.e. the Fable bar sharing the
  weekly allowance outright. All four are void: the scan was summing duplicate rows, and
  the duplication was heavier on Fable than on the rest.
- 2026-08-11: first reading after deduplicating: 7d 44%, Fable 36%, local ratio 0.327,
  implied share 0.40 (rounding bounds 0.39-0.41). The bars were large enough that
  rounding leaves little slack, so this is the first calibration worth trusting.

## Clock

With `clockUrl` set, the mod also mirrors the gauges on a Ulanzi TC002 desk clock
(52x16 pixels, stock firmware):

```
5H 24%            7D 44%          rows 0-4   label grey, percentage in tier colour
██████┆░░░░░░░░   ███████████┆░░  rows 6-8   two bars, 25 px each, at x=0 and x=27
FB ~36%   ██████████░░░░░░░░░░░░  rows 11-15 text, then a 3 px bar (rows 12-14) to the right edge
```

The colours and pace marks are the band's; the Fable row has no pace mark, as in the
terminal, and is blank when there is no estimate.

The screen is the clock's custom app named `usage`, sent as one full-screen bitmap to
`POST <clockUrl>/api/custom?name=usage`. It takes its turn in the clock's app rotation;
the mod never switches the clock to it and calls no other endpoint.

To turn it on, set `clockUrl` to the clock's base URL, e.g. `http://192.168.1.58`, in
`/config` or under `pluginConfigs` in settings. Empty (the default), or anything that is
not an `http://` or `https://` URL, leaves the mod making no request at all.

A frame is pushed when a session starts, on every `session.measure` and on every
one-minute tick, with a `duration` of 180 seconds (three ticks), so the screen updates
only while a session is open.

An unreachable clock is ignored: a push is never awaited by a hook, every failure is
swallowed, and while one push is still pending the next is skipped, until it has been
pending for 10 seconds.

## Files

- `hooks/register.tsx`: the hooks (`session.start`, `session.measure`,
  `classic.PostModelSwitch`, `ui.render` on `AbovePrompt`), the scan's cache and the
  clock push.
- `hooks/clock.ts`: the gauges as a 52x16 clock frame, and its request body.
- `hooks/usage.ts`: the pure parts: pace, tiers, the weekly window, pricing, and the
  `find | jq` argument vector.
- `hooks/usage-line.test.ts`, `hooks/clock.test.ts`: `claude plugin test .`
- `types/index.d.ts`: the `$.state` contract.
