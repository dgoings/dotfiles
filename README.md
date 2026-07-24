# dotfiles

Personal dotfiles managed with [GNU Stow](https://www.gnu.org/software/stow/).

## Packages

| Package  | Config                                                  |
| -------- | ------------------------------------------------------- |
| `claude` | Claude Code `settings.json` and global `CLAUDE.md`      |
| `fish`   | fish shell — vi keybinds, abbreviations, fisher plugins |
| `git`    | `.gitconfig` and `.githelpers`                          |
| `tmux`   | `.tmux.conf` — `C-g` prefix, vim pane navigation        |
| `zsh`    | `.zshrc` (oh-my-zsh)                                    |

## New machine setup

```sh
# Prerequisites
brew install stow

# Clone
git clone https://github.com/dgoings/dotfiles.git ~/source/dotfiles

# Symlink everything
cd ~/source/dotfiles && stow */
```

**Run stow from the repo root.** Stow's default target is the *parent* of the stow directory,
not `$HOME`. The repo-local `.stowrc` sets `--target=~` to fix this, but stow only reads it
when invoked from this directory — run it elsewhere and the symlinks land in the wrong place
with no error.

If a package refuses to stow, it's because a real file already exists at one of its target
paths. Stow aborts the *whole* package on a single conflict, so one stray file blocks every
other link. Preview with `stow -n -v <package>`, move the offending file aside, then retry.

## Machine-local config

`.zshrc` sources `~/.zshrc.local` if it exists. Put API keys, credentials, and per-machine
overrides there — it lives in `$HOME`, is not a stow package, and is never tracked by git.

## Day-to-day usage

Edit files in `~/source/dotfiles/<package>/` directly — symlinks mean changes take effect
immediately.

```sh
# Add a new dotfile to an existing package
mv ~/.some-new-config ~/source/dotfiles/zsh/.some-new-config
stow --restow zsh

# Restow all packages (e.g. after pulling changes)
cd ~/source/dotfiles && stow */

# Remove symlinks for a package
stow -D <package>
```
