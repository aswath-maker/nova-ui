"""
Nova Cat Plugin
===============

Public command:

    nova --cat

Behavior:

    nova --cat
        ↓
    starts a detached desktop-cat process
        ↓
    terminal command finishes
        ↓
    cat remains alive even if CMD is closed

Cat features:

    - Pixel-art cat loaded from cat.png
    - Gentle breathing animation
    - Draggable
    - Resizable
    - Mouse-wheel resizing
    - Red close button
    - Always on top
    - Double-click launches nova --ui
    - Right-click toggles controls
    - Escape closes the cat

IMPORTANT:
    The cat has NO cursor-following eye logic.
    The cat.png image is displayed as-is.

The plugin does not modify:
    - Nova model
    - Nova memory
    - Nova chat storage
    - Nova CPU priority
    - CPU affinity
    - other processes
    - Windows settings
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

# Gentle breathing.
BREATH_SPEED = 0.055
BREATH_AMOUNT = 0.035

# Animation update rate.
ANIMATION_INTERVAL_MS = 40

# Red close-button size.
CONTROL_SIZE_RATIO = 0.26

# Ctrl + drag resize sensitivity.
RESIZE_SENSITIVITY = 0.008


# ============================================================================
# FIND NOVA
# ============================================================================

def find_nova_command() -> list[str]:
    """
    Find the installed Nova command.

    Normally this will find:

        nova.exe

    If it cannot, fall back to:

        python -m novatrix.nova_cli
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
            f"[Nova Cat] Could not launch Nova GUI: {error}",
            file=sys.stderr,
            flush=True,
        )

        return False


# ============================================================================
# DETACHED CAT PROCESS
# ============================================================================

