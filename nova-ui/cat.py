"""
Nova Cat Plugin
===============

Command:

    nova --cat

Features:
    - Tiny pixel cat
    - Draggable around the desktop
    - Eyes follow the mouse cursor
    - Left click opens Nova GUI
    - Right click closes the cat
    - Escape closes the cat
    - Always on top
    - No external image/dependency required

The cat is only a launcher for Nova's GUI.
It does not modify Nova's model, memory, CPU priority,
or any other subsystem.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tkinter as tk

from novatrix.plugin_system import NovaPlugin


# ============================================================================
# CONFIGURATION
# ============================================================================

SCALE = 5

CAT_WIDTH = 20
CAT_HEIGHT = 18

WINDOW_PADDING = 4

UPDATE_INTERVAL_MS = 30

DRAG_THRESHOLD = 4


# ============================================================================
# PIXEL CAT
# ============================================================================

# 20 x 18 monochrome body.
#
# 0 = transparent
# 1 = black
# 2 = white
#
# The eyes are drawn separately so that their pupils can follow
# the actual mouse cursor.

CAT = [
    "00000011000001100000",
    "00000111000011100000",
    "00000111111111100000",
    "00001111111111110000",
    "00011111111111111000",
    "00111111111111111100",
    "01111111111111111110",
    "01111111111111111110",
    "11111111111111111111",
    "11111111111111111111",
    "11111111111111111111",
    "11111111111111111111",
    "01111111111111111110",
    "01111111111111111110",
    "00111111111111111100",
    "00011111111111111000",
    "00001111111111110000",
    "00000111111111100000",
]


# ============================================================================
# FIND NOVA
# ============================================================================

def find_nova_command() -> list[str]:
    """
    Find the installed Nova command.

    Prefer the console-script executable.
    Fall back to the current Python interpreter.
    """

    nova_executable = shutil.which(
        "nova"
    )

    if nova_executable:

        return [
            nova_executable
        ]

    return [
        sys.executable,
        "-m",
        "novatrix.nova_cli",
    ]


# ============================================================================
# LAUNCH NOVA UI
# ============================================================================

def launch_nova_ui() -> bool:
    """
    Launch Nova's existing GUI.

    Returns True when the process was successfully started.
    """

    command = find_nova_command()

    command.append(
        "--ui"
    )

    try:

        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        return True

    except OSError as error:

        print(
            f"[Nova Cat] Could not launch Nova GUI: {error}",
            file=sys.stderr,
            flush=True,
        )

        return False


# ============================================================================
# CAT WINDOW
# ============================================================================

class CatWindow:

    def __init__(self):

        self.root = tk.Tk()

        # --------------------------------------------------------------
        # Borderless / always-on-top
        # --------------------------------------------------------------

        self.root.overrideredirect(
            True
        )

        self.root.attributes(
            "-topmost",
            True,
        )

        # --------------------------------------------------------------
        # Transparency
        # --------------------------------------------------------------

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

            self.transparent_color = "#000000"

            self.root.configure(
                bg=self.transparent_color
            )

        # --------------------------------------------------------------
        # Size
        # --------------------------------------------------------------

        self.window_width = (
            CAT_WIDTH * SCALE
            + WINDOW_PADDING * 2
        )

        self.window_height = (
            CAT_HEIGHT * SCALE
            + WINDOW_PADDING * 2
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
        )

        self._position_bottom_right()

        # --------------------------------------------------------------
        # Canvas
        # --------------------------------------------------------------

        self.canvas = tk.Canvas(
            self.root,
            width=self.window_width,
            height=self.window_height,
            bg=self.transparent_color,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )

        self.canvas.pack()

        # --------------------------------------------------------------
        # Internal state
        # --------------------------------------------------------------

        self.dragging = False

        self.drag_start_x = 0
        self.drag_start_y = 0

        self.window_start_x = 0
        self.window_start_y = 0

        self.mouse_moved_during_click = False

        # --------------------------------------------------------------
        # Draw cat
        # --------------------------------------------------------------

        self._draw_cat_body()

        self._draw_eyes()

        # --------------------------------------------------------------
        # Mouse controls
        # --------------------------------------------------------------

        self.canvas.bind(
            "<ButtonPress-1>",
            self._mouse_down,
        )

        self.canvas.bind(
            "<B1-Motion>",
            self._mouse_drag,
        )

        self.canvas.bind(
            "<ButtonRelease-1>",
            self._mouse_up,
        )

        # Right click closes.
        self.canvas.bind(
            "<Button-3>",
            self._close,
        )

        self.root.bind(
            "<Escape>",
            self._close,
        )

        # --------------------------------------------------------------
        # Start eye tracking
        # --------------------------------------------------------------

        self._update_eyes()

    # ======================================================================
    # WINDOW POSITION
    # ======================================================================

    def _position_bottom_right(self):

        screen_width = (
            self.root.winfo_screenwidth()
        )

        screen_height = (
            self.root.winfo_screenheight()
        )

        x = (
            screen_width
            - self.window_width
            - 30
        )

        y = (
            screen_height
            - self.window_height
            - 70
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
            f"+{x}+{y}"
        )

    # ======================================================================
    # DRAW CAT BODY
    # ======================================================================

    def _draw_cat_body(self):

        for y, row in enumerate(CAT):

            for x, pixel in enumerate(row):

                if pixel == "0":

                    continue

                if pixel == "1":

                    fill = "#ffffff"

                else:

                    fill = "#000000"

                x1 = (
                    WINDOW_PADDING
                    + x * SCALE
                )

                y1 = (
                    WINDOW_PADDING
                    + y * SCALE
                )

                x2 = (
                    x1
                    + SCALE
                )

                y2 = (
                    y1
                    + SCALE
                )

                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=fill,
                    outline=fill,
                    tags=("cat_body",),
                )

    # ======================================================================
    # EYE GEOMETRY
    # ======================================================================

    def _eye_centers(self):
        """
        Return the two eye centers in canvas coordinates.

        These positions are deliberately fixed relative to the pixel cat.
        """

        left_eye = (
            WINDOW_PADDING
            + 6.2 * SCALE,
            WINDOW_PADDING
            + 7.3 * SCALE,
        )

        right_eye = (
            WINDOW_PADDING
            + 13.3 * SCALE,
            WINDOW_PADDING
            + 7.3 * SCALE,
        )

        return left_eye, right_eye

    # ======================================================================
    # DRAW EYES
    # ======================================================================

    def _draw_eyes(self):

        self.canvas.delete(
            "eyes"
        )

        left_eye, right_eye = (
            self._eye_centers()
        )

        self._draw_single_eye(
            *left_eye
        )

        self._draw_single_eye(
            *right_eye
        )

    def _draw_single_eye(
        self,
        center_x: float,
        center_y: float,
    ):

        # White 2x2 pixel eye socket.
        eye_radius = SCALE * 0.9

        self.canvas.create_oval(
            center_x - eye_radius,
            center_y - eye_radius,
            center_x + eye_radius,
            center_y + eye_radius,
            fill="#ffffff",
            outline="#ffffff",
            tags=("eyes",),
        )

    # ======================================================================
    # UPDATE EYES
    # ======================================================================

    def _update_eyes(self):

        if not self.root.winfo_exists():

            return

        mouse_x = (
            self.root.winfo_pointerx()
        )

        mouse_y = (
            self.root.winfo_pointery()
        )

        left_eye, right_eye = (
            self._eye_centers()
        )

        # --------------------------------------------------------------
        # Delete old eyes and redraw sockets + pupils.
        # --------------------------------------------------------------

        self.canvas.delete(
            "eyes"
        )

        self._update_single_eye(
            *left_eye,
            mouse_x,
            mouse_y,
        )

        self._update_single_eye(
            *right_eye,
            mouse_x,
            mouse_y,
        )

        self.root.after(
            UPDATE_INTERVAL_MS,
            self._update_eyes,
        )

    def _update_single_eye(
        self,
        eye_x: float,
        eye_y: float,
        mouse_x: int,
        mouse_y: int,
    ):

        # --------------------------------------------------------------
        # Eye socket
        # --------------------------------------------------------------

        eye_radius = SCALE * 0.9

        self.canvas.create_oval(
            eye_x - eye_radius,
            eye_y - eye_radius,
            eye_x + eye_radius,
            eye_y + eye_radius,
            fill="#ffffff",
            outline="#ffffff",
            tags=("eyes",),
        )

        # --------------------------------------------------------------
        # Direction toward cursor
        #
        # Convert the global cursor position into the approximate
        # direction from the eye.
        # --------------------------------------------------------------

        window_x = self.root.winfo_x()
        window_y = self.root.winfo_y()

        absolute_eye_x = (
            window_x
            + eye_x
        )

        absolute_eye_y = (
            window_y
            + eye_y
        )

        dx = (
            mouse_x
            - absolute_eye_x
        )

        dy = (
            mouse_y
            - absolute_eye_y
        )

        distance = math.hypot(
            dx,
            dy,
        )

        if distance < 1:

            dx = 0
            dy = 0

        else:

            dx /= distance
            dy /= distance

        # Keep pupil inside the eye.
        pupil_distance = SCALE * 0.32

        pupil_x = (
            eye_x
            + dx * pupil_distance
        )

        pupil_y = (
            eye_y
            + dy * pupil_distance
        )

        pupil_radius = SCALE * 0.38

        self.canvas.create_oval(
            pupil_x - pupil_radius,
            pupil_y - pupil_radius,
            pupil_x + pupil_radius,
            pupil_y + pupil_radius,
            fill="#000000",
            outline="#000000",
            tags=("eyes",),
        )

    # ======================================================================
    # DRAGGING
    # ======================================================================

    def _mouse_down(
        self,
        event,
    ):

        self.dragging = True

        self.mouse_moved_during_click = False

        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root

        self.window_start_x = (
            self.root.winfo_x()
        )

        self.window_start_y = (
            self.root.winfo_y()
        )

    def _mouse_drag(
        self,
        event,
    ):

        if not self.dragging:

            return

        dx = (
            event.x_root
            - self.drag_start_x
        )

        dy = (
            event.y_root
            - self.drag_start_y
        )

        if (
            abs(dx) > DRAG_THRESHOLD
            or abs(dy) > DRAG_THRESHOLD
        ):

            self.mouse_moved_during_click = True

        new_x = (
            self.window_start_x
            + dx
        )

        new_y = (
            self.window_start_y
            + dy
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
            f"+{new_x}+{new_y}"
        )

    def _mouse_up(
        self,
        event,
    ):

        del event

        self.dragging = False

        # A plain click launches Nova.
        #
        # A drag does not.
        if not self.mouse_moved_during_click:

            self._open_nova()

    # ======================================================================
    # OPEN NOVA
    # ======================================================================

    def _open_nova(self):

        started = launch_nova_ui()

        if started:

            self.root.destroy()

    # ======================================================================
    # CLOSE
    # ======================================================================

    def _close(
        self,
        event=None,
    ):

        del event

        self.root.destroy()

    # ======================================================================
    # RUN
    # ======================================================================

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
    version = "1.1.0"
    description = (
        "Summon a draggable pixel cat that launches Nova's GUI."
    )
    plugin_api_version = 1

    def register(
        self,
        nova_runtime,
    ):

        nova_runtime.register_cli_command(
            name="cat",
            callback=run_cat,
            help_text=(
                "Summon a draggable pixel cat that launches Nova GUI."
            ),
            action="store_true",
        )


# ============================================================================
# REQUIRED NOVA PLUGIN EXPORT
# ============================================================================

plugin = CatPlugin()
