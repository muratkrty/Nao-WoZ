#!/usr/bin/env bash
# Launch NAO WoZ.  Usage:  ./run.sh [--mock] [--ip 192.168.1.42 --autoconnect] [--port 8000]
cd "$(dirname "$0")"
eval "$(conda shell.bash hook)"
conda activate nao_woz
exec python server.py "$@"
