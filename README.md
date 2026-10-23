# ExoApp

Lighting, DPI and profiles for the EXO Rifter mouse (Sinowealth chip, USB ID
`258a:0029`) on Linux and Windows. The UI is in Finnish, English and Swedish.

OpenRGB detects this mouse as an "Everest GT-100" and sends colours in R,B,G
order, so they come out wrong (yellow shows as pink). ExoApp sends R,G,B.
Settings are stored in the mouse itself, so nothing has to keep running in the
background.

## Linux

```sh
./install_linux.sh
```

This sets up a Python environment in `.venv`, the `exoapp` command and an
"ExoApp" menu entry. Keep the folder where it is after installing; run
`./install_linux.sh --uninstall` to remove the command and menu entry.
Your user needs read/write access to the mouse's `/dev/hidraw*` node;
desktop sessions normally grant this.

## Windows

1. Install Python 3.12 or 3.13 from python.org (tick "Add python.exe to PATH").
2. Double-click `build_windows.bat`.
3. Run `dist\ExoApp\ExoApp.exe`. Copy the whole `dist\ExoApp` folder if you
   want to move it somewhere else.

No driver is needed. Close OpenRGB and the mouse's own software first, since
they talk to the same interface.

## Command line

`exoapp` with no arguments opens the window. With arguments it is a CLI:

```sh
exoapp status
exoapp set static orange
exoapp set breathing ff0080 -s slow
exoapp set rainbow -s fast -d up
exoapp set multicolor red orange yellow green cyan blue magenta
exoapp dpi 800 1600 3200 -a 2 -c red green blue
exoapp profile save Games
exoapp profile load Games
exoapp backup mouse.bin
exoapp restore mouse.bin
```

On Windows, use `python exoapp.py ...` from the source folder for the CLI.

Profiles and settings are stored in `~/.config/ExoApp` on Linux and in
`%APPDATA%\ExoApp` on Windows.

## Effects

The mouse firmware supports: static, multicolour breathing, rainbow,
spectrum cycle, colour cycle, wave, tail, rave, strobe and off. Its
single-colour breathing mode stays dark, so ExoApp runs "breathing" as
multicolour breathing with the same colour in every slot.
