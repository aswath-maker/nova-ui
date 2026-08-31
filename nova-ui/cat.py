"""
Nova Cat Plugin
===============

Command:

    nova --cat

Launches a tiny always-on-top pixel cat.

Click the cat:
    -> launches `nova --ui`

The cat window is only a launcher.
It does not:
    - create a model
    - modify Nova memory
    - modify chats
    - modify CPU priority
    - modify other processes
    - modify Windows settings
    - modify Nova's GUI implementation
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk

from novatrix.plugin_system import NovaPlugin


# ============================================================================
# CAT CONFIGURATION
# ============================================================================

CAT_SCALE = 4

CAT_WIDTH = 16
CAT_HEIGHT = 16

WINDOW_PADDING = 4


# ============================================================================
# PIXEL CAT
# ============================================================================

# 16x16 monochrome pixel cat.
#
# 0 = transparent
# 1 = black pixel
# 2 = white pixel
#
# The actual background is made transparent where Windows allows it.
#
# We draw using rectangles rather than loading an external image, keeping
# the plugin completely self-contained.

CAT = [
    "0000001100000011",
    "0000011100000111",
    "0000011111111111",
    "0000111111111111",
    "0001111111111111",
    "0011111111111111",
    "0111110111101111",
    "0111100111100111",
    "1111111111111111",
    "1111111111111111",
    "1111110111101111",
    "1111111111111111",
    "0111111111111110",
    "0011111111111100",
    "0001111111111000",
    "0000111111110000",
]


# ============================================================================
# FIND NOVA EXECUTABLE
# ============================================================================

def find_nova_command() -> list[str]:
    """
    Find the command used to launch the installed Nova CLI.

    Preferred:
        nova

    Fallback:
        current Python interpreter + novatrix.nova_cli

    No shell invocation is used.
    """

    nova_executable = shutil.which("nova")

    if nova_executable:
        return [nova_executable]

    # Fallback for environments where the `nova` console script isn't
    # available on PATH but the package is installed in the current Python.
    return [
        sys.executable,
        "-m",
        "novatrix.nova_cli",
    ]


# ============================================================================
# LAUNCH NOVA UI
# ============================================================================

def launch_nova_ui(root: tk.Tk) -> None:
    """
    Launch Nova's existing GUI command.

    The cat itself does not implement the GUI.
    """

    command = find_nova_command()

    command.append("--ui")

    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

    except OSError as error:
        # Keep the cat plugin self-contained and avoid bringing down Nova.
        print(
            f"[Nova Cat] Could not launch Nova UI: {error}",
            file=sys.stderr,
            flush=True,
        )

        return

    # The cat is merely a launcher.
    # Once the GUI has been requested, close the launcher process.
    root.destroy()


# ============================================================================
# CAT WINDOW
# ============================================================================

class CatWindow:

    def __init__(self):

        self.root = tk.Tk()

        self.root.overrideredirect(True)

        self.root.attributes(
            "-topmost",
            True,
        )

        # Windows supports this transparent-color technique in Tk.
        self.transparent_color = "#00ff00"

        try:
            self.root.configure(
                bg=self.transparent_color
            )

            self.root.attributes(
                "-transparentcolor",
                self.transparent_color,
            )

        except tk.TclError:
            # If transparency isn't available, use black background.
            self.transparent_color = "#000000"

            self.root.configure(
                bg=self.transparent_color
            )

        width = (
            CAT_WIDTH * CAT_SCALE
            + WINDOW_PADDING * 2
        )

        height = (
            CAT_HEIGHT * CAT_SCALE
            + WINDOW_PADDING * 2
        )

        self.root.geometry(
            f"{width}x{height}"
        )

        self._position_bottom_right(
            width,
            height,
        )

        self.canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg=self.transparent_color,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )

        self.canvas.pack()

        self._draw_cat()

        # Left click launches Nova UI.
        self.canvas.bind(
            "<Button-1>",
            self._clicked,
        )

        self.root.bind(
            "<Button-1>",
            self._clicked,
        )

        # Right click closes the cat.
        self.canvas.bind(
            "<Button-3>",
            self._close,
        )

        self.root.bind(
            "<Button-3>",
            self._close,
        )

        # Escape closes it.
        self.root.bind(
            "<Escape>",
            self._close,
        )

        # Small tooltip-like title in the window manager if applicable.
        try:
            self.root.title(
                "Nova Cat"
            )
        except tk.TclError:
            pass

    # ----------------------------------------------------------------------
    # Position
    # ----------------------------------------------------------------------

    def _position_bottom_right(
        self,
        width: int,
        height: int,
    ):

        screen_width = self.root.winfo_screenwidth()

        screen_height = self.root.winfo_screenheight()

        x = (
            screen_width
            - width
            - 25
        )

        y = (
            screen_height
            - height
            - 65
        )

        self.root.geometry(
            f"{width}x{height}+{x}+{y}"
        )

    # ----------------------------------------------------------------------
    # Draw
    # ----------------------------------------------------------------------

    def _draw_cat(self):

        for y, row in enumerate(CAT):

            for x, pixel in enumerate(row):

                if pixel == "0":
                    continue

                # Pure monochrome pixel art.
                if pixel == "1":
                    fill = "#ffffff"
                else:
                    fill = "#000000"

                x1 = (
                    WINDOW_PADDING
                    + x * CAT_SCALE
                )

                y1 = (
                    WINDOW_PADDING
                    + y * CAT_SCALE
                )

                x2 = (
                    x1
                    + CAT_SCALE
                )

                y2 = (
                    y1
                    + CAT_SCALE
                )

                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=fill,
                    outline=fill,
                )

    # ----------------------------------------------------------------------
    # Click
    # ----------------------------------------------------------------------

    def _clicked(
        self,
        event=None,
    ):

        del event

        launch_nova_ui(
            self.root
        )

    # ----------------------------------------------------------------------
    # Close
    # ----------------------------------------------------------------------

    def _close(
        self,
        event=None,
    ):

        del event

        self.root.destroy()

    # ----------------------------------------------------------------------
    # Run
    # ----------------------------------------------------------------------

    def run(self):

        self.root.mainloop()


# ============================================================================
# CLI CALLBACK
# ============================================================================

def run_cat(
    args,
    runtime,
):
    """
    Callback for:

        nova --cat
    """

    del args
    del runtime

    cat = CatWindow()

    cat.run()


# ============================================================================
# NOVA PLUGIN
# ============================================================================

class CatPlugin(NovaPlugin):

    name = "cat"
    version = "1.0.0"
    description = "Summon a tiny pixel cat that launches Nova's GUI."
    plugin_api_version = 1

    def register(
        self,
        nova_runtime,
    ):

        nova_runtime.register_cli_command(
            name="cat",
            callback=run_cat,
            help_text="Summon a tiny pixel cat that launches Nova GUI.",
            action="store_true",
        )


# ============================================================================
# REQUIRED PLUGIN EXPORT
# ============================================================================

plugin = CatPlugin()
