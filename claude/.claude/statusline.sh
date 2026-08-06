#!/usr/bin/env bash
# Claude Code status line: model + rate-limit usage (the same numbers /usage shows)
# + Fable tokens used today.
# Receives session JSON on stdin; rate_limits fields appear after the first API
# response in a session (Pro/Max only). Docs: https://code.claude.com/docs/en/statusline
set -euo pipefail

input=$(cat)

model=$(jq -r '.model.display_name // empty' <<<"$input")
five=$(jq -r '.rate_limits.five_hour.used_percentage // empty' <<<"$input")
week=$(jq -r '.rate_limits.seven_day.used_percentage // empty' <<<"$input")
reset=$(jq -r '.rate_limits.five_hour.resets_at // empty' <<<"$input")

# Colorize a used-percentage: green < 50, yellow < 80, red >= 80.
pct() {
  local n
  n=$(printf '%.0f' "$1")
  if [ "$n" -ge 80 ]; then printf '\033[31m%s%%\033[0m' "$n"
  elif [ "$n" -ge 50 ]; then printf '\033[33m%s%%\033[0m' "$n"
  else printf '\033[32m%s%%\033[0m' "$n"
  fi
}

# Fable weekly usage, as an estimated percentage of the plan's Fable sub-limit.
# /usage shows this as a third bar ("Current week (Fable)") but rate_limits
# carries no per-model buckets, so it is reconstructed here: sum Fable token
# spend since the weekly reset, price it at list rates, and divide by a
# calibrated budget.
#
# Cost, not token count, is the basis. Raw input+output is under 1% of the
# tokens actually metered — cache reads outnumber it ~100:1 — so a token-based
# estimate tracks nothing useful.
#
# Calibrated 2026-08-06: $178.13 of Fable spend showed as 17% on the /usage bar,
# giving the budget below. Cross-checked the same day against the all-models bar
# ($926.02 -> 29% -> $3193), which puts the Fable sub-limit at ~33% of the weekly
# allowance; two independently derived budgets forming a clean ratio is the
# evidence that metering tracks cost.
#
# Recalibrate when this drifts from /usage: read both numbers, then set
# FABLE_WEEKLY_BUDGET to (reported cost / reported fraction). Expect drift when
# the +50% weekly-limits promo ends (2026-08-19) or plan limits change. Counts
# local transcripts only, so usage from other devices or claude.ai is missing.
FABLE_WEEKLY_BUDGET=1047.81 # dollars of Fable spend per weekly window
FABLE_RESET_DOW=4           # Thursday, matching `date +%u` (1=Mon)
FABLE_RESET_HOUR=17         # 5pm, local

# Start of the current weekly window. Derived from the local calendar rather
# than by subtracting 604800 seconds, so a DST change doesn't walk the boundary
# an hour off.
days_back=$((($(date +%u) - FABLE_RESET_DOW + 7) % 7))
if [ "$days_back" -eq 0 ] && [ "$((10#$(date +%H)))" -lt "$FABLE_RESET_HOUR" ]; then
  days_back=7
fi
window_start=$(printf '%s %02d:00:00' "$(date -v-${days_back}d +%F)" "$FABLE_RESET_HOUR")
window_epoch=$(date -j -f '%Y-%m-%d %H:%M:%S' "$window_start" +%s)

cache="${TMPDIR:-/tmp}/claude-statusline-fable.$(id -u)"
cost=""

# Cache line is "<epoch> <window> <cost>"; reuse while same-window and fresh.
if [ -r "$cache" ]; then
  read -r cached_at cached_window cached_cost <"$cache" 2>/dev/null || true
  if [[ ${cached_at:-} =~ ^[0-9]+$ ]] && [ "${cached_window:-}" = "$window_epoch" ] &&
    [ $(($(date +%s) - cached_at)) -lt 120 ]; then
    cost=${cached_cost:-}
  fi
fi

if [ -z "$cost" ]; then
  transcripts=()
  while IFS= read -r -d '' t; do transcripts+=("$t"); done < <(
    find "$HOME/.claude/projects" -name '*.jsonl' -newermt "$window_start" -print0 2>/dev/null
  )

  cost=0
  if [ ${#transcripts[@]} -gt 0 ]; then
    # Read as raw lines and parse each individually: a transcript truncated
    # mid-write leaves a partial final line, and letting jq parse the file as
    # JSON would abort the whole scan on it and silently report zero.
    #
    # Timestamps are UTC with fractional seconds, which fromdateiso8601 rejects
    # outright, so strip the fraction before comparing against the window.
    # Subagent transcripts live in subagents/ subdirectories and are counted too
    # — they are a large share of real usage.
    cost=$(jq -rR --argjson since "$window_epoch" '
      fromjson?
      | objects
      | select(.type == "assistant")
      | select((.message.model // "") | startswith("claude-fable"))
      | select((((.timestamp // "") | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601?) // 0) >= $since)
      | (.message.usage // {}) as $u
      | [ ($u.input_tokens // 0), ($u.output_tokens // 0), ($u.cache_read_input_tokens // 0),
          ($u.cache_creation.ephemeral_5m_input_tokens // 0),
          ($u.cache_creation.ephemeral_1h_input_tokens // 0) ] | @tsv
    ' "${transcripts[@]}" 2>/dev/null |
      # Fable 5 list rates per MTok: input $10, output $50, cache read $1,
      # 5m cache write $12.50, 1h cache write $20.
      awk -F'\t' '{ i += $1; o += $2; r += $3; w5 += $4; w1 += $5 }
        END { printf "%.4f", (i * 10 + o * 50 + r * 1 + w5 * 12.5 + w1 * 20) / 1e6 }') || cost=0
  fi
  # stderr is redirected first so a failed open on $cache stays quiet too;
  # bash applies redirections left to right and reports the failure itself.
  printf '%s %s %s\n' "$(date +%s)" "$window_epoch" "$cost" 2>/dev/null >"$cache" || true
fi

fable=$(awk -v c="$cost" -v b="$FABLE_WEEKLY_BUDGET" \
  'BEGIN { if (b > 0) printf "%.0f", 100 * c / b; else print 0 }' 2>/dev/null) || fable=0

out="${model:-Claude}"
[ -n "$five" ] && out+=" | 5h $(pct "$five")"
if [[ "$reset" =~ ^[0-9]+$ ]]; then
  out+=" (resets $(date -r "$reset" +%H:%M))"
fi
[ -n "$week" ] && out+=" | 7d $(pct "$week")"
# Tilde marks this as a local estimate, not a figure the API reported.
case $fable in
'' | 0 | *[!0-9]*) ;;
*) out+=" | Fable ~$(pct "$fable")" ;;
esac

printf '%s\n' "$out"
