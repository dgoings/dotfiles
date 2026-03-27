# If you come from bash you might have to change your $PATH.
# export PATH=$HOME/bin:/usr/local/bin:$PATH

# Path to your oh-my-zsh installation.
export ZSH=/Users/dylan/.oh-my-zsh

# Set name of the theme to load. Optionally, if you set this to "random"
# it'll load a random theme each time that oh-my-zsh is loaded.
# See https://github.com/robbyrussell/oh-my-zsh/wiki/Themes
ZSH_THEME="gallifrey"

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion. Case
# sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment the following line to disable bi-weekly auto-update checks.
# DISABLE_AUTO_UPDATE="true"

# Uncomment the following line to change how often to auto-update (in days).
# export UPDATE_ZSH_DAYS=13

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
# ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
# DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# The optional three formats: "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# Which plugins would you like to load? (plugins can be found in ~/.oh-my-zsh/plugins/*)
# Custom plugins may be added to ~/.oh-my-zsh/custom/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
plugins=(git vi-mode vscode bun deno dotenv macos nvm pip direnv jump)

# Custom env file for dotenv plugin 
ZSH_DOTENV_FILE=.env.local

source $ZSH/oh-my-zsh.sh
VI_MODE_SET_CURSOR=true

# User configuration

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='mvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch x86_64"

# ssh
# export SSH_KEY_PATH="~/.ssh/dsa_id"

# Set personal aliases, overriding those provided by oh-my-zsh libs,
# plugins, and themes. Aliases can be placed here, though oh-my-zsh
# users are encouraged to define aliases within the ZSH_CUSTOM folder.
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"

# zshrc reloading
alias reload!='source ~/.zshrc'

# 10ms for key sequences
KEYTIMEOUT=1

# butterfish shell alias
alias bf="butterfish shell"

# jump plugin alias
alias j=jump
# colors
export LSCOLORS="exfxcxdxbxegedabagacad"
export CLICOLOR=true

# sensible ls
alias ls="ls -hG"
alias l="ls -a"
alias ll="ls -la"
alias x="clear"

function aps_smart_ls {
  clear && pwd
  if [[ `ls -a $* | wc -l` -lt 20 ]]; then
    ll $*
  else
    l $*
  fi
}
alias sl=aps_smart_ls

# navigation
function aps_pushd {
  pushd $1 && aps_smart_ls
}
alias o=aps_pushd

function aps_popd {
  popd && aps_smart_ls
}
alias p=aps_popd

function listening {
  lsof -i -n -P | grep --color=auto \
    --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox} TCP | \
    grep --color=auto --exclude-dir={.bzr,CVS,.git,.hg,.svn,.idea,.tox} LISTEN
}

# git
alias g=git

# python aliases
alias python=python3
alias pip=pip3
alias pyvc="python -m venv .venv/"
alias pyva="source .venv/bin/activate"

# bun completions
[ -s "/Users/dylan/.bun/_bun" ] && source "/Users/dylan/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
alias b=bun

# deno
export DENO_INSTALL="/Users/dylan/.deno"
export PATH="$DENO_INSTALL/bin:$PATH"

# supabase
alias sb=supabase

# Android
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export ANDROID_HOME=$HOME/Library/Android/sdk
export NDK_HOME="$ANDROID_HOME/ndk/$(ls $ANDROID_HOME/ndk | tail -n 1)"
export PATH=$PATH:$ANDROID_HOME/emulator
export PATH=$PATH:$ANDROID_HOME/platform-tools

# The following lines have been added by Docker Desktop to enable Docker CLI completions.
fpath=(/Users/dylan/.docker/completions $fpath)
autoload -Uz compinit
compinit
# End of Docker CLI completions

# Load Angular CLI autocompletion.
source <(ng completion script)

export WASMTIME_HOME="$HOME/.wasmtime"

export PATH="$WASMTIME_HOME/bin:$PATH"

# Turso
export PATH="$PATH:/Users/dylan/.turso"