def launch_detached_cat() -> bool:
    """
    Start the actual cat as an independent Windows GUI process.

    This is the important part.

    `nova --cat` itself is only the launcher.

    The cat receives its own Python process, detached from the
    terminal that launched Nova.

    Closing CMD therefore does not close the cat.
    """

    cat_script = os.path.abspath(
        __file__
    )

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    if os.name == "nt":

        # Windows creation flags.
        #
        # DETACHED_PROCESS:
        #     Cat is not attached to the invoking console.
        #
        # CREATE_NEW_PROCESS_GROUP:
        #     Gives the child its own process group.
        #
        # CREATE_NO_WINDOW:
        #     Prevents a console window from being created for the
        #     Python child.
        #

        DETACHED_PROCESS = 0x00000008

        CREATE_NEW_PROCESS_GROUP = 0x00000200

        CREATE_NO_WINDOW = 0x08000000

        creation_flags = (
            DETACHED_PROCESS
            |
            CREATE_NEW_PROCESS_GROUP
            |
            CREATE_NO_WINDOW
        )

        command = [
            sys.executable,
            cat_script,
            "--cat-child",
        ]

        try:

            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                close_fds=True,
                creationflags=creation_flags,
            )

            return True

        except OSError as error:

            print(
                (
                    "[Nova Cat] Could not start detached cat: "
                    f"{error}"
                ),
                file=sys.stderr,
                flush=True,
            )

            return False

    # ------------------------------------------------------------------
    # Non-Windows
    # ------------------------------------------------------------------
    #
    # This plugin is primarily intended for Windows.
    #
    # We deliberately do not implement platform-specific process
    # detachment tricks for Linux/macOS.
    #

    print(
        "[Nova Cat] Detached cat mode is Windows-only.",
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
        # Borderless window
        # ------------------------------------------------------------------

        self.root.overrideredirect(
            True
        )

        # Keep cat above normal windows.
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

        self.resize_start_scale = (
            INITIAL_SCALE
        )

        # ------------------------------------------------------------------
        # Find image
        # ------------------------------------------------------------------

        self.image_path = self._find_image()

        if self.image_path is None:

            self.root.destroy()

            raise RuntimeError(
                "Nova Cat could not find cat.png.\n\n"
                "Expected:\n"
                "cat.png beside plugin.py"
            )

        # ------------------------------------------------------------------
        # Load image
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
        # Transparent color
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

            # Fallback.
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
        # Initial render
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

        self.canvas.bind(
            "<Button-1>",
            self._single_click,
            add="+",
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

        # ------------------------------------------------------------------
        # Begin breathing animation
        # ------------------------------------------------------------------

        self._animate()

    # ======================================================================
    # FIND IMAGE
    # ======================================================================

    def _find_image(self) -> str | None:
        """
        Find cat.png beside plugin.py.

        Installed structure:

            ~/.nova/plugins/cat/
                plugin.py
                cat.png
        """

        plugin_directory = os.path.dirname(
            os.path.abspath(__file__)
        )

        image_path = os.path.join(
            plugin_directory,
            CAT_IMAGE_NAME,
        )

        if os.path.isfile(
            image_path
        ):

            return image_path

        # Development fallback.
        current_path = os.path.join(
            os.getcwd(),
            CAT_IMAGE_NAME,
        )

        if os.path.isfile(
            current_path
        ):

            return current_path

        return None

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
    # BREATHING SIZE
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
    # IMAGE SCALING
    # ======================================================================

    def _scale_image(
        self,
        target_width: int,
        target_height: int,
    ):
        """
        Scale the pixel-art image.

        No eye manipulation occurs here.
        The supplied PNG is the complete cat.
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
        # Resize image
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

        # Clear the canvas and redraw ONLY the supplied cat image.
        self.canvas.delete(
            "all"
        )

        self.canvas.create_image(
            width // 2,
            height // 2,
            image=self.current_image,
            anchor="center",
            tags=("cat",),
        )

        # --------------------------------------------------------------
        # Optional controls
        # --------------------------------------------------------------

        if self.controls_visible:

            self._draw_controls()

        # --------------------------------------------------------------
        # Initial position
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

        # Advance animation phase.
        self.breath_phase += (
            BREATH_SPEED
        )

        # --------------------------------------------------------------
        # Preserve cat center while breathing.
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
        # Rebuild image with slightly changed scale.
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
    # CLOSE BUTTON
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
        # Red X box
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
        # X
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

        # Close button always wins.
        if self.controls_visible:

            if self._controls_hit(
                event.x,
                event.y,
            ):

                self._close()

                return

        # --------------------------------------------------------------
        # Ctrl + drag = resize
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
        # Normal drag = move
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

        # Do not toggle controls when clicking X.
        if self.controls_visible:

            if self._controls_hit(
                event.x,
                event.y,
            ):

                return

        # Plain click toggles control visibility.
        #
        # Double-click will subsequently trigger the GUI launch handler.
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
    # MOUSE WHEEL RESIZE
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
            self.scale
            +
            change
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

        # Preserve center.
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
# NOVA CLI CALLBACK
# ============================================================================

def run_cat(
    args,
    runtime,
):
    """
    Public Nova command:

        nova --cat

    This callback does NOT run the Tkinter loop itself.

    Instead it starts a completely detached child process.
    """

    del args
    del runtime

    started = launch_detached_cat()

    if started:

        print(
            "Nova Cat summoned. 🐈"
        )

    else:

        print(
            "Nova Cat could not be started."
        )


# ============================================================================
# NOVA PLUGIN
# ============================================================================

class CatPlugin(NovaPlugin):

    name = "cat"

    version = "1.3.0"

    description = (
        "Summon a detached animated desktop pixel cat."
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
                "Summon a detached animated pixel cat."
            ),
            action="store_true",
        )


# ============================================================================
# REQUIRED NOVA EXPORT
# ============================================================================

plugin = CatPlugin()


# ============================================================================
# DETACHED CHILD ENTRY POINT
# ============================================================================

if (
    __name__ == "__main__"
    and len(sys.argv) > 1
    and sys.argv[1] == "--cat-child"
):

    cat = CatWindow()

    cat.run()
