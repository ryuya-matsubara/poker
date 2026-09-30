#!/usr/bin/env bash
set -euo pipefail
# Only ephemeral GitHub-hosted runner SDKs, never repository/user data.
sudo rm -rf /usr/local/lib/android /usr/share/dotnet /opt/ghc /usr/share/swift
free_kb=$(df --output=avail -k / | tail -1)
if [ "$free_kb" -lt 46137344 ]; then
  echo 'Need at least 44GiB free disk for 40GiB swap and artifacts' >&2
  df -h /
  exit 1
fi
sudo fallocate -l 40G /swap-poker-cfr
sudo chmod 600 /swap-poker-cfr
sudo mkswap /swap-poker-cfr
sudo swapon /swap-poker-cfr
free -h
df -h /
