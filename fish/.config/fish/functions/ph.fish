function ph --description 'SSH to ao-laptop and attach to a tmux session'
    set -l session main
    if set -q argv[1]
        set session $argv[1]
    end
    ssh -t "Dylan Goings"@ao-laptop "tmux new-session -A -s '$session'"
end
