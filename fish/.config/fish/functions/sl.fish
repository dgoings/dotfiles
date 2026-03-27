function sl --description 'Smart ls - short or long listing based on file count'
    clear; pwd
    if test (ls -a $argv | wc -l) -lt 20
        ls -lahG $argv
    else
        ls -ahG $argv
    end
end
