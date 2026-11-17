# Dotfiles Repo

## Architecture

This repo uses [GNU Stow](https://www.gnu.org/software/stow/) for symlink management. Each top-level directory is a Stow package. Running `stow <package>` symlinks its contents into `$HOME`. Edits inside `~/dotfiles/<package>/` take effect immediately via the symlinks — no copy or re-install needed.

To re-symlink everything: `stow */`
To re-symlink a single package: `stow --restow <package>`

**Always run stow from the repo root.** Stow's default target is the *parent* of the stow
directory (`~/source/`), not `$HOME`. The repo-local `.stowrc` sets `--target=~` to correct
this, but it is only read when stow is invoked from this directory. Run stow from anywhere
else and the symlinks land in the wrong place, silently.

Stow aborts the *entire* package on a single conflict, so a pre-existing real file at a
target path (e.g. a stock `~/.config/fish/config.fish`) blocks every other link in that
package. Use `stow -n -v <package>` to preview and surface conflicts; move the offending
file aside, then stow again.

## Path Convention

Files must mirror their destination path inside the package directory.

Example: `~/.config/fish/config.fish` lives at `fish/.config/fish/config.fish` in this repo.

## Packages

| Package | Destination  | Notes                                                            |
|---------|--------------|------------------------------------------------------------------|
| claude  | `~/.claude/` | Claude Code `settings.json`, global `CLAUDE.md`, and `mods/usage-line` (see below) |
| fish    | `~/.config/` | fish shell — vi keybinds, abbrs, fisher plugins (fzf, nvm)       |
| ghostty | `~/Library/Application Support/com.mitchellh.ghostty/` | Ghostty — Abernathy theme, JuliaMono font (`brew install --cask font-juliamono`) |
| git     | `~/`         | `.gitconfig` and `.githelpers`                                   |
| talon   | `~/.talon/user/dylan/` | Talon user scripts — Ulanzi AU05 remote, listening mode, Rango toggle (see below) |
| tmux    | `~/`         | `.tmux.conf` — `C-g` prefix, vim pane nav, 256-colour status bar |
| zsh     | `~/`         | `.zshrc` (oh-my-zsh)                                             |

## Conventions

- **Navigation**: vim-style keybinds — `h/j/k/l` pane movement in tmux, vi mode in both shells
- **Portability**: use `$HOME`, never a hardcoded `/Users/<name>`. The repo is shared across
  machines whose usernames differ, and hardcoded paths silently break on the other machine.
- **Secrets stay out of the repo.** `.zshrc` sources `~/.zshrc.local` if it exists; keep API
  keys, tokens, and credentials there. It lives in `$HOME`, is not a stow package, and is
  therefore never tracked.

## Claude Code usage-line mod

`claude/.claude/mods/usage-line/` is a Claude Code mod (a plugin of function hooks) that
draws the model, the 5h/7d rate-limit usage with pace references, and an estimated Fable
share of the weekly limit in the band above the prompt. It replaced the old
`statusline.sh`. `settings.json` loads it through `env.CLAUDE_CODE_PLUGIN_DIRS`; edits
hot-reload in a running interactive session. Its README holds the Fable calibration notes.
Check it with `claude plugin validate` and `claude plugin test` from the mod folder. The
engine lays `.claude-plugin/types/` and a `tsconfig.json` beside a loaded mod; both are
gitignored.

## Claude Code settings.json drift

`claude/.claude/settings.json` is a **live runtime file**, not a static config. Claude Code
rewrites it whenever you run `/model`, `/effort`, or a `/config` toggle, and when it stamps
`feedbackSurveyState`. Because the path is stowed, those writes land straight in the repo and
used to dirty the tree constantly — blocking `git rebase --continue` with the misleading error
`You must edit all merge conflicts and then mark them as resolved using git add`.

Claude Code cannot split this: the settings cascade is
`~/.claude/settings.json` (user) → `.claude/settings.json` (project) → `.claude/settings.local.json`
(local), and the `.local.json` variant exists **only at repo scope**. `/model` and `/effort`
always write user settings. So the fix lives in git, in two parts:

1. **Clean filter** (`.gitattributes` + `[filter "claude-settings"]` in `git/.gitconfig`) —
   sorts keys and strips `model`, `effortLevel`, `feedbackSurveyState` on the way *into* git,
   so the committed base is stable and free of per-machine values.
2. **`skip-worktree`** — local, per-clone index bit that makes git ignore worktree edits
   entirely. Needed *in addition* to the filter: the filter normalizes content, but stat-based
   checks (`git diff-files`, which is what rebase's dirty check uses) still flag the file until
   a `git add` refreshes the stat cache. The harness re-dirties it immediately, so the filter
   alone does not unblock rebases.

**Per-machine bootstrap** (the skip-worktree bit is not carried by clones):

```
git lock claude/.claude/settings.json
```

**To intentionally update the committed base** (e.g. after adding a plugin or hook):

```
git unlock claude/.claude/settings.json
git add claude/.claude/settings.json   # filter normalizes it
git commit
git lock claude/.claude/settings.json
```

`git locked` lists every skip-worktree file. If a settings change you made seems not to be
committable, this bit is why.

## Talon package

`talon/.talon/user/dylan/` is the Talon user folder: Ulanzi AU05 remote controls, listening
mode (Claude Code replies spoken aloud), the Rango on/off toggle, and spoken app names. Talon
reloads files the moment they change, so edits here take effect at once.

- **Stow it as one folder link.** `~/.talon/user` must exist as a real folder before
  `stow talon`, so stow links just `~/.talon/user/dylan`. Without it, stow links all of
  `~/.talon` into this repo and Talon's logs and runtime files land here.
- **`community` and `rango-talon` aren't in this repo.** They are their own git clones in
  `~/.talon/user/`. Don't edit them: put overrides in this package instead (for example
  `apps/app_names.py` supplies the app-switcher names community would read from its CSV).
- **Ignored, machine-local files** live inside the package: `.venv/` (pytest, for the tests)
  and `.listening/tts/venv/` (the Kokoro voice, made by `.listening/tts/setup.sh`). Its
  `.gitignore` keeps them out of git.
- **Tests:** unlike the rest of the repo, this package has some. Run
  `.venv/bin/python -m pytest -q .tests` from the package folder.
- **Older history** comes from the folder's own repo, merged in by commit `b9a1d03`. Those
  commits use paths relative to the folder, so `git log -- talon/` stops at the merge; read
  them with `git log b9a1d03^2`.

## Working in this Repo

There are no build, test, or lint commands. Validation is manual: open the relevant tool and verify the config works as expected.

When adding new dotfiles:

1. Identify the correct destination path (e.g., `~/.config/foo/bar`)
2. Create the mirrored structure under the appropriate package dir (e.g., `foo/.config/foo/bar`)
3. Run `stow foo` to create the symlink

Setup from scratch: `brew install stow && stow */`

On a machine that already has real config files in place, stow will refuse to overwrite them.
Move the existing file aside first, then stow — see the conflict note under Architecture.
