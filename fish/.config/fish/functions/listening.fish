function listening --description 'Show listening TCP ports'
    lsof -i -n -P | grep TCP | grep LISTEN
end
