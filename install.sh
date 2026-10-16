#!/usr/bin/env bash
# Per-user install of Pelta Control. Needs python + pyside6 (pacman -S pyside6).
# The udev rule is the only root step; it is printed at the end if missing.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/pelta-control"
RULE=/etc/udev/rules.d/70-rog-pelta.rules

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -rf "$DEST"
    rm -f "$HOME/.local/bin/pelta-control" \
          "$HOME/.local/share/applications/pelta-control.desktop" \
          "$HOME/.local/share/icons/hicolor/scalable/apps/pelta-control.svg" \
          "$HOME/.config/autostart/pelta-control.desktop"
    echo "Removed. To drop device access too: sudo rm $RULE"
    exit 0
fi

python3 -c 'import PySide6' 2>/dev/null || { echo "PySide6 missing: sudo pacman -S pyside6"; exit 1; }

rm -rf "$DEST"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications" \
         "$HOME/.local/share/icons/hicolor/scalable/apps" "$HOME/.config/autostart"
cp -r "$SRC/pelta" "$SRC/icons" "$SRC/pelta-control" "$DEST/"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +

# ASUS-owned ROG font + headset art: taken from a local ROG PELTA package, never shipped
mkdir -p "$DEST/assets"
if [[ -d "$SRC/assets" ]]; then
    cp "$SRC"/assets/* "$DEST/assets/"
else
    RES=$(find "$HOME/Downloads" -maxdepth 6 -type d -path '*ROG PELTA*/resources' 2>/dev/null | head -1)
    if [[ -n "$RES" ]]; then
        cp "$RES"/ROGFonts-Regular-*.ttf "$DEST/assets/ROGFonts-Regular.ttf" 2>/dev/null || true
        cp "$RES"/A501-*.svg "$DEST/assets/A501.svg" 2>/dev/null || true
    else
        echo "Note: ROG PELTA package not found in ~/Downloads; using fallback font and icon."
    fi
fi
ln -sf "$DEST/pelta-control" "$HOME/.local/bin/pelta-control"
cp "$SRC/icons/pelta-control.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/"
cp "$SRC/pelta-control.desktop" "$HOME/.local/share/applications/"
sed 's|^Exec=.*|Exec=pelta-control gui --tray|' "$SRC/pelta-control.desktop" \
    > "$HOME/.config/autostart/pelta-control.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Installed to $DEST (tray icon starts at login)."
if [[ ! -f $RULE ]]; then
    echo "Device access missing. Run once:"
    echo "  sudo install -m644 '$SRC/70-rog-pelta.rules' /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw"
fi
