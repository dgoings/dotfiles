# dotfiles

Personal dotfiles managed with [GNU Stow](https://www.gnu.org/software/stow/).

## Packages

| Package     | Config                                        |
| ----------- | --------------------------------------------- |
| `aerospace` | AeroSpace tiling window manager               |
| `btop`      | btop resource monitor                         |
| `claude`    | Claude Code settings, commands, skills        |
| `ghostty`   | Ghostty terminal                              |
| `git`       | Git global config                             |
| `home`      | Misc files that live directly in `$HOME`      |
| `karabiner` | Karabiner-Elements key remapping              |
| `lazygit`   | lazygit config                                |
| `nvim`      | Neovim (LazyVim)                              |
| `starship`  | Starship prompt                               |
| `tmux`      | tmux config                                   |
| `zsh`       | zshrc, zprofile, fzf integration              |

## Claude Code mode toggle

`claude-mode` controls whether Claude Code can run `git commit` autonomously.

```sh
claude-mode           # show current mode (control or trust)
claude-mode control   # block git commit (default)
claude-mode trust     # allow git commit
```

In control mode, Claude Code's UI prompts for approval on each commit. In trust mode, commits are auto-approved.

## New machine setup

```sh
# Prerequisites
brew install stow

# Clone
git clone <repo-url> ~/dotfiles

# Symlink everything
cd ~/dotfiles && stow */
```

## Day-to-day usage

Edit files in `~/dotfiles/<package>/` directly — symlinks mean changes take effect immediately.

```sh
# Add a new dotfile to an existing package
mv ~/.some-new-config ~/dotfiles/zsh/.some-new-config
stow --restow zsh

# Restow all packages (e.g. after pulling changes)
cd ~/dotfiles && stow */

# Remove symlinks for a package
stow -D <package>
```
