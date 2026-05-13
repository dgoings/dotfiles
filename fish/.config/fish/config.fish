if status is-interactive
  fish_vi_key_bindings
  bind -M insert \e\x7f backward-kill-word
end
export PATH="$HOME/.local/bin:$PATH"

# bun
set --export BUN_INSTALL "$HOME/.bun"
set --export PATH $BUN_INSTALL/bin $PATH

# nvm
set --universal nvm_default_version 25
# pnpm
set -gx PNPM_HOME "/Users/dylan.goings/Library/pnpm"
if not string match -q -- "$PNPM_HOME/bin" $PATH
  set -gx PATH "$PNPM_HOME/bin" $PATH
end
# pnpm end

# Java
echo 'set -gx JAVA_HOME "/Applications/Android Studio.app/Contents/jbr/Contents/Home"' >> ~/.config/fish/config.fish
fish_add_path $JAVA_HOME/bin
set -gx JAVA_HOME "/Applications/Android Studio.app/Contents/jbr/Contents/Home"
set -gx JAVA_HOME "/Applications/Android Studio.app/Contents/jbr/Contents/Home"
set -gx JAVA_HOME "/Applications/Android Studio.app/Contents/jbr/Contents/Home"
