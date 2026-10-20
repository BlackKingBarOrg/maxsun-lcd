#!/usr/bin/env bash
#
# Install the parts that run as you, or reload them after an edit:
#
#   ./install.sh
#
# - the `maxsun-lcd` command (editable uv tool, so ~/.local/bin follows this checkout)
# - the maxsun-lcd systemd user service, (re)started
# - the ai.bkblab.maxsun-lcd bar widget: a symlink to bar/, put after mytop
#
# The udev rule that lets you open the panel needs root; see README.

set -euo pipefail

CLONE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
PLUGIN="$CONFIG/omarchy/plugins/ai.bkblab.maxsun-lcd"
UNIT="$CONFIG/systemd/user/maxsun-lcd.service"

uv tool install --quiet --editable --force "$CLONE"

if [[ "$(readlink "$UNIT" 2>/dev/null)" != "$CLONE/systemd/maxsun-lcd.service" ]]; then
  systemctl --user link "$CLONE/systemd/maxsun-lcd.service"
fi
systemctl --user daemon-reload
systemctl --user enable --quiet maxsun-lcd.service
systemctl --user restart maxsun-lcd.service

if [[ -e "$PLUGIN" && ! -L "$PLUGIN" ]]; then
  echo "$PLUGIN is a real folder, not a link; move it away first" >&2
  exit 1
fi
if [[ "$(readlink "$PLUGIN" 2>/dev/null)" == "$CLONE/bar" ]] && grep -q '"ai.bkblab.maxsun-lcd"' "$CONFIG/omarchy/shell.json" 2>/dev/null; then
  # The shell's watcher does not descend through the symlink; a restart is
  # what picks up edits to bar/.
  omarchy restart shell
else
  ln -sfn "$CLONE/bar" "$PLUGIN"
  omarchy-shell -q shell rescanPlugins
  grep -q '"ai.bkblab.maxsun-lcd"' "$CONFIG/omarchy/shell.json" 2>/dev/null \
    || omarchy bar put ai.bkblab.maxsun-lcd --after ai.bkblab.mytop
fi

echo "installed; images go in ${MAXSUN_LCD_ROOT:-$HOME/Pictures/MaxsunLCD}/inbox"
