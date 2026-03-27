if status is-interactive
  fish_vi_key_bindings
end
export PATH="$HOME/.local/bin:$PATH"

# bun
set --export BUN_INSTALL "$HOME/.bun"
set --export PATH $BUN_INSTALL/bin $PATH

# nvm
set --universal nvm_default_version v18.4.0