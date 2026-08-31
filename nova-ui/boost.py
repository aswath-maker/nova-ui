"""
Nova Process Priority Plugin
============================

Commands:

    nova --boost
    nova --normal

--boost
    Sets the CURRENT Nova process to Windows HIGH_PRIORITY_CLASS.

--normal
    Sets the CURRENT Nova process back to Windows NORMAL_PRIORITY_CLASS.

This plugin changes ONLY Nova's own Windows process priority.

It does NOT:
    - inspect or modify other processes
    - kill/suspend/terminate processes
    - change CPU affinity
    - change CPU cores
    - change processor groups
    - change thread counts
    - change Qwen/llama.cpp configuration
    - change memory settings
    - change Windows power plans
    - change the registry
    - change services
    - change security software
    - change network settings
    - request administrator privileges
    - modify Nova's model, memory, GUI, web, or PDF systems

Windows only.
"""

from __future__ import annotations

import ctypes
import os

from novatrix.plugin_system import NovaPlugin


# ============================================================================
# Windows priority classes
# ============================================================================

NORMAL_PRIORITY_CLASS = 0x00000020
HIGH_PRIORITY_CLASS = 0x00000080


# ============================================================================
# Windows process priority helper
# ============================================================================

def _set_current_process_priority(priority_class: int) -> tuple[bool, str]:
    """
    Change the priority class of the CURRENT process only.

    The plugin callback executes inside Nova's process, therefore
    GetCurrentProcess() refers to Nova itself.

    No process enumeration or PID lookup is performed.
    """

    if os.name != "nt":
        return (
            False,
            "Process priority control is Windows-only.",
        )

    try:
        kernel32 = ctypes.WinDLL(
            "kernel32",
            use_last_error=True,
        )

        # ------------------------------------------------------------------
        # GetCurrentProcess
        # ------------------------------------------------------------------
        #
        # This returns a pseudo-handle for the process currently executing
        # this code. Since Nova executes the plugin callback in-process,
        # this is Nova's own process.
        #

        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p

        process_handle = kernel32.GetCurrentProcess()

        if not process_handle:

            error_code = ctypes.get_last_error()

            return (
                False,
                (
                    "Could not obtain Nova's current process handle. "
                    f"Windows error code: {error_code}."
                ),
            )

        # ------------------------------------------------------------------
        # SetPriorityClass
        # ------------------------------------------------------------------

        kernel32.SetPriorityClass.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]

        kernel32.SetPriorityClass.restype = ctypes.c_int

        result = kernel32.SetPriorityClass(
            process_handle,
            priority_class,
        )

        if not result:

            error_code = ctypes.get_last_error()

            return (
                False,
                (
                    "Windows refused the Nova process priority change. "
                    f"Windows error code: {error_code}."
                ),
            )

        # ------------------------------------------------------------------
        # Verify
        # ------------------------------------------------------------------

        kernel32.GetPriorityClass.argtypes = [
            ctypes.c_void_p,
        ]

        kernel32.GetPriorityClass.restype = ctypes.c_uint32

        actual_priority = kernel32.GetPriorityClass(
            process_handle
        )

        if actual_priority != priority_class:

            return (
                False,
                "Windows did not report the requested Nova priority class.",
            )

        return (
            True,
            "Priority change applied.",
        )

    except Exception as error:

        # The plugin must never crash Nova merely because the priority
        # operation failed.

        return (
            False,
            f"Could not change Nova process priority: {error}",
        )


# ============================================================================
# --boost
# ============================================================================

def boost_command(
    args,
    runtime,
):
    """
    Command:

        nova --boost

    Set Nova itself to HIGH priority.
    """

    del args
    del runtime

    success, message = _set_current_process_priority(
        HIGH_PRIORITY_CLASS
    )

    if success:

        print(
            "Nova: process priority is now HIGH."
        )

    else:

        print(
            f"Nova: {message}"
        )


# ============================================================================
# --normal
# ============================================================================

def normal_command(
    args,
    runtime,
):
    """
    Command:

        nova --normal

    Return Nova itself to normal Windows process priority.
    """

    del args
    del runtime

    success, message = _set_current_process_priority(
        NORMAL_PRIORITY_CLASS
    )

    if success:

        print(
            "Nova: process priority returned to NORMAL."
        )

    else:

        print(
            f"Nova: {message}"
        )


# ============================================================================
# Plugin
# ============================================================================

class ProcessPriorityPlugin(NovaPlugin):

    name = "process_priority"
    version = "1.0.0"
    description = (
        "Control Nova's own Windows process priority."
    )
    plugin_api_version = 1

    def register(
        self,
        nova_runtime,
    ):
        """
        Register exactly the two requested controls:

            --boost
            --normal
        """

        nova_runtime.register_cli_command(
            name="boost",
            callback=boost_command,
            help_text=(
                "Set the Nova process to HIGH Windows priority."
            ),
            action="store_true",
        )

        nova_runtime.register_cli_command(
            name="normal",
            callback=normal_command,
            help_text=(
                "Return the Nova process to NORMAL Windows priority."
            ),
            action="store_true",
        )


# ============================================================================
# Required Nova plugin export
# ============================================================================

plugin = ProcessPriorityPlugin()