# Dotfiles Repo

## Architecture

This repo uses [GNU Stow](https://www.gnu.org/software/stow/) for symlink management. Each top-level directory is a Stow package. Running `stow <package>` symlinks its contents into `$HOME`. Edits inside `~/dotfiles/<package>/` take effect immediately via the symlinks — no copy or re-install needed.

To re-symlink everything: `stow */`
To re-symlink a single package: `stow --restow <package>`

## Path Convention

Files must mirror their destination path inside the package directory.

Example: `~/.config/ghostty/config` lives at `ghostty/.config/ghostty/config` in this repo.

## Packages

| Package    | Destination                      | Notes                                                         |
|------------|----------------------------------|---------------------------------------------------------------|
| aerospace  | `~/`                             | AeroSpace tiling window manager                               |
| btop       | `~/.config/`                     | btop resource monitor — Catppuccin Mocha theme, vim keys      |
| claude     | `~/.claude/`                     | Claude Code settings, commands, skills, status line script    |
| ghostty    | `~/.config/`                     | Ghostty terminal emulator                                     |
| git        | `~/`                             | `.gitconfig`                                                  |
| home       | `~/`                             | Misc files that live directly in `$HOME`                      |
| karabiner  | `~/.config/`                     | Karabiner-Elements complex modifications (Caps Lock → Ctrl+B) |
| lazygit    | `~/Library/Application Support/` | lazygit — Catppuccin Mocha theme, Nerd Font v3 icons          |
| nvim       | `~/.config/`                     | Neovim — LazyVim starter; extras in `lazyvim.json`            |
| starship   | `~/.config/`                     | Starship prompt                                               |
| tmux       | `~/`                             | TPM config — vim-tmux-navigator + Catppuccin Mocha theme      |
| zsh        | `~/`                             | `.zshrc` and related shell config                             |

## Cross-Cutting Conventions

- **Theme**: Catppuccin Mocha across all tools — ghostty, tmux, btop, lazygit, nvim
- **Navigation**: vim-style keybinds everywhere; `Ctrl-h/j/k/l` bridges nvim↔tmux pane boundaries
- **Font**: JetBrainsMono Nerd Font (configured in ghostty)

## Working in this Repo

There are no build, test, or lint commands. Validation is manual: open the relevant tool and verify the config works as expected.

When adding new dotfiles:

1. Identify the correct destination path (e.g., `~/.config/foo/bar`)
2. Create the mirrored structure under the appropriate package dir (e.g., `foo/.config/foo/bar`)
3. Run `stow foo` to create the symlink

Setup from scratch: `brew install stow && stow */`

## Tmux IDE Layout (`dev` Command)

Full documentation: [docs/dev-layout.md](docs/dev-layout.md)
