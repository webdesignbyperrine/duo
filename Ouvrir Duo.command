#!/bin/zsh
cd "${0:A:h}"
export PATH="$HOME/.local/bin:$PATH"
python3 server.py &
DUO_SERVER_PID=$!
trap 'kill "$DUO_SERVER_PID" 2>/dev/null' EXIT INT TERM
sleep 1
open 'http://127.0.0.1:8786/launch'
echo 'Duo est ouvert dans votre navigateur. Gardez cette fenêtre ouverte pendant la discussion.'
wait "$DUO_SERVER_PID"
