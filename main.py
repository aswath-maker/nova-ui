"""
Nova GUI Plugin
===============

Single-file graphical frontend for Novatrix.

Launch:
    nova --ui

Architecture:

    GUI
      |
      +--> novatrix.chats
      |
      +--> novatrix.nova
      |
      +--> novatrix.web
      |
      +--> novatrix.pdf
      |
      +--> existing Nova/Qwen runtime

This plugin does NOT create:
    - another model
    - another chat database
    - another memory system
    - another web-search system
    - another PDF parser

The GUI is simply another frontend to Nova.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

from novatrix.chats import (
    chat_exists,
    create_chat,
    delete_chat,
    list_chats,
    open_chat,
)

from novatrix.nova import (
    nova,
    read_pdf,
    search_with_sources,
)

from novatrix.pdf import parse_pdf_control
from novatrix.web import parse_chat_controls
from novatrix.plugin_system import NovaPlugin


# ============================================================================
# THEME
# ============================================================================

BG = "#000000"

SIDEBAR = "#0a0a0a"
SIDEBAR_HOVER = "#171717"
SIDEBAR_ACTIVE = "#1c1c1c"

SURFACE = "#121212"
SURFACE_HOVER = "#191919"

BORDER = "#292929"

TEXT = "#f5f5f5"
TEXT_SECONDARY = "#b5b5b5"
TEXT_MUTED = "#737373"

WHITE = "#ffffff"
BLACK = "#000000"

FONT = "Segoe UI"

WINDOW_WIDTH = 1250
WINDOW_HEIGHT = 800


# ============================================================================
# SIMPLE DATA OBJECT
# ============================================================================

class ChatInfo:

    def __init__(
        self,
        name: str,
        messages: int = 0,
    ):
        self.name = name
        self.messages = messages


# ============================================================================
# NOVA BACKEND
# ============================================================================

class NovaBackend:
    """
    Thin adapter over the actual Novatrix 0.1.0 implementation.

    Persistent chats are managed through novatrix.chats.
    Model generation is handled through novatrix.nova.
    """

    def __init__(self):
        self.summary_interval = 10

    # ----------------------------------------------------------------------
    # Chat listing
    # ----------------------------------------------------------------------

    def list_chats(self) -> list[ChatInfo]:

        result = list_chats()

        chats = []

        for item in result:

            chats.append(
                ChatInfo(
                    name=item.get("name", "Unnamed Chat"),
                    messages=item.get("messages", 0),
                )
            )

        return chats

    # ----------------------------------------------------------------------
    # Chat creation
    # ----------------------------------------------------------------------

    def create_chat(
        self,
        name: str,
    ):

        return create_chat(
            name,
            summary_interval=self.summary_interval,
        )

    # ----------------------------------------------------------------------
    # Chat opening
    # ----------------------------------------------------------------------

    def open_chat(
        self,
        name: str,
    ):

        return open_chat(name)

    # ----------------------------------------------------------------------
    # Chat deletion
    # ----------------------------------------------------------------------

    def delete_chat(
        self,
        name: str,
    ):

        chat = open_chat(name)

        if chat is None:

            raise RuntimeError(
                f'Chat "{name}" does not exist.'
            )

        chat.delete()

    # ----------------------------------------------------------------------
    # Send message
    # ----------------------------------------------------------------------

    def send_message(
        self,
        chat_name: str,
        message: str,
        thinking: bool = False,
    ) -> str:

        chat = open_chat(chat_name)

        if chat is None:

            raise RuntimeError(
                f'Could not open chat "{chat_name}".'
            )

        # ==============================================================
        # PDF
        # ==============================================================

        pdf_request = parse_pdf_control(message)

        if pdf_request:

            if not pdf_request.get("path"):

                return (
                    "Usage: `@pdf file.pdf [question]`"
                )

            pdf_name = pdf_request["path"]

            question = pdf_request.get(
                "question"
            )

            use_thinking = bool(
                pdf_request.get(
                    "thinking",
                    False,
                )
            )

            chat.add_pdf_action(
                pdf_name,
                question=question,
                thinking=use_thinking,
            )

            try:

                answer = read_pdf(
                    pdf_name,
                    prompt=question,
                    think=use_thinking,
                )

            except Exception as error:

                answer = (
                    f"Error reading PDF: {error}"
                )

            chat.add_pdf_response(
                answer,
                pdf_name,
                thinking=use_thinking,
            )

            self._maybe_summarize(chat)

            return answer

        # ==============================================================
        # WEB
        # ==============================================================

        message, web_requested, parsed_thinking = (
            parse_chat_controls(message)
        )

        if web_requested:

            use_thinking = bool(
                parsed_thinking
            )

            result = search_with_sources(
                message,
                think=use_thinking,
            )

            answer = result.get(
                "answer",
                "",
            )

            sources = result.get(
                "sources",
                [],
            )

            # Persist the exact web event through Nova's chat system.
            chat.add_web_search_action(
                message,
                sources=sources,
                thinking=use_thinking,
            )

            chat.add_web_search_response(
                answer,
                query=message,
                sources=sources,
                thinking=use_thinking,
            )

            if sources:

                answer += (
                    "\n\nSources:\n"
                    +
                    "\n".join(
                        f"- {source.get('url', '')}"
                        for source in sources
                        if source.get("url")
                    )
                )

            self._maybe_summarize(chat)

            return answer

        # ==============================================================
        # EXPLICIT @think
        # ==============================================================

        if message.strip().startswith("@think "):

            thinking = True

            message = (
                message[7:]
                .strip()
            )

        # ==============================================================
        # PREPARE USER MESSAGE
        # ==============================================================

        if thinking:

            user_content = (
                "/think\n"
                + message
            )

        else:

            user_content = (
                "/no_think\n"
                + message
            )

        # ==============================================================
        # PERSIST USER MESSAGE
        # ==============================================================

        chat.add_user_message(
            user_content,
            action="local",
            web_searched=False,
            thinking=thinking,
        )

        # ==============================================================
        # BUILD MODEL CONTEXT
        # ==============================================================

        context = chat.get_context_for_model()

        # ==============================================================
        # USE EXISTING NOVA MODEL
        # ==============================================================

        response = nova.create_chat_completion(
            messages=context,
            max_tokens=500,
        )

        try:

            answer = (
                response["choices"][0]["message"]["content"]
            )

        except (
            KeyError,
            TypeError,
            IndexError,
        ) as error:

            raise RuntimeError(
                "Nova returned an unexpected response format."
            ) from error

        # ==============================================================
        # PERSIST ASSISTANT MESSAGE
        # ==============================================================

        chat.add_assistant_message(
            answer,
            thinking=thinking,
        )

        # ==============================================================
        # MEMORY SUMMARY
        # ==============================================================

        self._maybe_summarize(chat)

        return answer

    # ----------------------------------------------------------------------
    # Memory summary
    # ----------------------------------------------------------------------

    @staticmethod
    def _maybe_summarize(chat):

        try:

            if chat.should_summarize():

                chat.create_summary()

        except Exception as error:

            print(
                f"[Nova GUI] Memory summary failed: {error}",
                flush=True,
            )


# ============================================================================
# NOVA GUI
# ============================================================================

class NovaGUI:

    def __init__(self):

        self.backend = NovaBackend()

        # Currently selected Nova chat.
        self.current_chat: str | None = None

        # Thinking toggle.
        self.thinking = False

        # Prevent simultaneous requests.
        self.generating = False

        # ------------------------------------------------------------------
        # GUI display history
        #
        # This is NOT a second database.
        #
        # Nova remains the persistent source of truth.
        # This list merely represents what's currently displayed in the
        # open GUI conversation.
        # ------------------------------------------------------------------

        self.displayed_messages: list[dict[str, str]] = []

        # ------------------------------------------------------------------
        # Tk root
        # ------------------------------------------------------------------

        self.root = tk.Tk()

        self.root.title(
            "Nova"
        )

        self.root.geometry(
            f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}"
        )

        self.root.minsize(
            900,
            600,
        )

        self.root.configure(
            bg=BG,
        )

        self._configure_fonts()

        self._build_interface()

        self._load_chats_async()

    # ======================================================================
    # Fonts
    # ======================================================================

    def _configure_fonts(self):

        self.font_normal = (
            FONT,
            10,
        )

        self.font_message = (
            FONT,
            11,
        )

        self.font_small = (
            FONT,
            9,
        )

    # ======================================================================
    # Main interface
    # ======================================================================

    def _build_interface(self):

        self.root.grid_rowconfigure(
            0,
            weight=1,
        )

        self.root.grid_columnconfigure(
            1,
            weight=1,
        )

        self._build_sidebar()

        self._build_main()

    # ======================================================================
    # Sidebar
    # ======================================================================

    def _build_sidebar(self):

        self.sidebar = tk.Frame(
            self.root,
            bg=SIDEBAR,
            width=275,
        )

        self.sidebar.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.sidebar.grid_propagate(False)

        self.sidebar.grid_rowconfigure(
            2,
            weight=1,
        )

        # --------------------------------------------------------------
        # Logo
        # --------------------------------------------------------------

        logo = tk.Frame(
            self.sidebar,
            bg=SIDEBAR,
            height=65,
        )

        logo.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        logo.grid_propagate(False)

        tk.Label(
            logo,
            text="N",
            font=(
                FONT,
                19,
                "bold",
            ),
            fg=TEXT,
            bg=SIDEBAR,
        ).pack(
            side="left",
            padx=(18, 7),
            pady=15,
        )

        tk.Label(
            logo,
            text="Nova",
            font=(
                FONT,
                15,
                "bold",
            ),
            fg=TEXT,
            bg=SIDEBAR,
        ).pack(
            side="left",
            pady=15,
        )

        # --------------------------------------------------------------
        # New Chat
        # --------------------------------------------------------------

        new_chat_frame = tk.Frame(
            self.sidebar,
            bg=SIDEBAR,
        )

        new_chat_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=10,
            pady=(2, 10),
        )

        self.new_chat_button = self._make_button(
            new_chat_frame,
            "＋  New chat",
            self.create_chat,
            bg=SIDEBAR,
            hover=SIDEBAR_HOVER,
            fg=TEXT,
            anchor="w",
            padx=13,
            pady=11,
        )

        self.new_chat_button.pack(
            fill="x",
        )

        # --------------------------------------------------------------
        # Chat canvas
        # --------------------------------------------------------------

        self.chat_canvas = tk.Canvas(
            self.sidebar,
            bg=SIDEBAR,
            highlightthickness=0,
            borderwidth=0,
        )

        self.chat_canvas.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=7,
        )

        self.chat_frame = tk.Frame(
            self.chat_canvas,
            bg=SIDEBAR,
        )

        self.chat_window = (
            self.chat_canvas.create_window(
                0,
                0,
                anchor="nw",
                window=self.chat_frame,
            )
        )

        self.chat_frame.bind(
            "<Configure>",
            lambda event: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")
            ),
        )

        self.chat_canvas.bind(
            "<Configure>",
            self._resize_chat_frame,
        )

        self.chat_canvas.bind(
            "<MouseWheel>",
            self._sidebar_mousewheel,
        )

        # --------------------------------------------------------------
        # Footer
        # --------------------------------------------------------------

        footer = tk.Frame(
            self.sidebar,
            bg=SIDEBAR,
            height=50,
        )

        footer.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=14,
            pady=8,
        )

        footer.grid_propagate(False)

        tk.Label(
            footer,
            text="Local Nova",
            font=(
                FONT,
                9,
            ),
            fg=TEXT_MUTED,
            bg=SIDEBAR,
        ).pack(
            side="left",
        )

    def _resize_chat_frame(
        self,
        event,
    ):

        self.chat_canvas.itemconfigure(
            self.chat_window,
            width=event.width,
        )

    def _sidebar_mousewheel(
        self,
        event,
    ):

        self.chat_canvas.yview_scroll(
            int(-event.delta / 120),
            "units",
        )

    # ======================================================================
    # Main
    # ======================================================================

    def _build_main(self):

        self.main = tk.Frame(
            self.root,
            bg=BG,
        )

        self.main.grid(
            row=0,
            column=1,
            sticky="nsew",
        )

        self.main.grid_rowconfigure(
            1,
            weight=1,
        )

        self.main.grid_columnconfigure(
            0,
            weight=1,
        )

        self._build_topbar()

        self._build_conversation()

        self._build_input()

    # ======================================================================
    # Top bar
    # ======================================================================

    def _build_topbar(self):

        self.topbar = tk.Frame(
            self.main,
            bg=BG,
            height=62,
        )

        self.topbar.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        self.topbar.grid_propagate(False)

        self.chat_title = tk.Label(
            self.topbar,
            text="Nova",
            font=(
                FONT,
                15,
                "bold",
            ),
            fg=TEXT,
            bg=BG,
        )

        self.chat_title.pack(
            side="left",
            padx=24,
            pady=18,
        )

        self.status = tk.Label(
            self.topbar,
            text="",
            font=(
                FONT,
                9,
            ),
            fg=TEXT_MUTED,
            bg=BG,
        )

        self.status.pack(
            side="right",
            padx=24,
        )

    # ======================================================================
    # Conversation
    # ======================================================================

    def _build_conversation(self):

        outer = tk.Frame(
            self.main,
            bg=BG,
        )

        outer.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        outer.grid_rowconfigure(
            0,
            weight=1,
        )

        outer.grid_columnconfigure(
            0,
            weight=1,
        )

        # ==============================================================
        # Canvas
        # ==============================================================

        self.conversation_canvas = tk.Canvas(
            outer,
            bg=BG,
            highlightthickness=0,
            borderwidth=0,
        )

        self.conversation_canvas.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        # ==============================================================
        # Visible scrollbar
        # ==============================================================

        self.conversation_scrollbar = tk.Scrollbar(
            outer,
            orient="vertical",
            command=self.conversation_canvas.yview,
            bg=BG,
            troughcolor=BG,
            activebackground="#444444",
            highlightthickness=0,
            relief="flat",
            width=12,
        )

        self.conversation_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.conversation_canvas.configure(
            yscrollcommand=self.conversation_scrollbar.set,
        )

        # ==============================================================
        # Message frame
        # ==============================================================

        self.message_frame = tk.Frame(
            self.conversation_canvas,
            bg=BG,
        )

        self.message_window = (
            self.conversation_canvas.create_window(
                0,
                0,
                anchor="nw",
                window=self.message_frame,
            )
        )

        # Update scroll region when content changes.
        self.message_frame.bind(
            "<Configure>",
            lambda event: self.conversation_canvas.configure(
                scrollregion=self.conversation_canvas.bbox("all")
            ),
        )

        # Keep content width synced with canvas width.
        self.conversation_canvas.bind(
            "<Configure>",
            self._resize_message_frame,
        )

        # Mouse-wheel scrolling.
        self.conversation_canvas.bind(
            "<MouseWheel>",
            self._conversation_mousewheel,
        )

        self.message_frame.bind(
            "<MouseWheel>",
            self._conversation_mousewheel,
        )

        # Also allow scrolling when the mouse is directly over messages.
        self._bind_mousewheel_recursive(
            self.message_frame
        )

    def _resize_message_frame(
        self,
        event,
    ):

        self.conversation_canvas.itemconfigure(
            self.message_window,
            width=event.width,
        )

    def _conversation_mousewheel(
        self,
        event,
    ):

        self.conversation_canvas.yview_scroll(
            int(-event.delta / 120),
            "units",
        )

        return "break"

    def _bind_mousewheel_recursive(
        self,
        widget,
    ):

        try:

            widget.bind(
                "<MouseWheel>",
                self._conversation_mousewheel,
                add="+",
            )

        except Exception:

            pass

        for child in widget.winfo_children():

            self._bind_mousewheel_recursive(
                child
            )

    # ======================================================================
    # Input area
    # ======================================================================

    def _build_input(self):

        area = tk.Frame(
            self.main,
            bg=BG,
        )

        area.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=24,
            pady=(8, 22),
        )

        area.grid_columnconfigure(
            1,
            weight=1,
        )

        self.input_container = tk.Frame(
            area,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )

        self.input_container.grid(
            row=0,
            column=1,
            sticky="ew",
        )

        self.input_container.grid_columnconfigure(
            1,
            weight=1,
        )

        # --------------------------------------------------------------
        # Plus
        # --------------------------------------------------------------

        self.plus_button = self._make_button(
            self.input_container,
            "+",
            self.show_actions,
            bg=SURFACE,
            hover=SURFACE_HOVER,
            fg=TEXT_SECONDARY,
            font=(
                FONT,
                17,
            ),
            width=3,
            pady=8,
        )

        self.plus_button.grid(
            row=0,
            column=0,
            padx=(8, 2),
            pady=8,
        )

        # --------------------------------------------------------------
        # Text box
        # --------------------------------------------------------------

        self.input_box = tk.Text(
            self.input_container,
            height=3,
            wrap="word",
            font=self.font_message,
            bg=SURFACE,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#333333",
            selectforeground=TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=7,
            pady=9,
        )

        self.input_box.grid(
            row=0,
            column=1,
            sticky="ew",
            pady=7,
        )

        self.input_box.bind(
            "<Return>",
            self._handle_return,
        )

        # --------------------------------------------------------------
        # Think
        # --------------------------------------------------------------

        self.thinking_button = self._make_button(
            self.input_container,
            "Think",
            self.toggle_thinking,
            bg=SURFACE,
            hover=SURFACE_HOVER,
            fg=TEXT_SECONDARY,
            font=(
                FONT,
                9,
            ),
            pady=7,
        )

        self.thinking_button.grid(
            row=0,
            column=2,
            padx=3,
            pady=8,
        )

        # --------------------------------------------------------------
        # Send
        # --------------------------------------------------------------

        self.send_button = self._make_button(
            self.input_container,
            "↑",
            self.send_message,
            bg=WHITE,
            hover="#dddddd",
            fg=BLACK,
            font=(
                FONT,
                16,
                "bold",
            ),
            width=3,
            pady=5,
        )

        self.send_button.grid(
            row=0,
            column=3,
            padx=(3, 8),
            pady=8,
        )

        # --------------------------------------------------------------
        # Disclaimer
        # --------------------------------------------------------------

        tk.Label(
            area,
            text="Nova can make mistakes. Check important information.",
            font=(
                FONT,
                8,
            ),
            fg=TEXT_MUTED,
            bg=BG,
        ).grid(
            row=1,
            column=1,
            pady=(6, 0),
        )

    # ======================================================================
    # Button helper
    # ======================================================================

    def _make_button(
        self,
        parent,
        text,
        command,
        bg=SURFACE,
        hover=SURFACE_HOVER,
        fg=TEXT,
        font=None,
        width=None,
        padx=10,
        pady=7,
        anchor="center",
    ):

        config = {
            "text": text,
            "command": command,
            "bg": bg,
            "fg": fg,
            "activebackground": hover,
            "activeforeground": fg,
            "relief": "flat",
            "borderwidth": 0,
            "highlightthickness": 0,
            "font": font or self.font_normal,
            "padx": padx,
            "pady": pady,
            "anchor": anchor,
            "cursor": "hand2",
        }

        if width is not None:

            config["width"] = width

        button = tk.Button(
            parent,
            **config,
        )

        button.bind(
            "<Enter>",
            lambda event: button.configure(
                bg=hover
            ),
        )

        button.bind(
            "<Leave>",
            lambda event: button.configure(
                bg=bg
            ),
        )

        return button

    # ======================================================================
    # Empty state
    # ======================================================================

    def show_empty_state(self):

        self.displayed_messages = []

        self._clear_messages()

        container = tk.Frame(
            self.message_frame,
            bg=BG,
        )

        container.pack(
            expand=True,
            fill="both",
            pady=150,
        )

        tk.Label(
            container,
            text="N",
            font=(
                FONT,
                38,
                "bold",
            ),
            fg=TEXT,
            bg=BG,
        ).pack()

        tk.Label(
            container,
            text="How can I help?",
            font=(
                FONT,
                24,
            ),
            fg=TEXT,
            bg=BG,
        ).pack(
            pady=(8, 4),
        )

        tk.Label(
            container,
            text="Choose a conversation or start a new one.",
            font=(
                FONT,
                10,
            ),
            fg=TEXT_MUTED,
            bg=BG,
        ).pack()

    # ======================================================================
    # Load chats
    # ======================================================================

    def _load_chats_async(self):

        self.status.config(
            text="Loading..."
        )

        threading.Thread(
            target=self._load_chats_worker,
            daemon=True,
        ).start()

    def _load_chats_worker(self):

        try:

            chats = self.backend.list_chats()

        except Exception as error:

            self.root.after(
                0,
                lambda error=error: self._error(
                    "Could not load chats.",
                    error,
                ),
            )

            return

        self.root.after(
            0,
            lambda chats=chats: self._populate_chats(
                chats
            ),
        )

    def _populate_chats(
        self,
        chats: list[ChatInfo],
    ):

        # IMPORTANT:
        # Only the sidebar is modified here.
        #
        # The conversation is intentionally untouched.
        # This prevents the previous-message disappearing bug.

        for widget in self.chat_frame.winfo_children():

            widget.destroy()

        for chat in chats:

            self._add_chat_button(
                chat
            )

        self.status.config(
            text=""
        )

    def _add_chat_button(
        self,
        chat: ChatInfo,
    ):

        active = (
            self.current_chat == chat.name
        )

        background = (
            SIDEBAR_ACTIVE
            if active
            else SIDEBAR
        )

        foreground = (
            TEXT
            if active
            else TEXT_SECONDARY
        )

        row = tk.Frame(
            self.chat_frame,
            bg=SIDEBAR,
        )

        row.pack(
            fill="x",
            pady=1,
        )

        button = self._make_button(
            row,
            chat.name,
            lambda name=chat.name: self.open_chat(name),
            bg=background,
            hover=SIDEBAR_HOVER,
            fg=foreground,
            font=(
                FONT,
                10,
            ),
            anchor="w",
            padx=13,
            pady=9,
        )

        button.pack(
            side="left",
            fill="x",
            expand=True,
        )

        delete_button = self._make_button(
            row,
            "⋯",
            lambda name=chat.name: self.chat_menu(name),
            bg=background,
            hover=SIDEBAR_HOVER,
            fg=TEXT_MUTED,
            font=(
                FONT,
                12,
            ),
            width=3,
            pady=5,
        )

        delete_button.pack(
            side="right",
        )

    # ======================================================================
    # Create chat
    # ======================================================================

    def create_chat(self):

        name = simpledialog.askstring(
            "New chat",
            "Name this conversation:",
            parent=self.root,
        )

        if name is None:
            return

        name = name.strip()

        if not name:
            return

        if chat_exists(name):

            messagebox.showwarning(
                "Nova",
                f'A chat named "{name}" already exists.',
                parent=self.root,
            )

            return

        try:

            self.backend.create_chat(
                name
            )

        except Exception as error:

            self._error(
                "Could not create chat.",
                error,
            )

            return

        self.current_chat = name

        self.displayed_messages = []

        self.chat_title.config(
            text=name,
        )

        self._clear_messages()

        tk.Label(
            self.message_frame,
            text="Start the conversation.",
            font=(
                FONT,
                11,
            ),
            fg=TEXT_MUTED,
            bg=BG,
        ).pack(
            pady=100,
        )

        self._load_chats_async()

        self.input_box.focus_set()

    # ======================================================================
    # Open chat
    # ======================================================================

    def open_chat(
        self,
        name: str,
    ):

        self.current_chat = name

        self.chat_title.config(
            text=name,
        )

        self.displayed_messages = []

        self._clear_messages()

        self.status.config(
            text="Loading conversation..."
        )

        tk.Label(
            self.message_frame,
            text="Loading conversation...",
            font=(
                FONT,
                10,
            ),
            fg=TEXT_MUTED,
            bg=BG,
        ).pack(
            pady=100,
        )

        threading.Thread(
            target=self._open_chat_worker,
            args=(name,),
            daemon=True,
        ).start()

        # Refresh sidebar to highlight current chat.
        self._load_chats_async()

    def _open_chat_worker(
        self,
        name: str,
    ):

        try:

            chat = self.backend.open_chat(
                name
            )

            if chat is None:

                raise RuntimeError(
                    "Chat could not be opened."
                )

            messages = []

            for message in chat.messages:

                role = str(
                    message.get(
                        "role",
                        "assistant",
                    )
                )

                content = message.get(
                    "content",
                    "",
                )

                if not content:
                    continue

                messages.append(
                    {
                        "role": role,
                        "content": str(content),
                    }
                )

        except Exception as error:

            self.root.after(
                0,
                lambda error=error: self._error(
                    "Could not open chat.",
                    error,
                ),
            )

            return

        self.root.after(
            0,
            lambda messages=messages: self._loaded_chat(
                messages
            ),
        )

    def _loaded_chat(
        self,
        messages: list[dict[str, str]],
    ):

        self.displayed_messages = list(
            messages
        )

        self._render_displayed_messages()

        self.status.config(
            text=""
        )

    # ======================================================================
    # Chat menu
    # ======================================================================

    def chat_menu(
        self,
        name: str,
    ):

        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE_HOVER,
            activeforeground=TEXT,
            borderwidth=0,
        )

        menu.add_command(
            label="Open",
            command=lambda: self.open_chat(name),
        )

        menu.add_command(
            label="Delete",
            command=lambda: self.delete_chat(name),
        )

        try:

            menu.tk_popup(
                self.root.winfo_pointerx(),
                self.root.winfo_pointery(),
            )

        finally:

            menu.grab_release()

    # ======================================================================
    # Delete chat
    # ======================================================================

    def delete_chat(
        self,
        name: str,
    ):

        confirmed = messagebox.askyesno(
            "Delete chat",
            (
                f'Delete "{name}" permanently?\n\n'
                "This will delete the existing Nova conversation."
            ),
            parent=self.root,
        )

        if not confirmed:
            return

        try:

            self.backend.delete_chat(
                name
            )

        except Exception as error:

            self._error(
                "Could not delete chat.",
                error,
            )

            return

        if self.current_chat == name:

            self.current_chat = None

            self.displayed_messages = []

            self.chat_title.config(
                text="Nova",
            )

            self.show_empty_state()

        self._load_chats_async()

    # ======================================================================
    # Thinking
    # ======================================================================

    def toggle_thinking(self):

        self.thinking = not self.thinking

        if self.thinking:

            self.thinking_button.config(
                text="Think ✓",
                fg=TEXT,
            )

        else:

            self.thinking_button.config(
                text="Think",
                fg=TEXT_SECONDARY,
            )

    # ======================================================================
    # Actions
    # ======================================================================

    def show_actions(self):

        messagebox.showinfo(
            "Nova controls",
            (
                "Available controls:\n\n"
                "@think <message>\n"
                "@web <message>\n"
                "@pdf file.pdf [question]"
            ),
            parent=self.root,
        )

    # ======================================================================
    # Input
    # ======================================================================

    def _handle_return(
        self,
        event,
    ):

        # Shift + Enter = newline.
        if event.state & 0x0001:

            return None

        self.send_message()

        return "break"

    # ======================================================================
    # Send message
    # ======================================================================

    def send_message(self):

        if self.generating:
            return

        if self.current_chat is None:

            messagebox.showinfo(
                "Nova",
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

        chat_name = self.current_chat

        thinking = self.thinking

        self.input_box.delete(
            "1.0",
            "end",
        )

        # ==============================================================
        # ADD USER MESSAGE TO DISPLAY
        # ==============================================================

        self.displayed_messages.append(
            {
                "role": "user",
                "content": message,
            }
        )

        self._display_message(
            "user",
            message,
        )

        self._scroll_bottom()

        self._set_generating(
            True
        )

        threading.Thread(
            target=self._send_worker,
            args=(
                chat_name,
                message,
                thinking,
            ),
            daemon=True,
        ).start()

    def _send_worker(
        self,
        chat_name: str,
        message: str,
        thinking: bool,
    ):

        try:

            answer = self.backend.send_message(
                chat_name,
                message,
                thinking,
            )

        except Exception as error:

            self.root.after(
                0,
                lambda error=error: self._error(
                    "Nova could not generate a response.",
                    error,
                ),
            )

            self.root.after(
                0,
                lambda: self._set_generating(
                    False
                ),
            )

            return

        self.root.after(
            0,
            lambda answer=answer: self._receive_answer(
                answer
            ),
        )

    def _receive_answer(
        self,
        answer: str,
    ):

        # ==============================================================
        # APPEND RESPONSE
        # ==============================================================
        #
        # We intentionally do NOT:
        #
        #     self.show_empty_state()
        #     self.open_chat(...)
        #     self._clear_messages()
        #
        # The old conversation remains on screen.
        # ==============================================================

        self.displayed_messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        self._display_message(
            "assistant",
            answer,
        )

        self._set_generating(
            False
        )

        self._scroll_bottom()

        # Sidebar only.
        self._load_chats_async()

    # ======================================================================
    # Render entire current GUI history
    # ======================================================================

    def _render_displayed_messages(self):

        self._clear_messages()

        if not self.displayed_messages:

            tk.Label(
                self.message_frame,
                text="Start the conversation.",
                font=(
                    FONT,
                    11,
                ),
                fg=TEXT_MUTED,
                bg=BG,
            ).pack(
                pady=100,
            )

            return

        for message in self.displayed_messages:

            self._display_message(
                message.get(
                    "role",
                    "assistant",
                ),
                message.get(
                    "content",
                    "",
                ),
            )

        self._scroll_bottom()

    # ======================================================================
    # Message display
    # ======================================================================

    def _display_message(
        self,
        role: str,
        content: str,
    ):

        is_user = role.lower() in {
            "user",
            "human",
        }

        row = tk.Frame(
            self.message_frame,
            bg=BG,
        )

        row.pack(
            fill="x",
            padx=70,
            pady=15,
        )

        row.grid_columnconfigure(
            1,
            weight=1,
        )

        # --------------------------------------------------------------
        # Avatar
        # --------------------------------------------------------------

        avatar_bg = (
            WHITE
            if is_user
            else SURFACE_2
        )

        avatar_fg = (
            BLACK
            if is_user
            else TEXT
        )

        avatar = tk.Frame(
            row,
            width=32,
            height=32,
            bg=avatar_bg,
        )

        avatar.grid(
            row=0,
            column=0,
            sticky="n",
            padx=(0, 15),
        )

        avatar.grid_propagate(False)

        tk.Label(
            avatar,
            text="Y" if is_user else "N",
            font=(
                FONT,
                10,
                "bold",
            ),
            fg=avatar_fg,
            bg=avatar_bg,
        ).place(
            relx=0.5,
            rely=0.5,
            anchor="center",
        )

        # --------------------------------------------------------------
        # Content
        # --------------------------------------------------------------

        content_frame = tk.Frame(
            row,
            bg=BG,
        )

        content_frame.grid(
            row=0,
            column=1,
            sticky="ew",
        )

        tk.Label(
            content_frame,
            text="You" if is_user else "Nova",
            font=(
                FONT,
                10,
                "bold",
            ),
            fg=TEXT,
            bg=BG,
            anchor="w",
        ).pack(
            fill="x",
            pady=(0, 5),
        )

        # --------------------------------------------------------------
        # Message text
        # --------------------------------------------------------------

        text = tk.Text(
            content_frame,
            wrap="word",
            font=self.font_message,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#333333",
            selectforeground=TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )

        text.insert(
            "1.0",
            content,
        )

        text.configure(
            state="disabled",
        )

        line_count = max(
            1,
            content.count("\n") + 1,
        )

        text.configure(
            height=min(
                30,
                line_count,
            ),
        )

        text.pack(
            fill="x",
        )

        # Bind mouse-wheel directly to this message widget too.
        text.bind(
            "<MouseWheel>",
            self._conversation_mousewheel,
        )

    # ======================================================================
    # Clear message widgets
    # ======================================================================

    def _clear_messages(self):

        for widget in self.message_frame.winfo_children():

            widget.destroy()

    # ======================================================================
    # Generating state
    # ======================================================================

    def _set_generating(
        self,
        generating: bool,
    ):

        self.generating = generating

        if generating:

            self.status.config(
                text="Nova is thinking..."
            )

            self.send_button.config(
                state="disabled",
                bg="#444444",
                fg="#111111",
            )

        else:

            self.status.config(
                text=""
            )

            self.send_button.config(
                state="normal",
                bg=WHITE,
                fg=BLACK,
            )

    # ======================================================================
    # Scroll
    # ======================================================================

    def _scroll_bottom(self):

        self.root.after(
            50,
            lambda: self.conversation_canvas.yview_moveto(
                1.0
            ),
        )

    # ======================================================================
    # Error
    # ======================================================================

    def _error(
        self,
        message: str,
        error: Exception,
    ):

        print(
            f"[Nova GUI] {message}: {error}",
            flush=True,
        )

        messagebox.showerror(
            "Nova",
            f"{message}\n\n{error}",
            parent=self.root,
        )

    # ======================================================================
    # Run
    # ======================================================================

    def run(self):

        self.root.mainloop()


# ============================================================================
# NOVA PLUGIN
# ============================================================================

class GUIPlugin(NovaPlugin):

    name = "gui"
    version = "1.0.0"
    description = "Black and white graphical interface for Nova."
    plugin_api_version = 1

    def register(
        self,
        nova_runtime,
    ):

        nova_runtime.register_cli_command(
            name="ui",
            callback=self.launch,
            help_text="Launch the Nova graphical interface.",
            action="store_true",
        )

    def launch(
        self,
        args,
        runtime,
    ):

        del args
        del runtime

        app = NovaGUI()

        app.run()


# ============================================================================
# REQUIRED NOVA PLUGIN EXPORT
# ============================================================================

plugin = GUIPlugin()
