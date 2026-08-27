"""
Nova GUI Plugin
================

Single-file graphical frontend for Nova.

Install as:

    plugins/gui/plugin.py

Then launch:

    nova --ui

Architecture:
    GUI -> NovaRuntime -> existing Nova model/memory/tools

This plugin intentionally does NOT:
    - create another Qwen/Llama model
    - create another memory database
    - directly modify chat JSON files
    - parse sys.argv
    - implement a second web/PDF system
    - replace Nova's core CLI/chat systems

The concrete persistent-chat API is not part of the public Nova plugin
specification supplied to this plugin. Therefore NovaGUIBackend contains
a small runtime adapter that attempts to discover the existing chat API.
Once the real Nova source is available, that adapter should be replaced
with the exact concrete calls from Nova's implementation.
"""

from __future__ import annotations

import threading
import traceback
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Optional

from plugin_system import NovaPlugin


# ============================================================================
# Metadata
# ============================================================================

PLUGIN_NAME = "gui"
PLUGIN_VERSION = "1.0.0"
PLUGIN_API_VERSION = 1


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class ChatInfo:
    """A normalized representation of an existing Nova chat."""

    name: str
    identifier: str


@dataclass
class ChatMessage:
    """A normalized representation of a stored Nova message."""

    role: str
    content: str


# ============================================================================
# Nova backend adapter
# ============================================================================

