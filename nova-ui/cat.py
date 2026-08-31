"""
Nova Cat Plugin
===============

Command:

    nova --cat

A tiny animated desktop cat for Nova.

Controls
--------
Left drag:
    Move the cat.

Ctrl + left drag:
    Resize the cat vertically.

Mouse wheel:
    Resize the cat.

Single click:
    Show/hide the cat controls.

Double click:
    Launch Nova's GUI.

Red X:
    Remove the cat.

The cat:
    - stays on top
    - breathes gently
    - can be moved
    - can be resized
    - launches Nova GUI
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

BREATH_SPEED = 0.055
BREATH_AMOUNT = 0.035


CONTROL_SIZE_RATIO = 0.26

RESIZE_SENSITIVITY = 0.008


# ============================================================================
# FIND NOVA
# ============================================================================

def find_nova_command() -> list[str]:
    """
    Find the installed Nova command.

    Prefer the `nova` executable.

    Fall back to the current Python interpreter and the Nova module.
    """

    executable = shutil.which("nova")

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
    Launch:

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
            f"[Nova Cat] Failed to launch Nova GUI: {error}",
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
        # Borderless desktop window
        # --------------------------------------------------------------

        self.root.overrideredirect(
            True
        )

        self.root.attributes(
            "-topmost",
            True,
        )

        # --------------------------------------------------------------
        # State
        # --------------------------------------------------------------

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

        self.click_timer = None

        self.last_click_time = 0

        # --------------------------------------------------------------
        # Image path
        # --------------------------------------------------------------

        self.image_path = self._find_image()

        if self.image_path is None:

            self.root.destroy()

            raise RuntimeError(
                "Nova Cat could not find cat.png."
                "\n\n"
                "Place cat.png beside the plugin's source file."
            )

        # --------------------------------------------------------------
        # Load image
        # --------------------------------------------------------------

        try:

            self.original_image = tk.PhotoImage(
                file=self.image_path
            )

        except tk.TclError as error:

            self.root.destroy()

            raise RuntimeError(
                f"Could not load cat image:\n{error}"
            ) from error

        self.original_width = (
            self.original_image.width()
        )

        self.original_height = (
            self.original_image.height()
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
        # Canvas
        # --------------------------------------------------------------

        self.canvas = tk.Canvas(
            self.root,
            bg=self.transparent_color,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )

        self.canvas.pack()

        # --------------------------------------------------------------
        # Create initial cat
        # --------------------------------------------------------------

        self._rebuild_window()

        # --------------------------------------------------------------
        # Mouse events
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

        self.canvas.bind(
            "<Double-Button-1>",
            self._double_click,
        )

        self.canvas.bind(
            "<MouseWheel>",
            self._mouse_wheel,
        )

        self.canvas.bind(
            "<Button-3>",
            self._right_click,
        )

        self.root.bind(
            "<Escape>",
            self._close,
        )

        # --------------------------------------------------------------
        # Start animation
        # --------------------------------------------------------------

        self._animate()

    # ======================================================================
    # FIND IMAGE
    # ======================================================================

    def _find_image(self) -> str | None:
        """
        Locate cat.png.

        First try beside this source file.

        Then try the current working directory.
        """

        candidates = [
            os.path.join(
                os.path.dirname(
                    os.path.abspath(__file__)
                ),
                CAT_IMAGE_NAME,
            ),
            os.path.join(
                os.getcwd(),
                CAT_IMAGE_NAME,
            ),
        ]

        for path in candidates:

            if os.path.isfile(path):

                return path

        return None

    # ======================================================================
    # RESIZING
    # ======================================================================

    def _calculate_size(self) -> tuple[int, int]:

        breath = (
            1.0
            +
            math.sin(
                self.breath_phase
            )
            * BREATH_AMOUNT
        )

        effective_scale = (
            self.scale
            * breath
        )

        width = max(
            1,
            int(
                self.original_width
                * effective_scale
            ),
        )

        height = max(
            1,
            int(
                self.original_height
                * effective_scale
            ),
        )

        return width, height

    def _rebuild_window(self):

        width, height = self._calculate_size()

        self.window_width = width

        self.window_height = height

        # --------------------------------------------------------------
        # Resize image using PhotoImage zoom/subsample.
        #
        # Tkinter's native image scaling is integer-based, so we use
        # a generated image through zoom/subsample when possible.
        # --------------------------------------------------------------

        self.current_image = self._scale_image(
            width,
            height,
        )

        self.canvas.configure(
            width=width,
            height=height,
        )

        self.canvas.delete(
            "all"
        )

        self.image_id = self.canvas.create_image(
            width // 2,
            height // 2,
            image=self.current_image,
            anchor="center",
        )

        # --------------------------------------------------------------
        # Position controls
        # --------------------------------------------------------------

        if self.controls_visible:

            self._draw_controls()

        # --------------------------------------------------------------
        # Keep existing location when resizing.
        # --------------------------------------------------------------

        if not hasattr(
            self,
            "window_positioned",
        ):

            self._position_bottom_right()

            self.window_positioned = True

    def _scale_image(
        self,
        target_width: int,
        target_height: int,
    ):

        """
        Produce a PhotoImage scaled to the requested size.

        Tk's PhotoImage has limited native scaling functionality,
        so this function uses the closest stable integer scaling
        available from the original image.

        For the small pixel-art sprite this is intentional.
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

        # Integer enlargement.
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

        # Integer reduction.
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
    # POSITION
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
    # BREATHING ANIMATION
    # ======================================================================

    def _animate(self):

        if not self.root.winfo_exists():

            return

        # --------------------------------------------------------------
        # Advance breathing phase.
        # --------------------------------------------------------------

        self.breath_phase += BREATH_SPEED

        # --------------------------------------------------------------
        # Rebuild image at slightly different vertical/horizontal scale.
        # --------------------------------------------------------------

        current_x = self.root.winfo_x()

        current_y = self.root.winfo_y()

        old_width = self.window_width

        old_height = self.window_height

        self._rebuild_window()

        new_width = self.window_width

        new_height = self.window_height

        # Keep the cat centered in the same place while breathing.
        new_x = (
            current_x
            -
            (new_width - old_width) // 2
        )

        new_y = (
            current_y
            -
            (new_height - old_height) // 2
        )

        self.root.geometry(
            f"{new_width}x{new_height}"
            f"+{new_x}+{new_y}"
        )

        # --------------------------------------------------------------

    # ======================================================================
    # CONTROLS
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

        # Red square.
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

        # White X.
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

        # Bind click on the control region.
        self.canvas.tag_bind(
            "controls",
            "<Button-1>",
            self._close_from_control,
        )

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

    def _close_from_control(
        self,
        event,
    ):

        del event

        self._close()

    # ======================================================================
    # MOUSE DOWN
    # ======================================================================

    def _mouse_down(
        self,
        event,
    ):

        # Red X has priority.
        if self.controls_visible:

            if self._controls_hit(
                event.x,
                event.y,
            ):

                self._close()

                return

        # --------------------------------------------------------------
        # Ctrl + drag = resizing.
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
        # Normal drag = move.
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

        if self.resizing:

            self.resizing = False

            return

        self.dragging = False

    # ======================================================================
    # DOUBLE CLICK
    # ======================================================================

    def _double_click(
        self,
        event,
    ):

        del event

        # A double click is the explicit "open Nova" action.
        started = launch_nova_ui()

        if started:

            self.root.destroy()

    # ======================================================================
    # SINGLE CLICK
    # ======================================================================

    def _toggle_controls(self):

        self.controls_visible = (
            not self.controls_visible
        )

        self._rebuild_window()

    # ======================================================================
    # MOUSE WHEEL
    # ======================================================================

    def _mouse_wheel(
        self,
        event,
    ):

        # Positive = away/up.
        # Negative = toward/down.
        #
        # Wheel direction is inverted so:
        # scroll up   -> grow
        # scroll down -> shrink

        change = (
            0.10
            if event.delta > 0
            else -0.10
        )

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

        self._toggle_controls()

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

    version = "1.1.0"

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
