"""
Nova Cat Plugin
===============

Command:

    nova --cat

Features:
    - Uses the supplied cat.png artwork
    - Gentle breathing animation
    - Draggable around the desktop
    - Resizable
    - Red close button
    - Double-click launches Nova GUI
    - Always on top

The plugin does NOT:
    - create another model
    - modify Nova memory
    - modify Nova chat storage
    - modify CPU priority
    - modify other processes
    - modify Windows settings

The cat image is loaded from:

    cat.png

which must be located beside this plugin.py file.
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

CAT_IMAGE_NAME = "cat.png"

MIN_SCALE = 0.35
MAX_SCALE = 4.0

INITIAL_SCALE = 1.0

# Breathing animation.
BREATH_SPEED = 0.055
BREATH_AMOUNT = 0.035

# How frequently the animation updates.
ANIMATION_INTERVAL_MS = 40

# Size of the red close button relative to the cat.
CONTROL_SIZE_RATIO = 0.26

# Ctrl-drag resize sensitivity.
RESIZE_SENSITIVITY = 0.008


# ============================================================================
# FIND NOVA
# ============================================================================

def find_nova_command() -> list[str]:
    """
    Find the installed Nova command.

    Prefer the `nova` executable.

    If it is not available on PATH, fall back to the current
    Python interpreter and the Novatrix CLI module.
    """

    executable = shutil.which(
        "nova"
    )

    if executable:

        return [
            executable
        ]

    return [
        sys.executable,
        "-m",
        "novatrix.nova_cli",
    ]


# ============================================================================
# LAUNCH NOVA GUI
# ============================================================================

def launch_nova_ui() -> bool:
    """
    Launch Nova's existing graphical interface.

    Equivalent to:

        nova --ui
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

        # ------------------------------------------------------------------
        # Borderless / always-on-top window
        # ------------------------------------------------------------------

        self.root.overrideredirect(
            True
        )

        self.root.attributes(
            "-topmost",
            True,
        )

        # ------------------------------------------------------------------
        # State
        # ------------------------------------------------------------------

        self.scale = INITIAL_SCALE

        self.breath_phase = 0.0

        self.dragging = False

        self.resizing = False

        self.controls_visible = False

        self.drag_start_x = 0
        self.drag_start_y = 0

        self.window_start_x = 0
        self.window_start_y = 0

        self.resize_start_y = 0
        self.resize_start_scale = INITIAL_SCALE

        # ------------------------------------------------------------------
        # Locate cat image
        # ------------------------------------------------------------------

        self.image_path = self._find_image()

        if self.image_path is None:

            self.root.destroy()

            raise RuntimeError(
                "Nova Cat could not find cat.png.\n\n"
                "Make sure cat.png is beside plugin.py."
            )

        # ------------------------------------------------------------------
        # Load original image
        # ------------------------------------------------------------------

        try:

            self.original_image = tk.PhotoImage(
                file=self.image_path
            )

        except tk.TclError as error:

            self.root.destroy()

            raise RuntimeError(
                f"Could not load cat.png:\n{error}"
            ) from error

        self.original_width = (
            self.original_image.width()
        )

        self.original_height = (
            self.original_image.height()
        )

        # ------------------------------------------------------------------
        # Transparent window background
        # ------------------------------------------------------------------

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

            # Fallback for systems where transparentcolor isn't available.
            self.transparent_color = "#000000"

            self.root.configure(
                bg=self.transparent_color
            )

        # ------------------------------------------------------------------
        # Canvas
        # ------------------------------------------------------------------

        self.canvas = tk.Canvas(
            self.root,
            bg=self.transparent_color,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )

        self.canvas.pack()

        # ------------------------------------------------------------------
        # Initial cat
        # ------------------------------------------------------------------

        self._rebuild_window(
            first_build=True
        )

        # ------------------------------------------------------------------
        # Mouse controls
        # ------------------------------------------------------------------

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

        # Single click:
        # show/hide the controls.
        self.canvas.bind(
            "<Button-1>",
            self._single_click,
            add="+",
        )

        # Double click:
        # launch Nova GUI.
        self.canvas.bind(
            "<Double-Button-1>",
            self._double_click,
        )

        # Mouse wheel:
        # resize cat.
        self.canvas.bind(
            "<MouseWheel>",
            self._mouse_wheel,
        )

        # Right click:
        # also show/hide controls.
        self.canvas.bind(
            "<Button-3>",
            self._right_click,
        )

        # Escape:
        # close the cat.
        self.root.bind(
            "<Escape>",
            self._close,
        )

        # ------------------------------------------------------------------
        # Start breathing animation
        # ------------------------------------------------------------------

        self._animate()

    # ======================================================================
    # FIND IMAGE
    # ======================================================================

    def _find_image(self) -> str | None:
        """
        Find cat.png beside this plugin.py file.

        Current Nova installation structure:

            ~/.nova/plugins/cat/
                plugin.py
                cat.png
        """

        plugin_directory = os.path.dirname(
            os.path.abspath(__file__)
        )

        path = os.path.join(
            plugin_directory,
            CAT_IMAGE_NAME,
        )

        if os.path.isfile(path):

            return path

        # Development fallback:
        # useful when running the source file directly.
        current_directory_path = os.path.join(
            os.getcwd(),
            CAT_IMAGE_NAME,
        )

        if os.path.isfile(
            current_directory_path
        ):

            return current_directory_path

        return None

    # ======================================================================
    # INITIAL POSITION
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
            -
            self.window_width
            -
            35
        )

        y = (
            screen_height
            -
            self.window_height
            -
            75
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
            f"+{x}+{y}"
        )

    # ======================================================================
    # CALCULATE BREATHING SIZE
    # ======================================================================

    def _calculate_size(
        self,
    ) -> tuple[int, int]:

        breathing_factor = (
            1.0
            +
            math.sin(
                self.breath_phase
            )
            *
            BREATH_AMOUNT
        )

        effective_scale = (
            self.scale
            *
            breathing_factor
        )

        width = max(
            1,
            int(
                self.original_width
                *
                effective_scale
            ),
        )

        height = max(
            1,
            int(
                self.original_height
                *
                effective_scale
            ),
        )

        return (
            width,
            height,
        )

    # ======================================================================
    # SCALE IMAGE
    # ======================================================================

    def _scale_image(
        self,
        target_width: int,
        target_height: int,
    ):
        """
        Scale the pixel artwork using Tkinter's native pixel-preserving
        zoom/subsample operations.

        No image processing or eye overlays happen here.

        The PNG is simply the cat.
        """

        scale_x = (
            target_width
            /
            self.original_width
        )

        scale_y = (
            target_height
            /
            self.original_height
        )

        scale = min(
            scale_x,
            scale_y,
        )

        # --------------------------------------------------------------
        # Enlarge
        # --------------------------------------------------------------

        if scale >= 1:

            factor = max(
                1,
                int(
                    round(scale)
                ),
            )

            return self.original_image.zoom(
                factor,
                factor,
            )

        # --------------------------------------------------------------
        # Shrink
        # --------------------------------------------------------------

        divisor = max(
            1,
            int(
                round(
                    1 / scale
                )
            ),
        )

        return self.original_image.subsample(
            divisor,
            divisor,
        )

    # ======================================================================
    # REBUILD WINDOW
    # ======================================================================

    def _rebuild_window(
        self,
        first_build: bool = False,
    ):

        width, height = (
            self._calculate_size()
        )

        self.window_width = width

        self.window_height = height

        # --------------------------------------------------------------
        # Replace image
        # --------------------------------------------------------------

        self.current_image = (
            self._scale_image(
                width,
                height,
            )
        )

        self.canvas.configure(
            width=width,
            height=height,
        )

        self.canvas.delete(
            "all"
        )

        self.canvas.create_image(
            width // 2,
            height // 2,
            image=self.current_image,
            anchor="center",
        )

        # --------------------------------------------------------------
        # Draw optional controls
        # --------------------------------------------------------------

        if self.controls_visible:

            self._draw_controls()

        # --------------------------------------------------------------
        # First placement only
        # --------------------------------------------------------------

        if first_build:

            self._position_bottom_right()

            self.window_positioned = True

    # ======================================================================
    # BREATHING ANIMATION
    # ======================================================================

    def _animate(self):

        try:

            if not self.root.winfo_exists():

                return

        except tk.TclError:

            return

        # --------------------------------------------------------------
        # Update breathing phase
        # --------------------------------------------------------------

        self.breath_phase += BREATH_SPEED

        # --------------------------------------------------------------
        # Remember center so the cat breathes in place.
        # --------------------------------------------------------------

        old_x = self.root.winfo_x()

        old_y = self.root.winfo_y()

        old_width = self.window_width

        old_height = self.window_height

        center_x = (
            old_x
            +
            old_width / 2
        )

        center_y = (
            old_y
            +
            old_height / 2
        )

        # --------------------------------------------------------------
        # Rebuild image.
        # --------------------------------------------------------------

        self._rebuild_window()

        new_x = int(
            center_x
            -
            self.window_width / 2
        )

        new_y = int(
            center_y
            -
            self.window_height / 2
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
            f"+{new_x}+{new_y}"
        )

        self.root.after(
            ANIMATION_INTERVAL_MS,
            self._animate,
        )

    # ======================================================================
    # CONTROL BUTTON
    # ======================================================================

    def _draw_controls(self):

        self.canvas.delete(
            "controls"
        )

        size = max(
            14,
            int(
                self.window_width
                *
                CONTROL_SIZE_RATIO
            ),
        )

        margin = max(
            3,
            int(
                self.window_width
                *
                0.035
            ),
        )

        x = (
            self.window_width
            -
            size
            -
            margin
        )

        y = margin

        # --------------------------------------------------------------
        # Red square
        # --------------------------------------------------------------

        self.canvas.create_rectangle(
            x,
            y,
            x + size,
            y + size,
            fill="#e53935",
            outline="#ffffff",
            width=max(
                1,
                size // 14,
            ),
            tags=("controls",),
        )

        # --------------------------------------------------------------
        # White X
        # --------------------------------------------------------------

        line_width = max(
            2,
            size // 7,
        )

        self.canvas.create_line(
            x + size * 0.25,
            y + size * 0.25,
            x + size * 0.75,
            y + size * 0.75,
            fill="#ffffff",
            width=line_width,
            tags=("controls",),
        )

        self.canvas.create_line(
            x + size * 0.75,
            y + size * 0.25,
            x + size * 0.25,
            y + size * 0.75,
            fill="#ffffff",
            width=line_width,
            tags=("controls",),
        )

    # ======================================================================
    # CONTROL HIT TEST
    # ======================================================================

    def _controls_hit(
        self,
        x: int,
        y: int,
    ) -> bool:

        size = max(
            14,
            int(
                self.window_width
                *
                CONTROL_SIZE_RATIO
            ),
        )

        margin = max(
            3,
            int(
                self.window_width
                *
                0.035
            ),
        )

        control_x = (
            self.window_width
            -
            size
            -
            margin
        )

        control_y = margin

        return (
            control_x
            <=
            x
            <=
            control_x + size
            and
            control_y
            <=
            y
            <=
            control_y + size
        )

    # ======================================================================
    # MOUSE DOWN
    # ======================================================================

    def _mouse_down(
        self,
        event,
    ):

        # --------------------------------------------------------------
        # Close button gets priority.
        # --------------------------------------------------------------

        if self.controls_visible:

            if self._controls_hit(
                event.x,
                event.y,
            ):

                self._close()

                return

        # --------------------------------------------------------------
        # Ctrl + left drag = resize.
        # --------------------------------------------------------------

        ctrl_pressed = bool(
            event.state
            &
            0x0004
        )

        if ctrl_pressed:

            self.resizing = True

            self.dragging = False

            self.resize_start_y = (
                event.y_root
            )

            self.resize_start_scale = (
                self.scale
            )

            return

        # --------------------------------------------------------------
        # Normal left drag = move.
        # --------------------------------------------------------------

        self.dragging = True

        self.resizing = False

        self.drag_start_x = (
            event.x_root
        )

        self.drag_start_y = (
            event.y_root
        )

        self.window_start_x = (
            self.root.winfo_x()
        )

        self.window_start_y = (
            self.root.winfo_y()
        )

    # ======================================================================
    # MOUSE DRAG
    # ======================================================================

    def _mouse_drag(
        self,
        event,
    ):

        # --------------------------------------------------------------
        # Resize
        # --------------------------------------------------------------

        if self.resizing:

            delta = (
                event.y_root
                -
                self.resize_start_y
            )

            new_scale = (
                self.resize_start_scale
                +
                delta
                *
                RESIZE_SENSITIVITY
            )

            self._set_scale(
                new_scale
            )

            return

        # --------------------------------------------------------------
        # Move
        # --------------------------------------------------------------

        if not self.dragging:

            return

        dx = (
            event.x_root
            -
            self.drag_start_x
        )

        dy = (
            event.y_root
            -
            self.drag_start_y
        )

        new_x = (
            self.window_start_x
            +
            dx
        )

        new_y = (
            self.window_start_y
            +
            dy
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
            f"+{new_x}+{new_y}"
        )

    # ======================================================================
    # MOUSE UP
    # ======================================================================

    def _mouse_up(
        self,
        event,
    ):

        del event

        self.dragging = False

        self.resizing = False

    # ======================================================================
    # SINGLE CLICK
    # ======================================================================

    def _single_click(
        self,
        event,
    ):

        # A plain click toggles the controls.
        #
        # Double-click behavior is handled separately by Tkinter.
        # The cat itself is not launched on a single click.

        if self._controls_hit(
            event.x,
            event.y,
        ):

            return

        # Don't toggle controls while Ctrl-resizing.
        if self.resizing:

            return

        self.controls_visible = (
            not self.controls_visible
        )

        self._rebuild_window()

    # ======================================================================
    # DOUBLE CLICK
    # ======================================================================

    def _double_click(
        self,
        event,
    ):

        del event

        started = launch_nova_ui()

        if started:

            self.root.destroy()

    # ======================================================================
    # MOUSE WHEEL
    # ======================================================================

    def _mouse_wheel(
        self,
        event,
    ):

        if event.delta > 0:

            change = 0.10

        else:

            change = -0.10

        self._set_scale(
            self.scale + change
        )

    # ======================================================================
    # SET SCALE
    # ======================================================================

    def _set_scale(
        self,
        new_scale: float,
    ):

        new_scale = max(
            MIN_SCALE,
            min(
                MAX_SCALE,
                new_scale,
            ),
        )

        if abs(
            new_scale
            -
            self.scale
        ) < 0.001:

            return

        # Preserve the center while resizing.
        center_x = (
            self.root.winfo_x()
            +
            self.window_width / 2
        )

        center_y = (
            self.root.winfo_y()
            +
            self.window_height / 2
        )

        self.scale = new_scale

        # Rebuild without resetting the desktop position.
        self._rebuild_window()

        new_x = int(
            center_x
            -
            self.window_width / 2
        )

        new_y = int(
            center_y
            -
            self.window_height / 2
        )

        self.root.geometry(
            f"{self.window_width}x{self.window_height}"
            f"+{new_x}+{new_y}"
        )

    # ======================================================================
    # RIGHT CLICK
    # ======================================================================

    def _right_click(
        self,
        event,
    ):

        del event

        self.controls_visible = (
            not self.controls_visible
        )

        self._rebuild_window()

    # ======================================================================
    # CLOSE
    # ======================================================================

    def _close(
        self,
        event=None,
    ):

        del event

        try:

            self.root.destroy()

        except tk.TclError:

            pass

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

    del args
    del runtime

    cat = CatWindow()

    cat.run()


# ============================================================================
# NOVA PLUGIN
# ============================================================================

class CatPlugin(NovaPlugin):

    name = "cat"

    version = "1.2.0"

    description = (
        "Summon an animated draggable pixel cat."
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
                "Summon an animated draggable pixel cat."
            ),
            action="store_true",
        )


# ============================================================================
# REQUIRED NOVA EXPORT
# ============================================================================

plugin = CatPlugin()
