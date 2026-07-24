if status is-interactive
  fish_vi_key_bindings
  bind -M insert \e\x7f backward-kill-word
end

fish_add_path -g $HOME/.local/bin

# bun
set --export BUN_INSTALL "$HOME/.bun"
fish_add_path -g $BUN_INSTALL/bin

# nvm
set --universal nvm_default_version 25

# pnpm
set -gx PNPM_HOME "$HOME/Library/pnpm"
fish_add_path -g $PNPM_HOME/bin

# Java (Android Studio's bundled JBR)
set -l jbr "/Applications/Android Studio.app/Contents/jbr/Contents/Home"
if test -d $jbr
  set -gx JAVA_HOME $jbr
  fish_add_path -g $JAVA_HOME/bin
end
set -gx ANDROID_HOME "$HOME/Library/Android/sdk"
set -gx ANDROID_SDK_ROOT $ANDROID_HOME
fish_add_path $ANDROID_HOME/platform-tools $ANDROID_HOME/emulator $ANDROID_HOME/cmdline-tools/latest/bin
