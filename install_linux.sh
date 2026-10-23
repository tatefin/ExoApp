#!/bin/sh
# Installs ExoApp for the current user: venv, `exoapp` command, menu entry.
# Run with --uninstall to remove the command and menu entry again.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
BIN="$HOME/.local/bin/exoapp"
DESKTOP="$HOME/.local/share/applications/exoapp.desktop"

if [ "$1" = "--uninstall" ]; then
    rm -f "$BIN" "$DESKTOP"
    rm -rf "$DIR/.venv"
    echo "Uninstalled. Profiles are kept in ~/.config/ExoApp."
    exit 0
fi

python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$DIR/requirements.txt"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
cat > "$BIN" <<EOS
#!/bin/sh
exec "$DIR/.venv/bin/python" "$DIR/exoapp.py" "\$@"
EOS
chmod +x "$BIN"
cat > "$DESKTOP" <<EOS
[Desktop Entry]
Type=Application
Name=ExoApp
Comment=EXO Rifter mouse lighting, DPI and profiles
Exec=$BIN
Icon=$DIR/assets/exoapp.png
Categories=Settings;HardwareSettings;
EOS
echo "Installed: run 'exoapp' or open ExoApp from the menu."
