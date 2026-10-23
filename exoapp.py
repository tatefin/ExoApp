#!/usr/bin/env python3
"""ExoApp: lighting, DPI and profiles for the EXO Rifter mouse.

Run without arguments for the window; with arguments it is the command-line
tool (see `exoapp --help`).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import exoapp_core as core  # noqa: E402


def run_gui():
    import gui
    return gui.run()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(core.main(sys.argv[1:]))
    sys.exit(run_gui())
