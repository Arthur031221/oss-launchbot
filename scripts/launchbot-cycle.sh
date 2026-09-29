#!/bin/zsh
set -eu

if [[ $# -ne 1 ]]; then
  print -u2 'usage: launchbot-cycle.sh WORKSPACE'
  exit 2
fi

workspace=$1
repo_dir=${0:A:h:h}
export PATH="/opt/homebrew/bin:$PATH"
export PYTHONPATH="$repo_dir"
private_config="$HOME/.config/oss-launchbot/reddit.env"
if [[ -f "$private_config" ]]; then
  permissions=$(/usr/bin/stat -f '%Lp' "$private_config")
  if [[ "$permissions" != "600" ]]; then
    print -u2 'reddit.env must have permission mode 600'
    exit 1
  fi
  source "$private_config"
fi
python3 -m oss_launchbot.cli --workspace "$workspace" refresh
python3 -m oss_launchbot.cli --workspace "$workspace" run-due --live
