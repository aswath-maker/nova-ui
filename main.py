"""
Nova GUI Plugin
===============

Single-file desktop GUI for Novatrix.

Launch:
    nova --ui

The GUI is another frontend to the existing Nova system.

It uses:
    - novatrix.chats
    - novatrix.nova
    - novatrix.web
    - novatrix.pdf
    - the existing Nova persistent storage

It does NOT create:
    - another model
    - another chat database
    - another memory system
    - another PDF implementation
    - another web implementation
"""

from __future__ import annotations

import re
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
SIDEBAR_BG = "#0b0b0b"
SIDEBAR_HOVER = "#171717"
SIDEBAR_ACTIVE = "#1d1d1d"

SURFACE = "#121212"
SURFACE_HOVER = "#1a1a1a"

BORDER = "#2a2a2a"

TEXT = "#f4f4f4"
TEXT_SECONDARY = "#b6b6b6"
TEXT_MUTED = "#737373"

WHITE = "#ffffff"
BLACK = "#000000"

FONT = "Segoe UI"

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820


# ============================================================================
# CHAT INFORMATION
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
    Backend adapter for the real Novatrix 0.1.0 APIs.

    The GUI never writes chat JSON itself.
    """

    SUMMARY_INTERVAL = 10

    # ----------------------------------------------------------------------
    # Chat listing
    # ----------------------------------------------------------------------

    def list_chats(self) -> list[ChatInfo]:

        result = list_chats()

        chats = []

        for item in result:

            chats.append(
                ChatInfo(
                    name=str(
                        item.get(
                            "name",
                            "Unnamed Chat",
                        )
                    ),
                    messages=int(
                        item.get(
                            "messages",
                            0,
                        )
                    ),
                )
            )

        return chats

    # ----------------------------------------------------------------------
    # Create
    # ----------------------------------------------------------------------

    def create_chat(
        self,
        name: str,
    ):

        return create_chat(
            name,
            summary_interval=self.SUMMARY_INTERVAL,
        )

    # ----------------------------------------------------------------------
    # Open
    # ----------------------------------------------------------------------

    def open_chat(
        self,
        name: str,
    ):

        return open_chat(name)

    # ----------------------------------------------------------------------
    # Delete
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

        # The GUI already performed confirmation.
        chat.delete()

    # ----------------------------------------------------------------------
    # Send message
    # ----------------------------------------------------------------------

    def send_message(
        self,
        chat_name: str,
        message: str,
        thinking: bool,
    ) -> str:

        chat = open_chat(chat_name)

        if chat is None:

            raise RuntimeError(
                f'Could not open chat "{chat_name}".'
            )

        # ==============================================================
        # PDF
        # ==============================================================

        pdf_request = parse_pdf_control(
            message
        )

        if pdf_request:

            path = pdf_request.get(
                "path"
            )

            if not path:

                return (
                    "Usage: `@pdf file.pdf [question]`"
                )

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
                path,
                question=question,
                thinking=use_thinking,
            )

            try:

                answer = read_pdf(
                    path,
                    prompt=question,
                    think=use_thinking,
                )

            except Exception as error:

                answer = (
                    f"Error reading PDF: {error}"
                )

            chat.add_pdf_response(
                answer,
                path,
                thinking=use_thinking,
            )

            self._maybe_summarize(
                chat
            )

            return answer

        # ==============================================================
        # WEB
        # ==============================================================

        cleaned_message, web_requested, parsed_thinking = (
            parse_chat_controls(message)
        )

        if web_requested:

            use_thinking = bool(
                parsed_thinking
            )

            result = search_with_sources(
                cleaned_message,
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

            chat.add_web_search_action(
                cleaned_message,
                sources=sources,
                thinking=use_thinking,
            )

            chat.add_web_search_response(
                answer,
                query=cleaned_message,
                sources=sources,
                thinking=use_thinking,
            )

            # Keep sources visible in the final GUI answer.
            if sources:

                source_lines = []

                for source in sources:

                    url = source.get(
                        "url",
                        "",
                    )

                    if url:

                        source_lines.append(
                            f"- {url}"
                        )

                if source_lines:

                    answer += (
                        "\n\nSources:\n"
                        +
                        "\n".join(
                            source_lines
                        )
                    )

            self._maybe_summarize(
                chat
            )

            return answer

        # ==============================================================
        # EXPLICIT @think
        # ==============================================================

        if cleaned_message.strip().startswith(
            "@think "
        ):

            thinking = True

            cleaned_message = (
                cleaned_message[7:]
                .strip()
            )

        # ==============================================================
        # NORMAL CHAT
        # ==============================================================

        if thinking:

            user_content = (
                "/think\n"
                +
                cleaned_message
            )

        else:

            user_content = (
                "/no_think\n"
                +
                cleaned_message
            )

        # Persist the user message using Nova's actual Chat class.
        chat.add_user_message(
            user_content,
            action="local",
            web_searched=False,
            thinking=thinking,
        )

        # Build context using Nova's own rolling-memory implementation.
        context = chat.get_context_for_model()

        # Use Nova's existing model instance.
        response = nova.create_chat_completion(
            messages=context,
            max_tokens=500,
        )

        try:

            answer = (
                response[
                    "choices"
                ][0][
                    "message"
                ][
                    "content"
                ]
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as error:

            raise RuntimeError(
                "Nova returned an unexpected response format."
            ) from error

        # Persist assistant response.
        chat.add_assistant_message(
            answer,
            thinking=thinking,
        )

        self._maybe_summarize(
            chat
        )

        return str(
            answer
        )

    # ----------------------------------------------------------------------
    # Memory summary
    # ----------------------------------------------------------------------

    @staticmethod
    def _maybe_summarize(
        chat,
    ):

        try:

            if chat.should_summarize():

                chat.create_summary()

        except Exception as error:

            print(
                f"[Nova GUI] Memory summary failed: {error}",
                flush=True,
            )


# ============================================================================
# GUI
# ============================================================================

class NovaGUI:

    def __init__(self):

        self.backend = NovaBackend()

        self.current_chat: str | None = None

        self.thinking = False

        self.generating = False

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
            bg=BG
        )

        self._build_interface()

        # Load persistent chats after the window has been created.
        self.root.after(
            100,
            self.load_sidebar,
        )

    # ======================================================================
    # MAIN LAYOUT
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
    # SIDEBAR
    # ======================================================================

    def _build_sidebar(self):

        self.sidebar = tk.Frame(
            self.root,
            bg=SIDEBAR_BG,
            width=280,
        )

        self.sidebar.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.sidebar.grid_propagate(
            False
        )

        self.sidebar.grid_rowconfigure(
            2,
            weight=1,
        )

        # --------------------------------------------------------------
        # Logo
        # --------------------------------------------------------------

        logo_frame = tk.Frame(
            self.sidebar,
            bg=SIDEBAR_BG,
            height=70,
        )

        logo_frame.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        logo_frame.grid_propagate(
            False
        )

        tk.Label(
            logo_frame,
            text="N",
            font=(
                FONT,
                20,
                "bold",
            ),
            fg=TEXT,
            bg=SIDEBAR_BG,
        ).pack(
            side="left",
            padx=(20, 8),
            pady=17,
        )

        tk.Label(
            logo_frame,
            text="Nova",
            font=(
                FONT,
                16,
                "bold",
            ),
            fg=TEXT,
            bg=SIDEBAR_BG,
        ).pack(
            side="left",
            pady=17,
        )

        # --------------------------------------------------------------
        # New chat
        # --------------------------------------------------------------

        new_frame = tk.Frame(
            self.sidebar,
            bg=SIDEBAR_BG,
        )

        new_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=10,
            pady=(2, 10),
        )

        self.new_button = self._button(
            new_frame,
            "＋  New chat",
            self.create_new_chat,
            bg=SIDEBAR_BG,
            hover=SIDEBAR_HOVER,
            fg=TEXT,
            font=(
                FONT,
                10,
            ),
            anchor="w",
            padx=14,
            pady=11,
        )

        self.new_button.pack(
            fill="x",
        )

        # --------------------------------------------------------------
        # Sidebar chat list
        # --------------------------------------------------------------

        list_outer = tk.Frame(
            self.sidebar,
            bg=SIDEBAR_BG,
        )

        list_outer.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=7,
        )

        list_outer.grid_rowconfigure(
            0,
            weight=1,
        )

        list_outer.grid_columnconfigure(
            0,
            weight=1,
        )

        self.chat_canvas = tk.Canvas(
            list_outer,
            bg=SIDEBAR_BG,
            highlightthickness=0,
            borderwidth=0,
        )

        self.chat_canvas.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.chat_scrollbar = tk.Scrollbar(
            list_outer,
            orient="vertical",
            command=self.chat_canvas.yview,
            bg=SIDEBAR_BG,
            troughcolor=SIDEBAR_BG,
            activebackground="#444444",
            width=10,
            relief="flat",
            highlightthickness=0,
        )

        self.chat_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.chat_canvas.configure(
            yscrollcommand=self.chat_scrollbar.set,
        )

        self.chat_list_frame = tk.Frame(
            self.chat_canvas,
            bg=SIDEBAR_BG,
        )

        self.chat_window = (
            self.chat_canvas.create_window(
                0,
                0,
                anchor="nw",
                window=self.chat_list_frame,
            )
        )

        self.chat_list_frame.bind(
            "<Configure>",
            lambda event: self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox(
                    "all"
                )
            ),
        )

        self.chat_canvas.bind(
            "<Configure>",
            self._resize_chat_list,
        )

        self.chat_canvas.bind(
            "<MouseWheel>",
            self._sidebar_wheel,
        )

        # --------------------------------------------------------------
        # Footer
        # --------------------------------------------------------------

        footer = tk.Frame(
            self.sidebar,
            bg=SIDEBAR_BG,
            height=50,
        )

        footer.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=15,
            pady=7,
        )

        footer.grid_propagate(
            False
        )

        tk.Label(
            footer,
            text="Local Nova",
            font=(
                FONT,
                9,
            ),
            fg=TEXT_MUTED,
            bg=SIDEBAR_BG,
        ).pack(
            side="left",
        )

    def _resize_chat_list(
        self,
        event,
    ):

        self.chat_canvas.itemconfigure(
            self.chat_window,
            width=event.width,
        )

    def _sidebar_wheel(
        self,
        event,
    ):

        self.chat_canvas.yview_scroll(
            int(
                -event.delta / 120
            ),
            "units",
        )

        return "break"

    # ======================================================================
    # MAIN AREA
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
    # TOP BAR
    # ======================================================================

    def _build_topbar(self):

        self.topbar = tk.Frame(
            self.main,
            bg=BG,
            height=64,
        )

        self.topbar.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        self.topbar.grid_propagate(
            False
        )

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
            anchor="w",
        )

        self.chat_title.pack(
            side="left",
            padx=25,
            pady=19,
        )

        self.status_label = tk.Label(
            self.topbar,
            text="",
            font=(
                FONT,
                9,
            ),
            fg=TEXT_MUTED,
            bg=BG,
        )

        self.status_label.pack(
            side="right",
            padx=25,
        )

    # ======================================================================
    # CONVERSATION AREA
    # ======================================================================

    def _build_conversation(self):

        conversation_outer = tk.Frame(
            self.main,
            bg=BG,
        )

        conversation_outer.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        conversation_outer.grid_rowconfigure(
            0,
            weight=1,
        )

        conversation_outer.grid_columnconfigure(
            0,
            weight=1,
        )

        # ==============================================================
        # THIS IS THE IMPORTANT CHANGE
        #
        # One dedicated Text widget handles the entire conversation.
        #
        # Tkinter's Text widget already has robust scrolling behavior.
        # There is no nested Canvas/Frame message architecture to fight.
        # ==============================================================

        self.conversation = tk.Text(
            conversation_outer,
            bg=BG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#333333",
            selectforeground=TEXT,
            wrap="word",
            font=(
                FONT,
                11,
            ),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=70,
            pady=20,
            spacing1=2,
            spacing2=3,
            spacing3=8,
        )

        self.conversation.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        # --------------------------------------------------------------
        # Vertical scrollbar
        # --------------------------------------------------------------

        self.conversation_scrollbar = tk.Scrollbar(
            conversation_outer,
            orient="vertical",
            command=self.conversation.yview,
            bg=BG,
            troughcolor=BG,
            activebackground="#555555",
            width=12,
            relief="flat",
            highlightthickness=0,
        )

        self.conversation_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.conversation.configure(
            yscrollcommand=self.conversation_scrollbar.set,
        )

        # Read-only conversation surface.
        self.conversation.configure(
            state="disabled"
        )

        self.conversation.bind(
            "<MouseWheel>",
            self._conversation_wheel,
        )

        self.conversation.bind(
            "<Button-4>",
            lambda event: self.conversation.yview_scroll(
                -3,
                "units",
            ),
        )

        self.conversation.bind(
            "<Button-5>",
            lambda event: self.conversation.yview_scroll(
                3,
                "units",
            ),
        )

        # --------------------------------------------------------------
        # Message tags
        # --------------------------------------------------------------

        self.conversation.tag_configure(
            "you_name",
            foreground=TEXT,
            font=(
                FONT,
                10,
                "bold",
            ),
            spacing1=12,
            spacing3=3,
        )

        self.conversation.tag_configure(
            "nova_name",
            foreground=TEXT,
            font=(
                FONT,
                10,
                "bold",
            ),
            spacing1=18,
            spacing3=3,
        )

        self.conversation.tag_configure(
            "you_message",
            foreground=TEXT,
            font=(
                FONT,
                11,
            ),
            lmargin1=0,
            lmargin2=0,
            spacing3=9,
        )

        self.conversation.tag_configure(
            "nova_message",
            foreground=TEXT,
            font=(
                FONT,
                11,
            ),
            lmargin1=0,
            lmargin2=0,
            spacing3=18,
        )

        self.conversation.tag_configure(
            "system",
            foreground=TEXT_MUTED,
            font=(
                FONT,
                9,
            ),
        )

    # ======================================================================
    # INPUT
    # ======================================================================

    def _build_input(self):

        outer = tk.Frame(
            self.main,
            bg=BG,
        )

        outer.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=24,
            pady=(8, 22),
        )

        outer.grid_columnconfigure(
            1,
            weight=1,
        )

        # --------------------------------------------------------------
        # Input container
        # --------------------------------------------------------------

        self.input_container = tk.Frame(
            outer,
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

        self.plus_button = self._button(
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
            padx=(8, 3),
            pady=8,
        )

        # --------------------------------------------------------------
        # Input text
        # --------------------------------------------------------------

        self.input_box = tk.Text(
            self.input_container,
            height=3,
            wrap="word",
            bg=SURFACE,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground="#333333",
            selectforeground=TEXT,
            font=(
                FONT,
                11,
            ),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=8,
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
        # Thinking toggle
        # --------------------------------------------------------------

        self.thinking_button = self._button(
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

        self.send_button = self._button(
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
            outer,
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
    # BUTTON HELPER
    # ======================================================================

    def _button(
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
            "font": font or (
                FONT,
                10,
            ),
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
    # LOAD SIDEBAR
    # ======================================================================

    def load_sidebar(self):

        threading.Thread(
            target=self._load_sidebar_worker,
            daemon=True,
        ).start()

    def _load_sidebar_worker(self):

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
            lambda chats=chats: self._render_sidebar(
                chats
            ),
        )

    def _render_sidebar(
        self,
        chats: list[ChatInfo],
    ):

        # IMPORTANT:
        # Nothing in this function touches the conversation.
        #
        # Sidebar refresh therefore cannot erase conversation messages.

        for widget in self.chat_list_frame.winfo_children():

            widget.destroy()

        for chat in chats:

            self._add_chat_item(
                chat
            )

    def _add_chat_item(
        self,
        chat: ChatInfo,
    ):

        active = (
            self.current_chat == chat.name
        )

        background = (
            SIDEBAR_ACTIVE
            if active
            else SIDEBAR_BG
        )

        foreground = (
            TEXT
            if active
            else TEXT_SECONDARY
        )

        row = tk.Frame(
            self.chat_list_frame,
            bg=SIDEBAR_BG,
        )

        row.pack(
            fill="x",
            pady=1,
        )

        chat_button = self._button(
            row,
            chat.name,
            lambda name=chat.name: self.open_chat(
                name
            ),
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

        chat_button.pack(
            side="left",
            fill="x",
            expand=True,
        )

        menu_button = self._button(
            row,
            "⋯",
            lambda name=chat.name: self.chat_menu(
                name
            ),
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

        menu_button.pack(
            side="right",
        )

    # ======================================================================
    # CREATE CHAT
    # ======================================================================

    def create_new_chat(self):

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

        self.chat_title.config(
            text=name
        )

        self._clear_conversation()

        self._show_conversation_placeholder(
            "Start the conversation."
        )

        self.load_sidebar()

        self.input_box.focus_set()

    # ======================================================================
    # OPEN CHAT
    # ======================================================================

    def open_chat(
        self,
        name: str,
    ):

        self.current_chat = name

        self.chat_title.config(
            text=name
        )

        self.status_label.config(
            text="Loading conversation..."
        )

        self._clear_conversation()

        self._show_conversation_placeholder(
            "Loading conversation..."
        )

        # Refreshing sidebar is safe because it NEVER touches conversation.
        self.load_sidebar()

        threading.Thread(
            target=self._open_chat_worker,
            args=(name,),
            daemon=True,
        ).start()

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

            # Copy the actual Nova persistent history.
            history = []

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

                if content is None:
                    continue

                content = str(
                    content
                )

                if not content.strip():
                    continue

                history.append(
                    {
                        "role": role,
                        "content": content,
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
            lambda history=history, name=name:
                self._finish_open_chat(
                    name,
                    history,
                ),
        )

    def _finish_open_chat(
        self,
        name: str,
        history: list[dict[str, str]],
    ):

        # Ignore a late worker result if the user switched chats already.
        if self.current_chat != name:

            return

        self._render_history(
            history
        )

        self.status_label.config(
            text=""
        )

    # ======================================================================
    # DELETE CHAT
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

            self.chat_title.config(
                text="Nova"
            )

            self._clear_conversation()

            self._show_empty_state()

        self.load_sidebar()

    # ======================================================================
    # THINKING
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
    # ACTIONS
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
    # INPUT
    # ======================================================================

    def _handle_return(
        self,
        event,
    ):

        # Shift+Enter = newline.
        if event.state & 0x0001:

            return None

        self.send_message()

        return "break"

    # ======================================================================
    # SEND
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

        # Clear input immediately.
        self.input_box.delete(
            "1.0",
            "end",
        )

        # Add to display immediately so the UI feels responsive.
        self._append_display_message(
            "user",
            message,
        )

        self._scroll_to_bottom()

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

            self.backend.send_message(
                chat_name,
                message,
                thinking,
            )

            # IMPORTANT:
            #
            # We do not trust the GUI's temporary display as persistent
            # truth. Once Nova has saved the response, reload the entire
            # conversation from Nova's actual Chat object.
            #
            # This guarantees that the UI reflects the real stored history.

            chat = self.backend.open_chat(
                chat_name
            )

            if chat is None:

                raise RuntimeError(
                    "The chat disappeared after generation."
                )

            history = []

            for stored_message in chat.messages:

                role = str(
                    stored_message.get(
                        "role",
                        "assistant",
                    )
                )

                content = stored_message.get(
                    "content",
                    "",
                )

                if content is None:
                    continue

                content = str(
                    content
                )

                if not content.strip():
                    continue

                history.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

        except Exception as error:

            self.root.after(
                0,
                lambda error=error: self._generation_failed(
                    error
                ),
            )

            return

        self.root.after(
            0,
            lambda history=history, chat_name=chat_name:
                self._generation_finished(
                    chat_name,
                    history,
                ),
        )

    def _generation_finished(
        self,
        chat_name: str,
        history: list[dict[str, str]],
    ):

        if self.current_chat != chat_name:

            return

        # Replace the display with the COMPLETE persisted conversation.
        self._render_history(
            history
        )

        self._set_generating(
            False
        )

        # Sidebar refresh only.
        self.load_sidebar()

        self._scroll_to_bottom()

    def _generation_failed(
        self,
        error: Exception,
    ):

        self._set_generating(
            False
        )

        self._error(
            "Nova could not generate a response.",
            error,
        )

    # ======================================================================
    # DISPLAY HISTORY
    # ======================================================================

    def _render_history(
        self,
        history: list[dict[str, str]],
    ):

        self._clear_conversation()

        if not history:

            self._show_conversation_placeholder(
                "Start the conversation."
            )

            return

        for item in history:

            role = item.get(
                "role",
                "assistant",
            )

            content = item.get(
                "content",
                "",
            )

            self._append_display_message(
                role,
                content,
            )

        self._scroll_to_bottom()

    def _append_display_message(
        self,
        role: str,
        content: str,
    ):

        visible_content = (
            self._clean_display_content(
                content
            )
        )

        if not visible_content.strip():

            return

        is_user = (
            role.lower()
            in {
                "user",
                "human",
            }
        )

        name = (
            "You"
            if is_user
            else "Nova"
        )

        name_tag = (
            "you_name"
            if is_user
            else "nova_name"
        )

        message_tag = (
            "you_message"
            if is_user
            else "nova_message"
        )

        self.conversation.configure(
            state="normal"
        )

        # Name
        self.conversation.insert(
            "end",
            name
            +
            "\n",
            name_tag,
        )

        # Message
        self.conversation.insert(
            "end",
            visible_content.strip()
            +
            "\n\n",
            message_tag,
        )

        self.conversation.configure(
            state="disabled"
        )

    # ======================================================================
    # CLEAN DISPLAY TEXT
    # ======================================================================

    @staticmethod
    def _clean_display_content(
        content: str,
    ) -> str:

        text = str(
            content
        )

        # Remove internal thinking directives from visible UI.
        text = re.sub(
            r"^\s*/no_think\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"^\s*/think\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # Remove <think>...</think> blocks from the GUI display.
        #
        # The underlying persistent response is left untouched.
        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        return text.strip()

    # ======================================================================
    # CLEAR CONVERSATION
    # ======================================================================

    def _clear_conversation(self):

        self.conversation.configure(
            state="normal"
        )

        self.conversation.delete(
            "1.0",
            "end",
        )

        self.conversation.configure(
            state="disabled"
        )

    def _show_conversation_placeholder(
        self,
        text: str,
    ):

        self.conversation.configure(
            state="normal"
        )

        self.conversation.insert(
            "end",
            text,
            "system",
        )

        self.conversation.configure(
            state="disabled"
        )

    def _show_empty_state(self):

        self._clear_conversation()

        self.conversation.configure(
            state="normal"
        )

        self.conversation.insert(
            "end",
            "\n\n",
            "system",
        )

        self.conversation.insert(
            "end",
            "N\n",
            "nova_name",
        )

        self.conversation.insert(
            "end",
            "How can I help?\n\n",
            "nova_message",
        )

        self.conversation.insert(
            "end",
            "Choose a conversation or start a new one.",
            "system",
        )

        self.conversation.configure(
            state="disabled"
        )

    # ======================================================================
    # SCROLLING
    # ======================================================================

    def _conversation_wheel(
        self,
        event,
    ):

        self.conversation.yview_scroll(
            int(
                -event.delta / 120
            ),
            "units",
        )

        return "break"

    def _scroll_to_bottom(self):

        self.root.after(
            50,
            lambda: self.conversation.yview_moveto(
                1.0
            ),
        )

    # ======================================================================
    # GENERATION STATE
    # ======================================================================

    def _set_generating(
        self,
        generating: bool,
    ):

        self.generating = generating

        if generating:

            self.status_label.config(
                text="Nova is thinking..."
            )

            self.send_button.config(
                state="disabled",
                bg="#444444",
                fg="#111111",
            )

        else:

            self.status_label.config(
                text=""
            )

            self.send_button.config(
                state="normal",
                bg=WHITE,
                fg=BLACK,
            )

    # ======================================================================
    # ERROR
    # ======================================================================

    def _error(
        self,
        message: str,
        error: Exception,
    ):

        print(
            f"[Nova GUI] {message}",
            flush=True,
        )

        print(
            f"[Nova GUI] {type(error).__name__}: {error}",
            flush=True,
        )

        messagebox.showerror(
            "Nova",
            f"{message}\n\n{error}",
            parent=self.root,
        )

    # ======================================================================
    # RUN
    # ======================================================================

    def run(self):

        self.root.mainloop()


# ============================================================================
# NOVA PLUGIN
# ============================================================================

class GUIPlugin(NovaPlugin):

    name = "gui"
    version = "1.0.0"
    description = "Monochrome desktop graphical interface for Nova."
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
# REQUIRED PLUGIN EXPORT
# ============================================================================

plugin = GUIPlugin()