class NovaGUIBackend:
    """
    Adapter between the GUI and NovaRuntime.

    The model-facing API is known from the Nova plugin contract:
        runtime.ask(...)
        runtime.think(...)
        runtime.generate(...)

    Chat-management APIs are not defined in the supplied specification,
    so this class attempts to discover them without creating replacement
    storage.

    Once the actual Nova source is available, this class is the ONLY part
    that should normally need adjustment.
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime

    # ----------------------------------------------------------------------
    # Model access
    # ----------------------------------------------------------------------

    def ask(self, message: str, thinking: bool = False) -> Any:
        """
        Use Nova's already-loaded model.

        Never creates another Llama/Qwen instance.
        """
        if thinking:
            return self.runtime.think(message)

        return self.runtime.ask(message)

    # ----------------------------------------------------------------------
    # Locate existing chat subsystem
    # ----------------------------------------------------------------------

    def _find_chat_manager(self) -> Any:
        """
        Find an existing Nova chat/memory manager.

        This is deliberately conservative. We do not create one if it
        cannot be found.
        """

        candidates = (
            "chat",
            "chats",
            "chat_manager",
            "memory",
        )

        for attribute_name in candidates:
            manager = getattr(
                self.runtime,
                attribute_name,
                None,
            )

            if manager is not None:
                return manager

        # Some implementations may expose the manager as a method.
        for attribute_name in (
            "get_chat_manager",
            "get_chats",
            "get_chat",
        ):
            attribute = getattr(
                self.runtime,
                attribute_name,
                None,
            )

            if callable(attribute):
                try:
                    manager = attribute()

                    if manager is not None:
                        return manager

                except TypeError:
                    # It may require an argument, so it isn't a manager
                    # getter we can use here.
                    continue
                except Exception:
                    continue

        raise RuntimeError(
            "NovaRuntime does not expose a recognized existing chat API. "
            "The GUI refuses to create its own chat database."
        )

    @staticmethod
    def _find_method(
        obj: Any,
        names: tuple[str, ...],
    ):
        for name in names:
            method = getattr(
                obj,
                name,
                None,
            )

            if callable(method):
                return method

        return None

    # ----------------------------------------------------------------------
    # List chats
    # ----------------------------------------------------------------------

    def list_chats(self) -> list[ChatInfo]:
        manager = self._find_chat_manager()

        method = self._find_method(
            manager,
            (
                "list_chats",
                "get_chats",
                "list",
                "names",
            ),
        )

        if method is None:
            raise RuntimeError(
                "Nova's existing chat manager does not expose a supported "
                "chat-listing method."
            )

        chats = method()

        return self._normalize_chat_list(chats)

    # ----------------------------------------------------------------------
    # Load chat
    # ----------------------------------------------------------------------

    def load_chat(
        self,
        identifier: str,
    ) -> list[ChatMessage]:

        manager = self._find_chat_manager()

        method = self._find_method(
            manager,
            (
                "load_chat",
                "get_chat",
                "open_chat",
                "read_chat",
                "history",
                "get_history",
            ),
        )

        if method is None:
            raise RuntimeError(
                "Nova's existing chat manager does not expose a supported "
                "chat-loading method."
            )

        result = method(identifier)

        return self._normalize_messages(result)

    # ----------------------------------------------------------------------
    # Create chat
    # ----------------------------------------------------------------------

    def create_chat(
        self,
        name: str,
    ) -> ChatInfo:

        manager = self._find_chat_manager()

        method = self._find_method(
            manager,
            (
                "create_chat",
                "new_chat",
                "create",
                "new",
            ),
        )

        if method is None:
            raise RuntimeError(
                "Nova's existing chat manager does not expose a supported "
                "chat-creation method."
            )

        result = method(name)

        return self._normalize_chat(
            result,
            fallback_name=name,
        )

    # ----------------------------------------------------------------------
    # Delete chat
    # ----------------------------------------------------------------------

    def delete_chat(
        self,
        identifier: str,
    ) -> None:

        manager = self._find_chat_manager()

        method = self._find_method(
            manager,
            (
                "delete_chat",
                "remove_chat",
                "delete",
                "remove",
            ),
        )

        if method is None:
            raise RuntimeError(
                "Nova's existing chat manager does not expose a supported "
                "chat-deletion method."
            )

        method(identifier)

    # ----------------------------------------------------------------------
    # Persistent message operation
    # ----------------------------------------------------------------------

    def send_message(
        self,
        identifier: str,
        message: str,
        thinking: bool,
    ) -> Any:

        manager = self._find_chat_manager()

        method = self._find_method(
            manager,
            (
                "send_message",
                "append_and_ask",
                "ask",
                "chat",
                "send",
            ),
        )

        if method is None:
            raise RuntimeError(
                "Nova's existing chat manager does not expose a supported "
                "persistent message method."
            )

        # Try the most explicit API shape first.
        attempts = (
            lambda: method(
                identifier,
                message,
                thinking=thinking,
            ),
            lambda: method(
                chat=identifier,
                message=message,
                thinking=thinking,
            ),
            lambda: method(
                identifier,
                message,
                thinking,
            ),
            lambda: method(
                identifier,
                message,
            ),
        )

        last_error: Optional[Exception] = None

        for attempt in attempts:
            try:
                return attempt()

            except TypeError as exc:
                last_error = exc
                continue

        raise RuntimeError(
            "Nova's persistent chat message API does not match any "
            "supported adapter signature."
        ) from last_error

    # ----------------------------------------------------------------------
    # Normalization
    # ----------------------------------------------------------------------

    @staticmethod
    def _normalize_chat_list(
        value: Any,
    ) -> list[ChatInfo]:

        if value is None:
            return []

        if isinstance(value, dict):
            value = list(value.values())

        if not isinstance(value, (list, tuple)):
            raise RuntimeError(
                "Nova returned an unsupported chat-list format."
            )

        result: list[ChatInfo] = []

        for item in value:
            result.append(
                NovaGUIBackend._normalize_chat(item)
            )

        return result

    @staticmethod
    def _normalize_chat(
        item: Any,
        fallback_name: Optional[str] = None,
    ) -> ChatInfo:

        if isinstance(item, ChatInfo):
            return item

        # Some simple Nova APIs may return names directly.
        if isinstance(item, str):
            return ChatInfo(
                name=item,
                identifier=item,
            )

        if isinstance(item, dict):

            name = (
                item.get("name")
                or item.get("title")
                or item.get("chat_name")
                or fallback_name
                or item.get("id")
                or item.get("identifier")
            )

            identifier = (
                item.get("id")
                or item.get("identifier")
                or item.get("chat_id")
                or item.get("name")
                or item.get("title")
                or fallback_name
            )

            if name is None or identifier is None:
                raise RuntimeError(
                    "Nova returned a chat object without a usable name "
                    "or identifier."
                )

            return ChatInfo(
                name=str(name),
                identifier=str(identifier),
            )

        name = (
            getattr(item, "name", None)
            or getattr(item, "title", None)
            or fallback_name
        )

        identifier = (
            getattr(item, "identifier", None)
            or getattr(item, "id", None)
            or getattr(item, "chat_id", None)
            or name
        )

        if name is None or identifier is None:
            raise RuntimeError(
                f"Unsupported Nova chat object: {type(item).__name__}"
            )

        return ChatInfo(
            name=str(name),
            identifier=str(identifier),
        )

    @staticmethod
    def _normalize_messages(
        value: Any,
    ) -> list[ChatMessage]:

        if value is None:
            return []

        if isinstance(value, dict):

            for key in (
                "messages",
                "history",
                "chat",
                "conversation",
            ):
                if key in value:
                    value = value[key]
                    break

        if not isinstance(value, (list, tuple)):
            raise RuntimeError(
                "Nova returned an unsupported message-history format."
            )

        result: list[ChatMessage] = []

        for item in value:

            if isinstance(item, ChatMessage):
                result.append(item)
                continue

            if isinstance(item, dict):

                role = (
                    item.get("role")
                    or item.get("speaker")
                    or item.get("author")
                    or "assistant"
                )

                content = (
                    item.get("content")
                    if item.get("content") is not None
                    else item.get("message")
                )

                if content is None:
                    continue

                result.append(
                    ChatMessage(
                        role=str(role),
                        content=str(content),
                    )
                )

                continue

            role = getattr(
                item,
                "role",
                "assistant",
            )

            content = getattr(
                item,
                "content",
                None,
            )

            if content is None:
                content = getattr(
                    item,
                    "message",
                    None,
                )

            if content is None:
                continue

            result.append(
                ChatMessage(
                    role=str(role),
                    content=str(content),
                )
            )

        return result


# ============================================================================
# GUI
# ============================================================================

class NovaGUI:

    WINDOW_TITLE = "Nova"
    DEFAULT_GEOMETRY = "1200x760"

    BG = "#f7f7f8"
    SIDEBAR_BG = "#ededf0"
    TEXT = "#202123"
    MUTED = "#6f6f78"
    BORDER = "#d6d6da"
    USER_BG = "#ffffff"
    NOVA_BG = "#eeeeF1"
    ACTIVE_BG = "#ddddE2"

    def __init__(
        self,
        runtime: Any,
    ):

        self.runtime = runtime
        self.backend = NovaGUIBackend(runtime)

        self.root = tk.Tk()

        self.root.title(
            self.WINDOW_TITLE
        )

        self.root.geometry(
            self.DEFAULT_GEOMETRY
        )

        self.root.minsize(
            900,
            600,
        )

        self.current_chat: Optional[ChatInfo] = None
        self.thinking = False
        self.generating = False

        self._configure_styles()
        self._build_ui()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _configure_styles(self):

        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "TButton",
            font=("Segoe UI", 10),
            padding=(10, 7),
        )

    # ------------------------------------------------------------------
    # Main UI
    # ------------------------------------------------------------------

    def _build_ui(self):

        self.root.configure(
            bg=self.BG,
        )

        self.root.grid_rowconfigure(
            1,
            weight=1,
        )

        self.root.grid_columnconfigure(
            1,
            weight=1,
        )

        self._build_header()
        self._build_sidebar()
        self._build_conversation()
        self._build_input()

        self.show_empty_state()

        self.root.after(
            100,
            self.load_chat_list,
        )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self):

        self.header = tk.Frame(
            self.root,
            bg=self.BG,
            height=58,
        )

        self.header.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
        )

        self.header.grid_propagate(False)

        tk.Label(
            self.header,
            text="Nova",
            font=("Segoe UI Semibold", 17),
            fg=self.TEXT,
            bg=self.BG,
        ).pack(
            side="left",
            padx=22,
        )

        self.status_label = tk.Label(
            self.header,
            text="Loading...",
            font=("Segoe UI", 9),
            fg=self.MUTED,
            bg=self.BG,
        )

        self.status_label.pack(
            side="right",
            padx=22,
        )

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self):

        self.sidebar = tk.Frame(
            self.root,
            width=270,
            bg=self.SIDEBAR_BG,
        )

        self.sidebar.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        self.sidebar.grid_propagate(False)

        self.sidebar.grid_rowconfigure(
            2,
            weight=1,
        )

        tk.Label(
            self.sidebar,
            text="Chats",
            font=("Segoe UI Semibold", 13),
            fg=self.TEXT,
            bg=self.SIDEBAR_BG,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=16,
            pady=(15, 8),
        )

        ttk.Button(
            self.sidebar,
            text="+ New Chat",
            command=self.create_chat,
        ).grid(
            row=1,
            column=0,
            sticky="ew",
            padx=12,
            pady=(0, 10),
        )

        list_container = tk.Frame(
            self.sidebar,
            bg=self.SIDEBAR_BG,
        )

        list_container.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=8,
        )

        list_container.grid_rowconfigure(
            0,
            weight=1,
        )

        list_container.grid_columnconfigure(
            0,
            weight=1,
        )

        self.chat_canvas = tk.Canvas(
            list_container,
            bg=self.SIDEBAR_BG,
            highlightthickness=0,
        )

        self.chat_canvas.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            list_container,
            orient="vertical",
            command=self.chat_canvas.yview,
        )

        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.chat_canvas.configure(
            yscrollcommand=scrollbar.set,
        )

        self.chat_list_frame = tk.Frame(
            self.chat_canvas,
            bg=self.SIDEBAR_BG,
        )

        self.chat_window = self.chat_canvas.create_window(
            0,
            0,
            anchor="nw",
            window=self.chat_list_frame,
        )

        self.chat_list_frame.bind(
            "<Configure>",
            lambda event: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")
            ),
        )

        self.chat_canvas.bind(
            "<Configure>",
            self._resize_sidebar_content,
        )

    def _resize_sidebar_content(
        self,
        event,
    ):

        self.chat_canvas.itemconfigure(
            self.chat_window,
            width=event.width,
        )

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def _build_conversation(self):

        self.main = tk.Frame(
            self.root,
            bg=self.BG,
        )

        self.main.grid(
            row=1,
            column=1,
            sticky="nsew",
        )

        self.main.grid_rowconfigure(
            0,
            weight=1,
        )

        self.main.grid_columnconfigure(
            0,
            weight=1,
        )

        self.conversation_canvas = tk.Canvas(
            self.main,
            bg=self.BG,
            highlightthickness=0,
        )

        self.conversation_canvas.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            self.main,
            orient="vertical",
            command=self.conversation_canvas.yview,
        )

        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.conversation_canvas.configure(
            yscrollcommand=scrollbar.set,
        )

        self.message_frame = tk.Frame(
            self.conversation_canvas,
            bg=self.BG,
        )

        self.message_window = self.conversation_canvas.create_window(
            0,
            0,
            anchor="nw",
            window=self.message_frame,
        )

        self.message_frame.bind(
            "<Configure>",
            lambda event: self.conversation_canvas.configure(
                scrollregion=self.conversation_canvas.bbox("all")
            ),
        )

        self.conversation_canvas.bind(
            "<Configure>",
            self._resize_message_content,
        )

    def _resize_message_content(
        self,
        event,
    ):

        self.conversation_canvas.itemconfigure(
            self.message_window,
            width=event.width,
        )

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def _build_input(self):

        self.input_area = tk.Frame(
            self.main,
            bg=self.BG,
        )

        self.input_area.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=14,
        )

        self.input_area.grid_columnconfigure(
            0,
            weight=1,
        )

        self.input_box = tk.Text(
            self.input_area,
            height=4,
            wrap="word",
            font=("Segoe UI", 11),
            bg="#ffffff",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="solid",
            borderwidth=1,
        )

        self.input_box.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        self.thinking_button = tk.Button(
            self.input_area,
            text="🧠 OFF",
            command=self.toggle_thinking,
            font=("Segoe UI Semibold", 10),
            bg=self.BG,
            fg=self.TEXT,
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=8,
        )

        self.thinking_button.grid(
            row=0,
            column=1,
            padx=(8, 6),
            sticky="s",
        )

        self.send_button = ttk.Button(
            self.input_area,
            text="Send",
            command=self.send_message,
        )

        self.send_button.grid(
            row=0,
            column=2,
            sticky="s",
        )

        self.input_box.bind(
            "<Return>",
            self._handle_return,
        )

    # ------------------------------------------------------------------
    # Chat list
    # ------------------------------------------------------------------

    def load_chat_list(self):

        self.status_label.config(
            text="Loading chats..."
        )

        thread = threading.Thread(
            target=self._load_chat_list_worker,
            daemon=True,
        )

        thread.start()

    def _load_chat_list_worker(self):

        try:
            chats = self.backend.list_chats()

        except Exception as exc:

            self.root.after(
                0,
                lambda: self._show_error(
                    "Could not load Nova chats.",
                    exc,
                ),
            )

            return

        self.root.after(
            0,
            lambda: self._populate_chat_list(chats),
        )

    def _populate_chat_list(
        self,
        chats: list[ChatInfo],
    ):

        for widget in self.chat_list_frame.winfo_children():
            widget.destroy()

        for chat in chats:

            row = tk.Frame(
                self.chat_list_frame,
                bg=self.SIDEBAR_BG,
            )

            row.pack(
                fill="x",
                padx=2,
                pady=2,
            )

            button = tk.Button(
                row,
                text=chat.name,
                anchor="w",
                font=("Segoe UI", 10),
                fg=self.TEXT,
                bg=self.SIDEBAR_BG,
                activebackground=self.ACTIVE_BG,
                relief="flat",
                borderwidth=0,
                padx=10,
                pady=8,
                command=lambda c=chat: self.open_chat(c),
            )

            button.pack(
                side="left",
                fill="x",
                expand=True,
            )

            delete = tk.Button(
                row,
                text="⋯",
                font=("Segoe UI Semibold", 11),
                fg=self.MUTED,
                bg=self.SIDEBAR_BG,
                activebackground=self.ACTIVE_BG,
                relief="flat",
                borderwidth=0,
                command=lambda c=chat: self.delete_chat(c),
            )

            delete.pack(
                side="right",
                padx=(0, 4),
            )

        self.status_label.config(
            text="Nova ready."
        )

    # ------------------------------------------------------------------
    # Create chat
    # ------------------------------------------------------------------

    def create_chat(self):

        name = simpledialog.askstring(
            "New Chat",
            "Chat name:",
            parent=self.root,
        )

        if name is None:
            return

        name = name.strip()

        if not name:
            return

        self.status_label.config(
            text="Creating chat..."
        )

        thread = threading.Thread(
            target=self._create_chat_worker,
            args=(name,),
            daemon=True,
        )

        thread.start()

    def _create_chat_worker(
        self,
        name: str,
    ):

        try:
            chat = self.backend.create_chat(name)

        except Exception as exc:

            self.root.after(
                0,
                lambda: self._show_error(
                    "Could not create chat.",
                    exc,
                ),
            )

            return

        self.root.after(
            0,
            lambda: self._chat_created(chat),
        )

    def _chat_created(
        self,
        chat: ChatInfo,
    ):

        self.current_chat = chat

        self._refresh_chat_list()

        self._render_chat(
            chat,
            [],
        )

    # ------------------------------------------------------------------
    # Open chat
    # ------------------------------------------------------------------

    def open_chat(
        self,
        chat: ChatInfo,
    ):

        self.current_chat = chat

        self.status_label.config(
            text=f"Opening {chat.name}..."
        )

        self._clear_messages()

        loading = tk.Label(
            self.message_frame,
            text="Loading conversation...",
            font=("Segoe UI", 11),
            fg=self.MUTED,
            bg=self.BG,
        )

        loading.pack(
            pady=60,
        )

        thread = threading.Thread(
            target=self._load_chat_worker,
            args=(chat,),
            daemon=True,
        )

        thread.start()

    def _load_chat_worker(
        self,
        chat: ChatInfo,
    ):

        try:
            messages = self.backend.load_chat(
                chat.identifier
            )

        except Exception as exc:

            self.root.after(
                0,
                lambda: self._show_error(
                    "This chat could not be loaded.",
                    exc,
                ),
            )

            return

        self.root.after(
            0,
            lambda: self._render_chat(
                chat,
                messages,
            ),
        )

    def _render_chat(
        self,
        chat: ChatInfo,
        messages: list[ChatMessage],
    ):

        self._clear_messages()

        title = tk.Label(
            self.message_frame,
            text=chat.name,
            font=("Segoe UI Semibold", 16),
            fg=self.TEXT,
            bg=self.BG,
            anchor="w",
        )

        title.pack(
            fill="x",
            padx=40,
            pady=(28, 18),
        )

        for message in messages:
            self._display_message(
                message.role,
                message.content,
            )

        self.status_label.config(
            text="Nova ready."
        )

        self._scroll_bottom()

    # ------------------------------------------------------------------
    # Delete chat
    # ------------------------------------------------------------------

    def delete_chat(
        self,
        chat: ChatInfo,
    ):

        confirmed = messagebox.askyesno(
            "Delete Chat",
            (
                f'Delete chat "{chat.name}"?\n\n'
                "This will permanently delete its memory."
            ),
            parent=self.root,
        )

        if not confirmed:
            return

        self.status_label.config(
            text="Deleting chat..."
        )

        thread = threading.Thread(
            target=self._delete_chat_worker,
            args=(chat,),
            daemon=True,
        )

        thread.start()

    def _delete_chat_worker(
        self,
        chat: ChatInfo,
    ):

        try:
            self.backend.delete_chat(
                chat.identifier
            )

        except Exception as exc:

            self.root.after(
                0,
                lambda: self._show_error(
                    "Could not delete chat.",
                    exc,
                ),
            )

            return

        self.root.after(
            0,
            lambda: self._chat_deleted(chat),
        )

    def _chat_deleted(
        self,
        chat: ChatInfo,
    ):

        if (
            self.current_chat is not None
            and self.current_chat.identifier
            == chat.identifier
        ):
            self.current_chat = None
            self.show_empty_state()

        self._refresh_chat_list()

    def _refresh_chat_list(self):

        self.load_chat_list()

    # ------------------------------------------------------------------
    # Message display
    # ------------------------------------------------------------------

    def _clear_messages(self):

        for widget in self.message_frame.winfo_children():
            widget.destroy()

    def show_empty_state(self):

        self._clear_messages()

        frame = tk.Frame(
            self.message_frame,
            bg=self.BG,
        )

        frame.pack(
            expand=True,
            fill="both",
            pady=130,
        )

        tk.Label(
            frame,
            text="Nova",
            font=("Segoe UI Semibold", 25),
            fg=self.TEXT,
            bg=self.BG,
        ).pack(
            pady=(0, 8),
        )

        tk.Label(
            frame,
            text="Select a chat or create a new one.",
            font=("Segoe UI", 11),
            fg=self.MUTED,
            bg=self.BG,
        ).pack()

    def _display_message(
        self,
        role: str,
        content: str,
    ):

        is_user = role.lower() in {
            "user",
            "human",
        }

        outer = tk.Frame(
            self.message_frame,
            bg=self.BG,
        )

        outer.pack(
            fill="x",
            padx=38,
            pady=7,
        )

        tk.Label(
            outer,
            text="You" if is_user else "Nova",
            font=("Segoe UI Semibold", 10),
            fg=self.TEXT,
            bg=self.BG,
            anchor="w",
        ).pack(
            fill="x",
            pady=(0, 4),
        )

        bubble = tk.Frame(
            outer,
            bg=self.USER_BG
            if is_user
            else self.NOVA_BG,
        )

        bubble.pack(
            fill="x",
        )

        text = tk.Text(
            bubble,
            wrap="word",
            font=(
                "Consolas"
                if self._looks_like_code(content)
                else "Segoe UI"
            ),
            bg=(
                self.USER_BG
                if is_user
                else self.NOVA_BG
            ),
            fg=self.TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )

        text.insert(
            "1.0",
            content,
        )

        text.configure(
            state="disabled",
        )

        line_count = content.count("\n") + 1

        text.configure(
            height=max(
                2,
                min(
                    25,
                    line_count,
                ),
            ),
        )

        text.pack(
            fill="x",
            padx=14,
            pady=12,
        )

    @staticmethod
    def _looks_like_code(
        text: str,
    ) -> bool:

        stripped = text.strip()

        return (
            stripped.startswith("```")
            or "\n    " in text
        )

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _handle_return(
        self,
        event,
    ):

        # Shift+Enter = newline.
        if event.state & 0x0001:
            return None

        self.send_message()

        return "break"

    def toggle_thinking(self):

        self.thinking = not self.thinking

        if self.thinking:

            self.thinking_button.config(
                text="🧠 ON",
                bg=self.ACTIVE_BG,
                activebackground="#d2d2d6",
            )

        else:

            self.thinking_button.config(
                text="🧠 OFF",
                bg=self.BG,
                activebackground="#e5e5e8",
            )

    # ------------------------------------------------------------------
    # Send message
    # ------------------------------------------------------------------

    def send_message(self):

        if self.generating:
            return

        if self.current_chat is None:

            messagebox.showinfo(
                "No Chat Selected",
                "Create or select a chat first.",
                parent=self.root,
            )

            return

        message = self.input_box.get(
            "1.0",
            "end-1c",
        ).strip()

        if not message:
            return

        chat = self.current_chat
        thinking = self.thinking

        self.input_box.delete(
            "1.0",
            "end",
        )

        self._display_message(
            "user",
            message,
        )

        self._set_generating(
            True
        )

        thread = threading.Thread(
            target=self._send_message_worker,
            args=(
                chat.identifier,
                message,
                thinking,
            ),
            daemon=True,
        )

        thread.start()

        self._scroll_bottom()

    def _send_message_worker(
        self,
        identifier: str,
        message: str,
        thinking: bool,
    ):

        try:

            result = self.backend.send_message(
                identifier,
                message,
                thinking,
            )

        except Exception as primary_error:

            # If the persistent-chat API is unavailable, use NovaRuntime
            # directly rather than silently creating replacement storage.
            try:

                result = self.backend.ask(
                    message,
                    thinking=thinking,
                )

            except Exception as fallback_error:

                self.root.after(
                    0,
                    lambda: self._show_error(
                        "Nova could not generate a response.",
                        fallback_error,
                    ),
                )

                self.root.after(
                    0,
                    lambda: self._set_generating(False),
                )

                return

            # The fallback is intentionally not treated as persistent
            # history. The actual Nova chat implementation will need to
            # be used once its concrete API is known.

            print(
                "[Nova GUI] Persistent chat API failed; "
                "used runtime.ask()/think() fallback.",
                flush=True,
            )

            print(
                f"[Nova GUI] Original error: {primary_error}",
                flush=True,
            )

        answer = self._extract_response(
            result
        )

        self.root.after(
            0,
            lambda: self._receive_response(answer),
        )

    @staticmethod
    def _extract_response(
        result: Any,
    ) -> str:

        if isinstance(result, str):
            return result

        if isinstance(result, dict):

            for key in (
                "answer",
                "response",
                "content",
                "message",
                "text",
            ):

                value = result.get(key)

                if value is not None:
                    return str(value)

        return str(result)

    def _receive_response(
        self,
        answer: str,
    ):

        self._display_message(
            "assistant",
            answer,
        )

        self._set_generating(
            False
        )

        self._scroll_bottom()

    # ------------------------------------------------------------------
    # UX
    # ------------------------------------------------------------------

    def _set_generating(
        self,
        value: bool,
    ):

        self.generating = value

        if value:

            self.status_label.config(
                text="Generating..."
            )

            self.send_button.state(
                ["disabled"]
            )

        else:

            self.status_label.config(
                text="Nova ready."
            )

            self.send_button.state(
                ["!disabled"]
            )

    def _scroll_bottom(self):

        self.root.after(
            30,
            lambda: self.conversation_canvas.yview_moveto(
                1.0
            ),
        )

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def _show_error(
        self,
        message: str,
        exception: Exception,
    ):

        print(
            f"[Nova GUI] {message}",
            flush=True,
        )

        traceback.print_exc()

        self.status_label.config(
            text="Error"
        )

        messagebox.showerror(
            "Nova",
            message,
            parent=self.root,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):

        self.root.mainloop()


# ============================================================================
# Nova plugin entry point
# ============================================================================

def run_ui(
    args,
    runtime,
):
    """
    CLI callback for:

        nova --ui
    """

    del args

    gui = NovaGUI(
        runtime
    )

    gui.run()

    return None


class GUIPlugin(NovaPlugin):

    name = PLUGIN_NAME
    version = PLUGIN_VERSION
    description = "Desktop graphical interface for Nova."
    plugin_api_version = PLUGIN_API_VERSION

    def register(
        self,
        nova,
    ):

        nova.register_cli_command(
            name="ui",
            callback=run_ui,
            help_text="Launch the Nova graphical interface.",
            action="store_true",
        )


# ============================================================================
# Plugin export
# ============================================================================

plugin = GUIPlugin()
