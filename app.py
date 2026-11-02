"""Local Windows desktop draft. No bundled datasets or precomputed findings."""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import engine
import workflow
import comparison
import investigation
import chart
import mapping_checks
from record_search import match_spans
from import_errors import ImportFailure
from comparison_view import ComparisonView
from evidence_labels import time_label, source_label

BG, WHITE, INK, MUTED, LINE, ACCENT = (
    "#0a0c10",
    "#101923",
    "#e0f7ff",
    "#9aafc4",
    "#24535e",
    "#00f3ff",
)
RAIL, SELECTED, AMBER, RED = "#050505", "#07343e", "#ff6b00", "#ff0055"
NONE = "Not mapped"
UI_STATE = Path(__file__).with_name(".surge-ui.json")


class Workbench(tk.Tk):
    def __init__(self, *, start_hidden=False):
        super().__init__()
        # Regression checks can construct the legacy UI without briefly mapping
        # a second window. Layout checks explicitly deiconify when needed.
        if start_hidden:
            self.withdraw()
        self.title("Surge — Legacy Workbench")
        self.geometry("1360x880")
        self.minsize(1100, 760)
        self.configure(bg=BG)
        self.current = self.reference = self.result = self.run_config = None
        self.previous = None
        self.compare_records = False
        self.rules = []
        self.context = {}
        self.reference_by = []
        self.busy = False
        self.generation = 0
        self._mapping_key = None
        self.mapping_report = None
        self._preview_note = None
        self._preview_page = 0
        self.messages = queue.Queue()
        self.status = tk.StringVar(value="Import data or open a case.")
        self.session = tk.StringVar(value=NONE)
        self.event_id = tk.StringVar(value=NONE)
        self.time = tk.StringVar(value=NONE)
        self.time_format = tk.StringVar(value="milliseconds")
        self.time_origin = tk.StringVar(value="unspecified")
        self.threshold = tk.StringVar(value="6")
        self.only_leads = tk.BooleanVar(value=True)
        self.minimum_priority = tk.StringVar(value="All")
        self.differences_only = tk.BooleanVar(value=False)
        self.show_values = tk.BooleanVar(value=False)
        self.show_details = tk.BooleanVar(value=False)
        self.search = tk.StringVar()
        self._search_timer = None
        self._search_result = None
        self._search_index = {}
        self._chart_points = []
        self._chart_reveal = None
        self._split_ratio = 0.5
        try:
            if UI_STATE.stat().st_size <= 4096:
                ratio = json.loads(UI_STATE.read_text(encoding="utf-8")).get("split", 0.5)
                if (
                    isinstance(ratio, (int, float))
                    and not isinstance(ratio, bool)
                    and 0.3 <= ratio <= 0.7
                ):
                    self._split_ratio = ratio
        except (OSError, ValueError, AttributeError):
            pass
        self._style()
        self._layout()
        for variable in (
            self.session,
            self.event_id,
            self.time,
            self.time_format,
            self.time_origin,
            self.threshold,
        ):
            variable.trace_add("write", self._changed)
        self.search.trace_add("write", self._search_changed)
        self.bind("<Control-f>", self._focus_search)
        self.after(60, self._poll)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*Font", ("Consolas", 10))
        style.configure(".", font=("Consolas", 10), background=BG, foreground=INK)
        style.configure(
            "TButton",
            padding=(10, 7),
            background=WHITE,
            bordercolor=LINE,
            lightcolor=WHITE,
            darkcolor=WHITE,
            borderwidth=1,
            focusthickness=1,
            focuscolor=ACCENT,
        )
        style.map(
            "TButton",
            background=[("disabled", "#0e1219"), ("pressed", "#171039"), ("active", "#10333e")],
            foreground=[("disabled", "#718496"), ("active", ACCENT)],
            bordercolor=[
                ("disabled", "#25303c"),
                ("pressed", "#3a00ff"),
                ("focus", ACCENT),
                ("active", ACCENT),
            ],
            lightcolor=[("active", "#24535e")],
            darkcolor=[("active", "#142e38")],
        )
        style.configure(
            "Rail.TButton", background=RAIL, borderwidth=0, anchor="w", padding=(14, 10)
        )
        style.map(
            "Rail.TButton", background=[("active", "#10232f")], foreground=[("active", ACCENT)]
        )
        style.configure(
            "Active.Rail.TButton",
            background=SELECTED,
            foreground=ACCENT,
            borderwidth=1,
            bordercolor=ACCENT,
            lightcolor=SELECTED,
            darkcolor=SELECTED,
        )
        style.map("Active.Rail.TButton", background=[("active", SELECTED)])
        style.configure("Accent.TButton", background=ACCENT, foreground=RAIL, borderwidth=0)
        style.map(
            "Accent.TButton",
            background=[("disabled", "#18313b"), ("pressed", "#00b8c4"), ("active", "#73faff")],
            foreground=[("disabled", "#8aabb8"), ("!disabled", RAIL)],
        )
        style.configure(
            "TEntry",
            fieldbackground=RAIL,
            foreground=INK,
            insertcolor=INK,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            padding=6,
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", ACCENT)],
            lightcolor=[("focus", ACCENT)],
            darkcolor=[("focus", "#163d48")],
        )
        style.configure(
            "TCombobox",
            fieldbackground=RAIL,
            background=WHITE,
            foreground=INK,
            arrowcolor=ACCENT,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            padding=5,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", RAIL)],
            foreground=[("readonly", INK)],
            selectbackground=[("readonly", RAIL)],
            selectforeground=[("readonly", INK)],
            bordercolor=[("focus", ACCENT), ("active", ACCENT)],
            arrowcolor=[("active", "#00ff66")],
        )
        self.option_add("*TCombobox*Listbox.background", WHITE)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", SELECTED)
        self.option_add("*TCombobox*Listbox.selectForeground", INK)
        style.configure("TCheckbutton", background=BG, foreground=MUTED, focuscolor=ACCENT)
        style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", INK)])
        style.configure(
            "Treeview",
            background=WHITE,
            fieldbackground=WHITE,
            foreground=INK,
            rowheight=34,
            borderwidth=0,
            font=("Consolas", 10),
        )
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Treeview.Heading",
            background=RAIL,
            foreground=ACCENT,
            padding=(4, 9),
            relief="flat",
            font=("Consolas", 9),
        )
        style.layout(
            "Treeview.Heading",
            [
                ("Treeheading.cell", {"sticky": "nswe"}),
                (
                    "Treeheading.padding",
                    {"sticky": "nswe", "children": [("Treeheading.text", {"sticky": "we"})]},
                ),
            ],
        )
        style.map("Treeview.Heading", background=[("active", SELECTED)])
        style.map("Treeview", background=[("selected", SELECTED)], foreground=[("selected", INK)])
        style.configure(
            "TScrollbar",
            background=LINE,
            troughcolor=BG,
            arrowcolor=MUTED,
            bordercolor=BG,
            lightcolor=BG,
            darkcolor=BG,
            arrowsize=12,
        )
        style.map(
            "TScrollbar", background=[("pressed", "#00ff66"), ("active", ACCENT), ("!active", LINE)]
        )
        for orientation in ("Vertical", "Horizontal"):
            style.layout(
                f"{orientation}.TScrollbar",
                [
                    (
                        f"{orientation}.Scrollbar.trough",
                        {
                            "sticky": "nswe",
                            "children": [
                                (
                                    f"{orientation}.Scrollbar.thumb",
                                    {"sticky": "nswe", "expand": "1"},
                                )
                            ],
                        },
                    )
                ],
            )
        style.configure("Sash", sashthickness=5, sashpad=0)
        style.configure("TPanedwindow", background=LINE)

    def destroy(self):
        # Cancel this window's pending callbacks before its Tk commands disappear.
        for timer in self.tk.call("after", "info"):
            self.after_cancel(timer)
        self.update_idletasks()
        super().destroy()

    def _layout(self):
        status = tk.Frame(self, bg=RAIL, padx=16, pady=7)
        status.pack(side="bottom", fill="x")
        tk.Label(
            status, textvariable=self.status, bg=RAIL, fg=MUTED, anchor="w", font=("Consolas", 9)
        ).pack(side="left", fill="x", expand=True)
        tk.Label(status, text="LOCAL  /  FILES", bg=RAIL, fg=MUTED, font=("Consolas", 9)).pack(
            side="right", padx=(16, 0)
        )
        self.rail = rail = tk.Frame(self, bg=RAIL, width=154, padx=10, pady=18)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self.navigation = {}
        for name, label in (
            ("Findings", "Findings"),
            ("Data", "Data"),
            ("Compare", "Compare"),
            ("Health", "Details"),
        ):
            button = ttk.Button(
                rail, text=label, style="Rail.TButton", command=lambda n=name: self.show_page(n)
            )
            button.pack(fill="x", pady=2)
            self.navigation[name] = button
        tk.Frame(rail, bg=LINE, height=1).pack(fill="x", padx=12, pady=20)
        ttk.Button(rail, text="Open case", style="Rail.TButton", command=self._open).pack(
            fill="x", pady=2
        )
        self.rail_line = tk.Frame(self, bg=LINE, width=1)
        self.rail_line.pack(side="left", fill="y")
        self.workspace = tk.Frame(self, bg=BG)
        self.workspace.pack(side="left", fill="both", expand=True)
        self.workspace.rowconfigure(0, weight=1)
        self.workspace.columnconfigure(0, weight=1)
        self.pages = {}
        for name in ("Data", "Findings", "Compare", "Health"):
            page = tk.Frame(self.workspace, bg=BG, padx=18, pady=16)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[name] = page
        self._data_page()
        self._findings_page()
        self._compare_page()
        self._health_page()
        self.show_page("Data")
        self._sync_data_controls()
        self.bind("<Control-o>", lambda _: self._load("current"))
        self.bind("<Control-Return>", lambda _: self._run())
        self.bind("<Control-s>", lambda _: self._save())
        for i, name in enumerate(("Findings", "Data", "Compare", "Health"), 1):
            self.bind(f"<Alt-Key-{i}>", lambda _, n=name: self.show_page(n))

    def show_page(self, name):
        if name != "Data" and not self.result:
            name = "Data"
        self.pages[name].tkraise()
        self.active_page = name
        for key, button in self.navigation.items():
            button.configure(style="Active.Rail.TButton" if key == name else "Rail.TButton")

    def _label(self, parent, text, size=10, bold=False):
        widget = tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=INK,
            font=("Consolas", size, "bold" if bold else "normal"),
            anchor="w",
            justify="left",
        )
        widget.pack(anchor="w", pady=(0, 7))
        return widget

    def _table(self, parent, columns, height=9):
        frame = tk.Frame(parent, bg=BG, highlightthickness=1, highlightbackground=LINE)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=col, anchor="w")
            tree.column(col, width=150, minwidth=90)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)

        def scroll(bar, first, last):
            bar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                bar.grid_remove()
            else:
                bar.grid()

        tree.configure(
            yscrollcommand=lambda first, last: scroll(vertical, first, last),
            xscrollcommand=lambda first, last: scroll(horizontal, first, last),
        )
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _text(self, parent, height=10):
        frame = tk.Frame(parent, bg=WHITE)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        text = tk.Text(
            frame,
            bg=WHITE,
            fg=INK,
            wrap="word",
            font=("Segoe UI", 11),
            relief="flat",
            padx=20,
            pady=18,
            height=height,
            width=28,
            insertbackground=INK,
            selectbackground=SELECTED,
            selectforeground=INK,
            spacing1=2,
            spacing3=5,
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=ACCENT,
        )
        text.tag_configure("muted", foreground=MUTED, font=("Consolas", 10))
        text.tag_configure("evidence", foreground=ACCENT, font=("Consolas", 10))
        text.tag_configure("gap", foreground=AMBER)
        text.tag_configure("value", font=("Consolas", 11))
        scroll = ttk.Scrollbar(frame, command=text.yview)

        def update_scroll(first, last):
            scroll.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scroll.pack_forget()
            else:
                scroll.pack(side="right", fill="y")

        text.configure(yscrollcommand=update_scroll)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return text

    @staticmethod
    def _write(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _data_page(self):
        page = self.pages["Data"]
        self.empty_data = tk.Frame(page, bg=BG)
        start = tk.Frame(self.empty_data, bg=BG)
        start.place(relx=0.12, rely=0.25, anchor="nw")
        self._label(start, "Import data or reopen a saved case.", 11).configure(fg=MUTED)
        entry_actions = tk.Frame(start, bg=BG)
        entry_actions.pack(anchor="w", pady=(8, 12))
        self.start_import = ttk.Button(
            entry_actions,
            text="Import data",
            style="Accent.TButton",
            command=lambda: self._load("current"),
        )
        self.start_import.pack(side="left", padx=(0, 10))
        self.start_open = ttk.Button(entry_actions, text="Open case", command=self._open)
        self.start_open.pack(side="left")
        self._label(start, "CSV · JSON · JSONL", 9).configure(fg=MUTED)
        self.data_setup = tk.Frame(page, bg=BG)
        page = self.data_setup
        actions = tk.Frame(page, bg=BG)
        actions.pack(fill="x", pady=(0, 16))
        self.data_actions = {}
        for title, action in (
            ("Import data", lambda: self._load("current")),
            ("Add reference", lambda: self._load("reference")),
            ("Load policy", self._load_policy),
            ("Save policy", self._save_policy),
        ):
            button = ttk.Button(actions, text=title, command=action)
            button.pack(side="left", padx=(0, 8))
            self.data_actions[title] = button
        self.run_button = ttk.Button(
            actions, text="Analyze", command=self._run, style="Accent.TButton"
        )
        self.run_button.pack(side="right")
        self.setup_hint = self._label(page, "")
        self.setup_hint.configure(fg=MUTED, wraplength=880)
        self.source_label = self._label(page, "No data loaded")
        self.reference_label = self._label(page, "Reference: not loaded")
        self.reference_label.configure(fg=MUTED)
        self.data_separator = tk.Frame(page, bg=LINE, height=1)
        self.data_separator.pack(fill="x", pady=(8, 12))
        body = tk.Frame(page, bg=BG)
        body.pack(fill="both", expand=True, pady=(9, 0))
        mapping_host = tk.Frame(body, bg=BG, width=292)
        mapping_host.pack(side="right", fill="y", padx=(24, 0))
        mapping_host.pack_propagate(False)
        self.mapping_canvas = tk.Canvas(mapping_host, bg=BG, highlightthickness=0, width=272)
        mapping_scroll = ttk.Scrollbar(
            mapping_host, orient="vertical", command=self.mapping_canvas.yview
        )
        mapping_scroll.pack(side="right", fill="y")
        self.mapping_canvas.pack(side="left", fill="both", expand=True)
        self.mapping_canvas.configure(yscrollcommand=mapping_scroll.set)
        mapping = tk.Frame(self.mapping_canvas, bg=BG)
        self.mapping_frame = mapping
        mapping_window = self.mapping_canvas.create_window((0, 0), window=mapping, anchor="nw")
        mapping.bind(
            "<Configure>",
            lambda _: self.mapping_canvas.configure(scrollregion=self.mapping_canvas.bbox("all")),
        )
        self.mapping_canvas.bind(
            "<Configure>",
            lambda event: self.mapping_canvas.itemconfigure(mapping_window, width=event.width),
        )
        self.mapping_notes = {}
        self.mapping_note_widgets = {}

        def note(parent, group):
            holder = tk.Frame(parent, bg=BG)
            holder.pack(fill="x")
            self.mapping_notes[group] = holder
            self.mapping_note_widgets[group] = []
            return holder

        self.numeric_setup = tk.Frame(mapping, bg=BG)
        self.numeric_setup.pack(fill="x")
        self._label(self.numeric_setup, "Values to compare")
        self.features = tk.Listbox(
            self.numeric_setup,
            selectmode="extended",
            exportselection=False,
            height=3,
            font=("Consolas", 10),
            bg=WHITE,
            fg=INK,
            relief="flat",
            selectbackground=SELECTED,
            selectforeground=ACCENT,
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=ACCENT,
        )
        self.features.pack(fill="x", pady=(0, 8))
        self.features.bind("<<ListboxSelect>>", self._changed)
        note(self.numeric_setup, "features")
        self.combos = []
        self.mapping_labels = []
        for title, variable, group in (
            ("Session", self.session, "session"),
            ("Record ID", self.event_id, "event_id"),
            ("Time", self.time, "time"),
        ):
            self.mapping_labels.append(self._label(mapping, title))
            combo = ttk.Combobox(mapping, textvariable=variable, values=[NONE], state="readonly")
            combo.pack(fill="x", pady=(0, 4))
            self.combos.append(combo)
            note(mapping, group)
        self.time_setup = tk.Frame(mapping, bg=BG)
        self._label(self.time_setup, "Time format")
        ttk.Combobox(
            self.time_setup,
            textvariable=self.time_format,
            values=["milliseconds", "seconds", "iso8601"],
            state="readonly",
        ).pack(fill="x", pady=(0, 8))
        ttk.Label(self.time_setup, text="Numeric clock").pack(anchor="w")
        ttk.Combobox(
            self.time_setup,
            textvariable=self.time_origin,
            values=["unspecified", "elapsed", "unix"],
            state="readonly",
        ).pack(fill="x", pady=(0, 8))
        self.threshold_setup = tk.Frame(mapping, bg=BG)
        self.threshold_setup.pack(fill="x", pady=4)
        row = tk.Frame(self.threshold_setup, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="Deviation threshold", bg=BG, fg=INK).pack(side="left")
        ttk.Entry(row, textvariable=self.threshold, width=6).pack(side="right")
        # Keep threshold feedback in the same conditional container.
        self.threshold_note = note(self.threshold_setup, "threshold")
        self.rules_button = ttk.Button(mapping, text="Edit rules", command=self._rules_dialog)
        self.rules_button.pack(fill="x", pady=(10, 5))
        self.rule_label = self._label(mapping, "0 rules")
        note(mapping, "rules")
        ttk.Button(mapping, text="Map context", command=self._context_dialog).pack(
            fill="x", pady=(0, 5)
        )
        self.context_label = self._label(mapping, "No context mapped")
        note(mapping, "context")

        def wheel(event):
            # Leave list/combobox choices to their own scrolling behavior.
            if isinstance(event.widget, (tk.Listbox, ttk.Combobox)):
                return
            self.mapping_canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"

        def wire(widget):
            widget.bind("<MouseWheel>", wheel, add="+")
            widget.bind("<FocusIn>", self._show_mapping_control, add="+")
            for child in widget.winfo_children():
                wire(child)

        wire(mapping_host)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        footer = tk.Frame(left, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.preview_note = self._label(footer, "Preview: first 100 records", 9)
        self.preview_note.configure(fg=MUTED, wraplength=560)
        footer.bind(
            "<Configure>",
            lambda event: self.preview_note.configure(wraplength=max(160, event.width - 8)),
        )
        self.preview_actions = tk.Frame(footer, bg=BG)
        self.preview_back = ttk.Button(
            self.preview_actions, text="Back to preview", command=self._reset_preview
        )
        self.preview_back.pack(side="left")
        self.preview_previous = ttk.Button(
            self.preview_actions, text="Previous", command=lambda: self._preview_step(-1)
        )
        self.preview_previous.pack(side="left", padx=8)
        self.preview_next = ttk.Button(
            self.preview_actions, text="Next", command=lambda: self._preview_step(1)
        )
        self.preview_next.pack(side="left")
        self.preview_split = ttk.Panedwindow(left, orient="vertical")
        self.preview_split.pack(fill="both", expand=True)
        preview_table = tk.Frame(self.preview_split, bg=BG)
        self.preview_split.add(preview_table, weight=1)
        self.preview_values_pane = tk.Frame(self.preview_split, bg=BG)
        self.preview_record_label = self._label(self.preview_values_pane, "", 9)
        self.preview_record_label.configure(fg=MUTED, wraplength=560)
        self.preview_warning = self._label(self.preview_values_pane, "", 9)
        self.preview_warning.configure(fg=AMBER, wraplength=560)
        self.preview_record_actions = tk.Frame(self.preview_values_pane, bg=BG)
        self.preview_record_previous = ttk.Button(
            self.preview_record_actions,
            text="Previous record",
            command=lambda: self._preview_record_step(-1),
        )
        self.preview_record_previous.pack(side="left")
        self.preview_record_next = ttk.Button(
            self.preview_record_actions,
            text="Next record",
            command=lambda: self._preview_record_step(1),
        )
        self.preview_record_next.pack(side="left", padx=8)
        self.preview_record_position = tk.Label(
            self.preview_record_actions, text="", bg=BG, fg=MUTED, font=("Consolas", 9)
        )
        self.preview_record_position.pack(side="left")
        self._preview_search_ready = False
        self.preview_search_actions = tk.Frame(self.preview_values_pane, bg=BG)
        tk.Label(
            self.preview_search_actions,
            text="Find in record",
            bg=BG,
            fg=MUTED,
            font=("Consolas", 9),
        ).pack(side="left", padx=(0, 8))
        self.preview_search = tk.StringVar()
        self.preview_search_entry = ttk.Entry(
            self.preview_search_actions, textvariable=self.preview_search, width=18
        )
        self.preview_search_entry.pack(side="left", fill="x", expand=True)
        self.preview_search_clear = ttk.Button(
            self.preview_search_actions, text="Clear", command=lambda: self.preview_search.set("")
        )
        self.preview_search_clear.pack(side="left", padx=8)
        self.preview_search_count = tk.Label(
            self.preview_search_actions, text="", bg=BG, fg=MUTED, font=("Consolas", 9)
        )
        self.preview_search_count.pack(side="left")
        self.preview_search_entry.bind("<Escape>", lambda _: self.preview_search.set("") or "break")
        self.preview_search.trace_add("write", self._filter_preview_fields)
        self.preview_match_actions = tk.Frame(self.preview_values_pane, bg=BG)
        self.preview_match_previous = ttk.Button(
            self.preview_match_actions,
            text="Previous match",
            command=lambda: self._preview_match_step(-1),
        )
        self.preview_match_previous.pack(side="left")
        self.preview_match_next = ttk.Button(
            self.preview_match_actions,
            text="Next match",
            command=lambda: self._preview_match_step(1),
        )
        self.preview_match_next.pack(side="left", padx=8)
        self.preview_match_count = tk.Label(
            self.preview_match_actions, text="", bg=BG, fg=MUTED, font=("Consolas", 9)
        )
        self.preview_match_count.pack(side="left")
        self.preview_copy_match = ttk.Button(
            self.preview_match_actions,
            text="Copy match",
            command=self._copy_preview_match,
            state="disabled",
        )
        self.preview_copy_match.pack(side="right")
        self._preview_matches = []
        self._preview_match_index = -1
        self.preview_copy_actions = tk.Frame(self.preview_values_pane, bg=BG)
        tk.Label(
            self.preview_copy_actions, text="Field", bg=BG, fg=MUTED, font=("Consolas", 9)
        ).pack(side="left", padx=(0, 8))
        self.preview_copy_field = tk.StringVar()
        self.preview_field_choice = ttk.Combobox(
            self.preview_copy_actions,
            textvariable=self.preview_copy_field,
            state="readonly",
            width=18,
        )
        self.preview_field_choice.pack(side="left", fill="x", expand=True)
        self.preview_field_choice.bind("<<ComboboxSelected>>", self._preview_field_changed)
        self.preview_copy_value = ttk.Button(
            self.preview_copy_actions, text="Copy value", command=lambda: self._copy_preview(False)
        )
        self.preview_copy_value.pack(side="left", padx=8)
        self.preview_copy_record = ttk.Button(
            self.preview_copy_actions, text="Copy record", command=lambda: self._copy_preview(True)
        )
        self.preview_copy_record.pack(side="left")
        self.preview_values = self._text(self.preview_values_pane, height=7)
        self.preview_values.configure(padx=12, pady=10, spacing1=0, spacing3=1)
        self.preview_values.tag_configure(
            "search_match", background=SELECTED, foreground=INK, underline=True
        )
        self.preview_values.tag_configure(
            "search_current", background=ACCENT, foreground=BG, underline=True
        )
        self.preview_values.tag_raise("sel")
        self.preview_values.bind("<Button-1>", self._preview_match_click)
        self.preview_values.bind("<Motion>", self._preview_match_hover)
        self.preview_values.bind("<Leave>", lambda _: self.preview_values.configure(cursor="xterm"))
        for widget in (self.preview_search_entry, self.preview_values):
            widget.bind("<F3>", lambda _: self._preview_match_step(1) or "break")
            widget.bind("<Shift-F3>", lambda _: self._preview_match_step(-1) or "break")
        self.preview_values_pane.bind("<Configure>", self._resize_preview_values)
        self.preview_values_pane.bind(
            "<Map>", lambda _: self.after_idle(self._place_preview_values)
        )
        self.preview = self._table(preview_table, ["Import data to view records"], height=7)
        self.preview.configure(show="tree headings", selectmode="browse")
        self.preview.heading("#0", text="Record")
        self.preview.column("#0", width=130, minwidth=130, stretch=False)
        self.preview.tag_configure("related", foreground=MUTED)
        self.preview.tag_configure("affected", foreground=AMBER)
        self.preview.bind("<<TreeviewSelect>>", self._inspect_preview)
        self.preview.bind("<Return>", self._inspect_preview)
        self._preview_dataset = None

    def _resize_preview_values(self, event):
        for label in (self.preview_record_label, self.preview_warning):
            label.configure(wraplength=max(160, event.width - 12))

    def _place_preview_values(self, _event=None):
        if len(self.preview_split.panes()) == 2 and self.preview_values_pane.winfo_ismapped():
            fraction = 0.25 if self.preview_search.get() else 0.35
            self.preview_split.sashpos(
                0, max(110, int(self.preview_split.winfo_height() * fraction))
            )

    def _clear_preview_values(self):
        self._preview_search_ready = False
        self._preview_visible_fields = []
        self.preview_search.set("")
        self.preview_search_actions.pack_forget()
        self.preview_search_count.configure(text="")
        self.preview_match_actions.pack_forget()
        self._preview_matches = []
        self._preview_match_index = -1
        self.preview_values.configure(cursor="xterm")
        self.preview_match_count.configure(text="")
        for button in (
            self.preview_match_previous,
            self.preview_match_next,
            self.preview_copy_match,
        ):
            button.configure(state="disabled")
        if str(self.preview_values_pane) in self.preview_split.panes():
            self.preview_split.forget(self.preview_values_pane)
        self.preview_record_label.configure(text="")
        self.preview_warning.configure(text="")
        self.preview_record_actions.pack_forget()
        self.preview_record_position.configure(text="")
        self.preview_copy_actions.pack_forget()
        self.preview_copy_field.set("")
        self.preview_field_choice.configure(values=())
        self.preview_copy_value.configure(state="disabled")
        self.preview_copy_record.configure(state="disabled")
        for button in (self.preview_record_previous, self.preview_record_next):
            button.configure(state="disabled")
        self._write(self.preview_values, "")

    def _preview_selected_row(self):
        selected = self.preview.selection()
        data = self._preview_dataset
        note = self._preview_note
        if (
            not selected
            or data is None
            or data is not (getattr(self, note.source, None) if note else self.current)
            or (note is not None and not self._preview_affected_records())
        ):
            return None
        index = int(selected[0])
        if not self.preview.exists(str(index)) or not 1 <= index <= len(data.rows):
            return None
        return data.rows[index - 1]

    def _preview_field_changed(self, _event=None):
        row = self._preview_selected_row()
        field = self.preview_copy_field.get()
        self.preview_copy_value.configure(
            state="normal" if row is not None and field in row else "disabled"
        )
        if field in self._preview_visible_fields:
            self.preview_values.see(f"preview_field_{self._preview_fields.index(field)}")

    def _copy_preview(self, whole_record):
        row = self._preview_selected_row()
        if row is None:
            self._clear_preview_values()
            self.status.set("Select a record to copy.")
            return
        field = self.preview_copy_field.get()
        if not whole_record and field not in row:
            self.status.set("Field is missing. Nothing copied.")
            return
        # JSON preserves types, Unicode, and control characters without inventing missing values.
        payload = json.dumps(row if whole_record else row[field], ensure_ascii=False, indent=2)
        self._copy_preview_text(
            payload, "Record copied as JSON." if whole_record else "Value copied as JSON."
        )

    def _copy_preview_text(self, payload, message):
        try:
            self.clipboard_clear()
            self.clipboard_append(payload)
        except tk.TclError:
            self.status.set("Could not copy. Try again.")
            return
        self.status.set(message)

    def _copy_preview_match(self):
        if not self._preview_search_ready:
            self.status.set("Select a match to copy.")
            return
        row = self._preview_selected_row()
        if (
            row is None
            or row is not self._preview_match_row
            or self.preview_search.get().casefold() != self._preview_match_query
        ):
            self._filter_preview_fields()
            self.status.set("Select a match to copy.")
            return
        if not 0 <= self._preview_match_index < len(self._preview_matches):
            self.status.set("Select a match to copy.")
            return
        _, start, end = self._preview_matches[self._preview_match_index]
        # Copy the original displayed characters, not the query or a case-folded version.
        self._copy_preview_text(
            self.preview_values.get(start, end), "Match copied as displayed text."
        )

    def _preview_affected_records(self):
        note = self._preview_note
        data = self._preview_dataset
        if (
            note is None
            or data is None
            or data is not getattr(self, note.source, None)
            or self.mapping_report is None
            or not any(
                note is item for notes in self.mapping_report.groups.values() for item in notes
            )
        ):
            return []
        return sorted(set(range(1, len(data.rows) + 1) if note.rows is None else note.rows))

    def _preview_record_step(self, step):
        selected = self.preview.selection()
        affected = self._preview_affected_records()
        if not selected or not affected or step not in (-1, 1):
            return
        index = int(selected[0])
        candidates = [row for row in affected if (row < index if step < 0 else row > index)]
        if not candidates:
            return
        target = candidates[-1] if step < 0 else candidates[0]
        page = self._preview_rows.index(target) // 100
        if page != self._preview_page:
            self._preview_page = page
            self._render_preview(selected_record=target)
        else:
            self.preview.selection_set(str(target))
            self.preview.focus(str(target))
            self.preview.see(str(target))
            self._inspect_preview()

    def _inspect_preview(self, _event=None):
        selected = self.preview.selection()
        data = self._preview_dataset
        note = self._preview_note
        expected = getattr(self, note.source) if note else self.current
        if not selected or data is None or data is not expected:
            self._clear_preview_values()
            return
        index = int(selected[0])
        if not self.preview.exists(str(index)) or not 1 <= index <= len(data.rows):
            self._clear_preview_values()
            return
        row = data.rows[index - 1]
        role = "Reference" if note and note.source == "reference" else "Incoming"
        relation = " · related" if "related" in self.preview.item(str(index), "tags") else ""
        self.preview_record_label.configure(text=f"{role} · {data.name} · Record {index}{relation}")
        self.preview_warning.configure(text=note.text if note else "")
        if note:
            self.preview_warning.pack(fill="x", pady=(0, 7), after=self.preview_record_label)
            affected = self._preview_affected_records()
            self.preview_record_actions.pack(fill="x", pady=(0, 7), after=self.preview_warning)
            self.preview_record_position.configure(
                text=(
                    f"{affected.index(index) + 1:,} of {len(affected):,} affected"
                    if index in affected
                    else f"Related · {len(affected):,} affected"
                )
            )
            self.preview_record_previous.configure(
                state="normal" if any(i < index for i in affected) else "disabled"
            )
            self.preview_record_next.configure(
                state="normal" if any(i > index for i in affected) else "disabled"
            )
        else:
            self.preview_warning.pack_forget()
            self.preview_record_actions.pack_forget()
        self.preview_search_actions.pack(
            fill="x",
            pady=(0, 7),
            after=self.preview_record_actions if note else self.preview_record_label,
        )
        self.preview_copy_actions.pack(fill="x", pady=(0, 7), after=self.preview_search_actions)
        self.preview_copy_record.configure(state="normal")
        self._preview_search_ready = True
        self._filter_preview_fields()
        if str(self.preview_values_pane) not in self.preview_split.panes():
            self.preview_split.add(self.preview_values_pane, weight=1)

    def _filter_preview_fields(self, *_args):
        if not self._preview_search_ready:
            return
        row = self._preview_selected_row()
        if row is None:
            self._clear_preview_values()
            return
        note = self._preview_note
        query = self.preview_search.get().casefold()
        was_shown = bool(self.preview_match_actions.winfo_manager())
        if query:
            self.preview_match_actions.pack(
                fill="x", pady=(0, 7), after=self.preview_search_actions
            )
        else:
            self.preview_match_actions.pack_forget()
        if was_shown != bool(query):
            self.after_idle(self._place_preview_values)
        self._preview_matches = []
        self._preview_match_index = -1
        self._preview_match_row = row
        self._preview_match_query = query
        values = {
            field: json.dumps(row[field], ensure_ascii=False) if field in row else "Missing"
            for field in self._preview_fields
        }
        self._preview_visible_fields = [
            field
            for field, value in values.items()
            if query in field.casefold() or query in value.casefold()
        ]
        visible = self._preview_visible_fields
        self.preview_search_count.configure(text=f"{len(visible)} of {len(values)} fields")
        self.preview_search_clear.configure(state="normal" if query else "disabled")
        self.preview_field_choice.configure(values=visible)
        if self.preview_copy_field.get() not in visible:
            self.preview_copy_field.set(next(iter(visible), ""))
        self.preview_copy_value.configure(
            state="normal" if visible and self.preview_copy_field.get() in row else "disabled"
        )
        text = self.preview_values
        text.configure(state="normal")
        text.delete("1.0", "end")
        for position, field in enumerate(self._preview_fields):
            if field not in visible:
                continue
            mark = f"preview_field_{position}"
            text.mark_set(mark, "end-1c")
            text.mark_gravity(mark, "left")
            text.insert(
                "end",
                ("→ " if note and field in note.fields else "") + field + "\n",
                "evidence" if note and field in note.fields else "muted",
            )
            prefix = 2 if note and field in note.fields else 0
            self._add_preview_matches(field, field, text.index(f"{mark}+{prefix}c"), query)
            # Read the source row, never the shortened text in the table.
            value = values[field]
            value_start = text.index("end-1c")
            text.insert("end", value + "\n\n", "value")
            self._add_preview_matches(field, value, value_start, query)
        if not visible:
            text.insert("end", "No matching fields.", "muted")
        text.configure(state="disabled")
        text.yview_moveto(0)
        if self._preview_matches:
            self._preview_match_index = 0
        self._show_preview_match()

    def _add_preview_matches(self, field, value, start, query):
        for first, last in match_spans(value, query):
            begin = self.preview_values.index(f"{start}+{first}c")
            end = self.preview_values.index(f"{start}+{last}c")
            self.preview_values.tag_add("search_match", begin, end)
            self._preview_matches.append((field, begin, end))

    def _show_preview_match(self, scroll=True):
        text = self.preview_values
        text.tag_remove("search_current", "1.0", "end")
        index = self._preview_match_index
        count = len(self._preview_matches)
        self.preview_match_count.configure(
            text=f"{index + 1} of {count} matches" if count else "No matches"
        )
        self.preview_match_previous.configure(state="normal" if index > 0 else "disabled")
        self.preview_match_next.configure(state="normal" if 0 <= index < count - 1 else "disabled")
        self.preview_copy_match.configure(state="normal" if 0 <= index < count else "disabled")
        if index >= 0:
            field, start, end = self._preview_matches[index]
            text.tag_add("search_current", start, end)
            if scroll:
                text.see(end)
                text.see(start)
            self.preview_copy_field.set(field)
            row = self._preview_selected_row()
            self.preview_copy_value.configure(
                state="normal" if row is not None and field in row else "disabled"
            )

    def _preview_match_at(self, x, y):
        text = self.preview_values
        index = text.index(f"@{x},{y}")
        box = text.bbox(index)
        # Text.index snaps blank space to nearby text. Only actual glyph cells are clickable.
        if box is None or not (box[0] <= x < box[0] + box[2] and box[1] <= y < box[1] + box[3]):
            return None
        return next(
            (
                i
                for i, (_, start, end) in enumerate(self._preview_matches)
                if text.compare(start, "<=", index) and text.compare(index, "<", end)
            ),
            None,
        )

    def _preview_match_hover(self, event):
        hit = self._preview_match_at(event.x, event.y) if self._preview_search_ready else None
        self.preview_values.configure(cursor="hand2" if hit is not None else "xterm")

    def _preview_match_click(self, event):
        if not self._preview_search_ready:
            return
        if (
            self._preview_selected_row() is not self._preview_match_row
            or self.preview_search.get().casefold() != self._preview_match_query
        ):
            self._filter_preview_fields()
            return
        hit = self._preview_match_at(event.x, event.y)
        if hit is not None:
            self._preview_match_index = hit
            self._show_preview_match(scroll=False)
            self.preview_values.focus_set()
        # Keep native text selection and drag-to-copy available.

    def _preview_match_step(self, step):
        if not self._preview_search_ready or step not in (-1, 1):
            return
        if (
            self._preview_selected_row() is not self._preview_match_row
            or self.preview_search.get().casefold() != self._preview_match_query
        ):
            self._filter_preview_fields()
            return
        target = self._preview_match_index + step
        if 0 <= target < len(self._preview_matches):
            self._preview_match_index = target
            self._show_preview_match()

    def _render_mapping_notes(self):
        report = self.mapping_report
        for group, holder in self.mapping_notes.items():
            for child in holder.winfo_children():
                child.destroy()
            self.mapping_note_widgets[group] = []
            for note in report.groups.get(group, []):
                linked = note.source is not None
                widget = self._label(holder, note.text, 9)
                widget.configure(
                    fg=AMBER if note.level != "info" else MUTED,
                    wraplength=260,
                    cursor="hand2" if linked else "",
                    takefocus=linked,
                    highlightthickness=1 if linked else 0,
                    highlightbackground=BG,
                    highlightcolor=ACCENT,
                    font=("Consolas", 9, "underline" if linked else "normal"),
                )
                self.mapping_note_widgets[group].append(widget)
                if linked:

                    def open_note(_event=None, item=note, snapshot=report):
                        self._open_mapping_preview(item, snapshot)
                        return "break"

                    widget.bind("<Button-1>", open_note)
                    widget.bind("<Return>", open_note)
                    widget.bind("<space>", open_note)
                    widget.bind("<FocusIn>", self._show_mapping_control)
                widget.bind(
                    "<MouseWheel>",
                    lambda event: self.mapping_canvas.yview_scroll(
                        -int(event.delta / 120), "units"
                    ),
                )

    def _open_mapping_preview(self, note, report):
        # An old callback must never inspect a replacement source or mapping.
        if report is not self.mapping_report or note.source is None:
            return
        if not any(note is item for notes in report.groups.values() for item in notes):
            return
        if getattr(self, note.source, None) is None:
            return
        self._preview_note = note
        self._preview_page = 0
        self._render_preview()
        self.preview.focus_set()

    def _reset_preview(self):
        self._preview_note = None
        self._preview_page = 0
        self._render_preview()

    def _preview_step(self, step):
        if self._preview_note:
            self._preview_page = max(
                0, min(self._preview_page + step, (len(self._preview_rows) - 1) // 100)
            )
            self._render_preview()

    def _render_preview(self, selected_record=None):
        note = self._preview_note
        data = getattr(self, note.source) if note else self.current
        copy_field = self.preview_copy_field.get() if data is self._preview_dataset else ""
        search = self.preview_search.get() if data is self._preview_dataset else ""
        self._clear_preview_values()
        self.preview_copy_field.set(copy_field)
        self.preview_search.set(search)
        self._preview_dataset = data
        if data is None:
            self.preview.delete(*self.preview.get_children())
            return
        affected = set(
            range(1, len(data.rows) + 1)
            if note and note.rows is None
            else note.rows if note else ()
        )
        related = set(note.related) - affected if note else set()
        indices = (
            sorted(affected | related) if note else list(range(1, min(100, len(data.rows)) + 1))
        )
        self._preview_rows = indices
        fields = list(dict.fromkeys((*note.fields, *data.fields))) if note else list(data.fields)
        self._preview_fields = fields
        self.preview.delete(*self.preview.get_children())
        columns = [f"field_{i}" for i in range(len(fields))]
        self.preview.configure(columns=columns)
        for column, field in zip(columns, fields):
            self.preview.heading(
                column, text=("→ " if note and field in note.fields else "") + field
            )
            self.preview.column(column, width=145, minwidth=120)
        start = self._preview_page * 100 if note else 0
        visible = indices[start : start + 100]
        shortened = False
        for index in visible:
            row = data.rows[index - 1]
            values = []
            for field in fields:
                value = json.dumps(row[field], ensure_ascii=False) if field in row else "Missing"
                if len(value) > 180:
                    value = value[:179] + "…"
                    shortened = True
                values.append(value)
            self.preview.insert(
                "",
                "end",
                iid=str(index),
                text=f"{index} · related" if index in related else str(index),
                values=values,
                tags=("related" if index in related else "affected",) if note else (),
            )
        self.preview.xview_moveto(0)
        self.preview.yview_moveto(0)
        if note:
            selected = (
                selected_record
                if selected_record in visible
                else next(
                    (index for index in visible if index in affected), next(iter(visible), None)
                )
            )
            if selected is not None:
                self.preview.selection_set(str(selected))
                self.preview.focus(str(selected))
                self.preview.see(str(selected))
            role = "Reference" if note.source == "reference" else "Incoming"
            # Source identity stays beside the view, since the main data label remains incoming.
            message = (
                f"{role} · {data.name} · {len(affected):,} affected"
                + (f" · {len(related):,} related" if related else "")
                + f" · Showing {start + 1 if visible else 0}–{start + len(visible)} of {len(indices):,}"
                + "\n→ marks the affected fields. Record numbers are file positions."
            )
            self.preview_actions.pack(fill="x")
            self.preview_previous.configure(state="normal" if start else "disabled")
            self.preview_next.configure(
                state="normal" if start + 100 < len(indices) else "disabled"
            )
        else:
            message = f"Incoming · {data.name} · Preview: first {len(visible):,} records"
            self.preview_actions.pack_forget()
        if shortened:
            message += "\nTable values are shortened. Select a record for full values."
        elif not note:
            message += "\nSelect a record for full values."
        self.preview_note.configure(text=message)
        self._inspect_preview()

    def _show_mapping_control(self, event):
        self.update_idletasks()
        widget = event.widget
        top = widget.winfo_rooty() - self.mapping_frame.winfo_rooty()
        view_top = self.mapping_canvas.canvasy(0)
        height = self.mapping_canvas.winfo_height()
        if top < view_top or top + widget.winfo_height() > view_top + height:
            target = max(0, top - 12)
            self.mapping_canvas.yview_moveto(target / max(1, self.mapping_frame.winfo_height()))

    def _sync_data_controls(self):
        loaded = self.current is not None
        if loaded:
            self.empty_data.pack_forget()
            self.data_setup.pack(fill="both", expand=True)
            self.rail.pack(side="left", fill="y", before=self.workspace)
            self.rail_line.pack(side="left", fill="y", before=self.workspace)
        else:
            self.data_setup.pack_forget()
            self.empty_data.pack(fill="both", expand=True)
            self.rail.pack_forget()
            self.rail_line.pack_forget()
        available = "disabled" if self.busy else "normal"
        self.start_import.configure(state=available)
        self.start_open.configure(state=available)
        for button in self.data_actions.values():
            button.configure(state=available if loaded else "disabled")
        for name, button in self.navigation.items():
            button.configure(state="normal" if name == "Data" or self.result else "disabled")
        if not self.result and getattr(self, "active_page", "Data") != "Data":
            self.show_page("Data")
        # Keep widgets and values alive while hiding irrelevant setup.
        if self.features.size():
            self.numeric_setup.pack(fill="x", before=self.mapping_labels[0])
        else:
            self.numeric_setup.pack_forget()
        if self.time.get() != NONE:
            self.time_setup.pack(fill="x", before=self.rules_button)
        else:
            self.time_setup.pack_forget()
        selected = bool(self.features.curselection())
        try:
            threshold_valid = 1 <= float(self.threshold.get()) <= 100
        except ValueError:
            threshold_valid = False
        if selected or not threshold_valid:
            self.threshold_setup.pack(fill="x", pady=4, before=self.rules_button)
        else:
            self.threshold_setup.pack_forget()
        if selected or self.reference:
            self.reference_label.pack(anchor="w", pady=(0, 7), before=self.data_separator)
        else:
            self.reference_label.pack_forget()
        ready, policy_ready, hint = False, False, ""
        if loaded:
            if not selected and not self.rules:
                hint = (
                    "Choose values or add a rule."
                    if self.features.size()
                    else "Add a rule to analyze these records."
                )
            elif selected and self.reference is None:
                hint = "Add a reference for the selected values."
            else:
                try:
                    engine.validate_config(self.config(), self.current, self.reference)
                    ready = True
                except (ValueError, TypeError) as exc:
                    hint = str(exc)
            policy_ready = ready
            config = self.config(raw_threshold=True)
            key = (id(self.current), id(self.reference), engine.canonical(config))
            if key != self._mapping_key:
                self.mapping_report = mapping_checks.check(self.current, self.reference, config)
                self._mapping_key = key
                self._render_mapping_notes()
                if self._preview_note:
                    self._reset_preview()
            report = self.mapping_report
            if report.blocked:
                ready = False
                if not hint:
                    hint = "Fix the marked fields before analyzing."
            elif any(note.level == "check" for notes in report.groups.values() for note in notes):
                hint = "Check the marked fields. Analysis can continue with gaps."
        self.setup_hint.configure(text=hint)
        if hint:
            self.setup_hint.pack(anchor="w", pady=(0, 7), before=self.source_label)
        else:
            self.setup_hint.pack_forget()
        self.run_button.configure(state="normal" if ready and not self.busy else "disabled")
        self.data_actions["Save policy"].configure(
            state="normal" if policy_ready and not self.busy else "disabled"
        )

    def _findings_page(self):
        page = self.pages["Findings"]
        self.summary_label = self._label(page, "No results yet")
        self.summary_label.configure(fg=MUTED, font=("Consolas", 10))
        filters = tk.Frame(page, bg=BG)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            filters, text="Findings only", variable=self.only_leads, command=self._render_findings
        ).pack(side="left")
        tk.Label(filters, text="Priority ≥", bg=BG, fg=MUTED, font=("Consolas", 10)).pack(
            side="left", padx=(18, 6)
        )
        priority = ttk.Combobox(
            filters,
            textvariable=self.minimum_priority,
            values=["All", *engine.PRIORITIES],
            state="readonly",
            width=10,
        )
        priority.pack(side="left")
        priority.bind("<<ComboboxSelected>>", lambda _: self._render_findings())
        ttk.Button(filters, text="Export alerts", command=self._export_alerts).pack(side="right")
        self.export_button = ttk.Button(
            filters, text="Save case", command=self._save, state="disabled"
        )
        self.export_button.pack(side="right", padx=(8, 8))
        search_row = tk.Frame(page, bg=BG)
        search_row.pack(fill="x", pady=(0, 8))
        tk.Label(search_row, text="Search", bg=BG, fg=MUTED, font=("Consolas", 10)).pack(
            side="left", padx=(0, 8)
        )
        self.search_entry = ttk.Entry(search_row, textvariable=self.search, width=28)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Escape>", self._clear_search)
        self.search_entry.bind("<Return>", lambda _: self._render_findings())
        self.clear_search_button = ttk.Button(search_row, text="Clear", command=self._clear_search)
        self.clear_search_button.pack(side="left", padx=8)
        tk.Label(
            search_row, text="ID · session · user · rule", bg=BG, fg=MUTED, font=("Consolas", 10)
        ).pack(side="left")
        self.filter_note = self._label(
            page, "Priority keeps gaps visible. Search filters the list; exports use priority.", 9
        )
        self.filter_note.configure(fg=MUTED)
        self.investigation = ttk.Panedwindow(page, orient="horizontal")
        self.investigation.pack(fill="both", expand=True, pady=(8, 0))
        records = tk.Frame(self.investigation, bg=BG, width=500)
        inspection = tk.Frame(self.investigation, bg=WHITE, width=500)
        self.investigation.add(records, weight=1)
        self.investigation.add(inspection, weight=1)
        self.investigation.bind("<Configure>", self._resize_split)
        self.investigation.bind("<ButtonRelease-1>", self._remember_split)
        self.chart_frame = tk.Frame(records, bg=BG)
        self.chart_frame.pack(side="bottom", fill="x", pady=(12, 0))
        self.timeline = tk.Canvas(
            self.chart_frame,
            bg=BG,
            height=110,
            highlightthickness=1,
            highlightbackground=BG,
            highlightcolor=ACCENT,
            takefocus=True,
            cursor="hand2",
        )
        self.timeline.pack(fill="x")
        self.timeline.bind("<Configure>", lambda event: self._plot())
        self.timeline.bind("<Button-1>", self._chart_click)
        self.timeline.bind("<Left>", lambda _: self._chart_step(-1))
        self.timeline.bind("<Right>", lambda _: self._chart_step(1))
        self.chart_readout = tk.Label(
            self.chart_frame,
            text="",
            bg=BG,
            fg=INK,
            anchor="w",
            justify="left",
            font=("Consolas", 10),
            wraplength=450,
        )
        self.chart_readout.pack(fill="x", padx=12, pady=(2, 4))
        self.chart_return = ttk.Button(
            self.chart_frame, text="Return to filters", command=self._render_findings
        )
        self.findings = self._table(records, ["Record", "Priority", "Result", "Match"], height=5)
        for name, width in (("Record", 65), ("Priority", 85), ("Result", 90), ("Match", 210)):
            self.findings.column(name, width=width, minwidth=min(width, 90))
        for tag, color in (
            ("Critical", RED),
            ("Error", RED),
            ("Warning", AMBER),
            ("Notice", INK),
            ("Unknown", AMBER),
        ):
            self.findings.tag_configure(tag, foreground=color)
        self.findings.bind("<<TreeviewSelect>>", self._inspect)
        disclosures = tk.Frame(inspection, bg=WHITE)
        disclosures.pack(side="bottom", fill="x", padx=16, pady=10)
        ttk.Checkbutton(
            disclosures, text="Details", variable=self.show_details, command=self._inspect
        ).pack(side="left")
        ttk.Checkbutton(
            disclosures, text="Source values", variable=self.show_values, command=self._inspect
        ).pack(side="left", padx=16)
        self.detail = self._text(inspection, height=10)
        self.detail.configure(spacing1=1, spacing3=2, pady=14)
        self._write(
            self.detail,
            "Select a record.\n\nIts values, context, and matching conditions appear here.",
        )

    def _resize_split(self, event):
        if event.widget is self.investigation and event.width > 1:
            self.investigation.sashpos(0, int(event.width * self._split_ratio))

    def _remember_split(self, _=None):
        width = self.investigation.winfo_width()
        if width <= 1:
            return
        ratio = min(0.7, max(0.3, self.investigation.sashpos(0) / width))
        self._split_ratio = ratio
        self.investigation.sashpos(0, int(width * ratio))
        try:
            UI_STATE.write_text(json.dumps({"split": ratio}), encoding="utf-8")
        except OSError:
            self.status.set("Layout updated for this session; the preference could not be saved.")

    def _compare_page(self):
        page = self.pages["Compare"]
        actions = tk.Frame(page, bg=BG)
        actions.pack(fill="x", pady=(0, 12))
        ttk.Button(actions, text="Choose case", command=self._compare).pack(side="left")
        self.settings_button = ttk.Button(
            actions, text="Settings", command=lambda: self._comparison_mode(False)
        )
        self.settings_button.pack(side="left", padx=(12, 0))
        self.changed_records_button = ttk.Button(
            actions,
            text="Changed records",
            state="disabled",
            command=lambda: self._comparison_mode(True),
        )
        self.changed_records_button.pack(side="left", padx=(8, 0))
        self.changes_filter = ttk.Checkbutton(
            actions,
            text="Changes only",
            variable=self.differences_only,
            command=self._render_comparison,
        )
        self.changes_filter.pack(side="left", padx=16)
        self.comparison_note = tk.StringVar(value="Analyze data, then choose a saved case.")
        self._label(page, "").configure(textvariable=self.comparison_note, fg=MUTED)
        self._label(page, "Fewer findings do not establish better accuracy.", 9).configure(fg=MUTED)
        self.compare_body = tk.Frame(page, bg=BG)
        self.compare_body.pack(fill="both", expand=True, pady=(8, 0))
        self.changed_list_frame = tk.Frame(self.compare_body, bg=BG, width=200)
        self.changed_list_frame.pack_propagate(False)
        self.changed_list = self._table(self.changed_list_frame, ["Record", "Change"])
        self.changed_list.column("Record", width=55, minwidth=50, stretch=False)
        self.changed_list.column("Change", width=140, minwidth=125)
        self.changed_list.bind("<<TreeviewSelect>>", self._inspect_comparison)
        self.comparison = ComparisonView(
            self.compare_body, background=BG, foreground=INK, muted=MUTED, line=LINE, changed=AMBER
        )
        self.comparison.pack(side="right", fill="both", expand=True)

    def _health_page(self):
        page = self.pages["Health"]
        self.health = self._text(page)
        self._write(self.health, "No analysis yet. Import data and define its fields in Data.")

    def _changed(self, *_):
        self.generation += 1
        if self.result is not None:
            self.result = self.run_config = None
            self.export_button.configure(state="disabled")
            self.status.set("Data or settings changed. Analyze again to refresh the findings.")
            self._render_findings()
            self._write(self.health, "Settings changed. Analyze again to update details.")
            self._clear_comparison()
            self.comparison_note.set("Settings changed. Analyze again to compare.")
        self._sync_data_controls()

    def _job(self, kind, function):
        if self.busy:
            return
        self.busy = True
        self._sync_data_controls()
        token = self.generation
        self.status.set("Working…")

        def work():
            try:
                self.messages.put((kind, token, function(), None))
            except Exception as exc:
                self.messages.put((kind, token, None, exc))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            kind, token, value, error = self.messages.get_nowait()
        except queue.Empty:
            self.after(60, self._poll)
            return
        self.busy = False
        if error:
            self.status.set("Operation could not complete. Your previous data was retained.")
            if isinstance(error, ImportFailure):
                self.status.set(
                    "Import failed. Fix the listed problems and try again. Your previous data was retained."
                )
                self._show_import_error(error, kind)
            else:
                messagebox.showerror("Check the input", str(error), parent=self)
        elif kind in ("current", "reference"):
            setattr(self, kind, value)
            if kind == "current":
                self.rules = []
                self.context = {}
                self.reference_by = []
                self.time_origin.set("unspecified")
                for var in (self.session, self.event_id, self.time):
                    var.set(NONE)
            self._changed()
            self._refresh_data()
            self.show_page("Data")
            self.status.set(f"Loaded {len(value.rows):,} records from {value.name}.")
        elif kind == "analysis":
            if token != self.generation:
                self.status.set(
                    "Settings changed during analysis. Run again to use the latest settings."
                )
            else:
                self.result, self.run_config = value
                self.export_button.configure(state="normal")
                self._render_findings()
                self._render_health()
                self._render_comparison()
                self.show_page("Findings")
                self.status.set("Analysis complete. Findings are linked to the imported evidence.")
        elif kind == "open":
            self.current, self.reference, config, result = value
            self.result = None
            self._refresh_data()
            self._apply_config(config)
            self.result, self.run_config = result, config
            self.export_button.configure(state="normal")
            self._render_findings()
            self._render_health()
            self._render_comparison()
            self.show_page("Findings")
            self.status.set(
                "Case reopened and results recomputed. Imported evidence remains an assertion."
            )
        elif kind == "compare":
            self.previous = value
            self._render_comparison()
            self.status.set("Comparison case verified and recomputed.")
        elif kind == "save":
            self.status.set("Case saved with source evidence, settings, and reproducible findings.")
        elif kind == "policy_load":
            if token != self.generation:
                self.status.set(
                    "Settings changed while loading. Load the policy again to apply it."
                )
            else:
                self._apply_config(value)
                self.show_page("Data")
                self.status.set("Policy loaded. Check the mappings, then Analyze.")
        elif kind == "policy_save":
            self.status.set("Policy saved. It contains settings, not source records.")
        elif kind == "alerts":
            self.status.set(
                f"Exported {value:,} alerts from the analysis snapshot. Gaps were included."
            )
        self._sync_data_controls()
        self.after(60, self._poll)

    def _show_import_error(self, error, role):
        window = tk.Toplevel(self)
        window.title("Check import")
        window.configure(bg=BG)
        window.geometry("760x490")
        window.minsize(520, 320)
        window.transient(self)
        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(18, 10))
        text = tk.Text(
            body,
            wrap="word",
            bg=BG,
            fg=INK,
            insertbackground=INK,
            selectbackground=SELECTED,
            relief="flat",
            font=("Consolas", 11),
            padx=4,
            pady=4,
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        prefix = "Reference: " if role == "reference" else ""
        text.insert("1.0", prefix + error.describe())
        text.configure(state="disabled")
        actions = tk.Frame(window, bg=BG)
        actions.pack(side="bottom", fill="x", padx=18, pady=(0, 16), before=body)
        ttk.Button(actions, text="Close", command=window.destroy).pack(side="right")
        window.bind("<Escape>", lambda _event: window.destroy())
        text.focus_set()
        window.grab_set()
        return window

    def _load(self, role):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose data",
            filetypes=[("Data files", "*.csv *.json *.jsonl *.ndjson"), ("All files", "*.*")],
        )
        if path:
            self._job(role, lambda: engine.load_dataset(path))

    def _refresh_data(self):
        selected = [self.features.get(i) for i in self.features.curselection()]
        self.features.delete(0, "end")
        if self.current:
            d = self.current
            self.source_label.configure(
                text=f"{d.name}   ·   {len(d.rows):,} records   ·   {len(d.fields)} fields"
            )
            for combo in self.combos:
                combo.configure(values=[NONE, *d.fields])
            for field in engine.numeric_fields(d):
                self.features.insert("end", field)
                if field in selected:
                    self.features.selection_set(self.features.size() - 1)
            self._reset_preview()
        self.reference_label.configure(
            text=(
                f"Reference   {self.reference.name}   ·   {len(self.reference.rows):,} records"
                if self.reference
                else "Reference: not loaded"
            )
        )
        self.rule_label.configure(text=f"{len(self.rules)} rules")
        self.context_label.configure(
            text=(
                f"{len(self.context)} context fields mapped"
                if self.context
                else "No context mapped"
            )
        )
        self._sync_data_controls()

    def config(self, *, raw_threshold=False):
        config = {
            "features": [self.features.get(i) for i in self.features.curselection()],
            "session": None if self.session.get() == NONE else self.session.get(),
            "event_id": None if self.event_id.get() == NONE else self.event_id.get(),
            "time": None if self.time.get() == NONE else self.time.get(),
            "time_format": self.time_format.get(),
            "threshold": self.threshold.get() if raw_threshold else float(self.threshold.get()),
            "rules": json.loads(json.dumps(self.rules)),
        }
        if self.context:
            config["context"] = dict(self.context)
        if self.reference_by:
            config["reference_by"] = list(self.reference_by)
        if self.time_origin.get() != "unspecified":
            config["time_origin"] = self.time_origin.get()
        return config

    def _apply_config(self, config):
        self._changed()
        self.reference_by = list(config.get("reference_by", []))
        self.time_origin.set(config.get("time_origin", "unspecified"))
        self.features.selection_clear(0, "end")
        for i in range(self.features.size()):
            if self.features.get(i) in config["features"]:
                self.features.selection_set(i)
        for key in ("session", "event_id", "time", "time_format", "threshold"):
            getattr(self, key).set(config[key] if config[key] is not None else NONE)
        self.rules = json.loads(json.dumps(config["rules"]))
        self.context = dict(config.get("context", {}))
        self.rule_label.configure(text=f"{len(self.rules)} rules")
        self.context_label.configure(
            text=(
                f"{len(self.context)} context fields mapped"
                if self.context
                else "No context mapped"
            )
        )
        self._sync_data_controls()

    def _load_policy(self):
        if self.busy:
            return
        if not self.current:
            messagebox.showinfo(
                "Import data",
                "Load data and any needed reference before loading a policy.",
                parent=self,
            )
            return
        path = filedialog.askopenfilename(
            parent=self, title="Load policy", filetypes=[("Surge policy", "*.json")]
        )
        if path:
            current, reference = self.current, self.reference
            self._job("policy_load", lambda: workflow.load_policy(path, current, reference))

    def _save_policy(self):
        if self.busy:
            return
        if not self.current:
            messagebox.showinfo(
                "Import data",
                "Load data and configure a rule or numeric comparison first.",
                parent=self,
            )
            return
        try:
            config = self.config()
            engine.validate_config(config, self.current, self.reference)
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Check policy", str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save new policy",
            initialfile="surge.policy.json",
            defaultextension=".json",
            filetypes=[("Surge policy", "*.json")],
        )
        if path:
            current, reference = self.current, self.reference
            self._job("policy_save", lambda: workflow.save_policy(path, current, reference, config))

    def _context_dialog(self):
        if self.busy or not self.current:
            return
        window = tk.Toplevel(self)
        window.title("Surge — Context")
        window.geometry("490x300")
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()
        body = tk.Frame(window, bg=BG, padx=18, pady=18)
        body.pack(fill="both", expand=True)
        self._label(body, "Choose fields already present in your data.")
        self._label(body, "Mapped values are shown with each finding.")
        variables = {}
        for role in ("User", "Host", "Process"):
            row = tk.Frame(body, bg=BG)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=role, bg=BG, fg=INK, width=9, anchor="w").pack(side="left")
            variable = tk.StringVar(value=self.context.get(role, NONE))
            variables[role] = variable
            ttk.Combobox(
                row, textvariable=variable, values=[NONE, *self.current.fields], state="readonly"
            ).pack(side="right", fill="x", expand=True)

        def apply():
            self.context = {role: var.get() for role, var in variables.items() if var.get() != NONE}
            self._changed()
            self.context_label.configure(
                text=(
                    f"{len(self.context)} context fields mapped"
                    if self.context
                    else "No context mapped"
                )
            )
            window.destroy()

        ttk.Button(body, text="Apply", command=apply).pack(anchor="e", pady=12)

    def _export_alerts(self):
        if self.busy or not self.result:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export alerts",
            initialfile="surge.alerts.jsonl",
            defaultextension=".jsonl",
            filetypes=[("Alerts", "*.jsonl")],
        )
        if path:
            current, reference, config, result = (
                self.current,
                self.reference,
                self.run_config,
                self.result,
            )
            minimum = self.minimum_priority.get()
            self._job(
                "alerts",
                lambda: workflow.export_alerts(path, current, reference, config, result, minimum),
            )

    def _run(self):
        if not self.current:
            messagebox.showinfo("Choose data", "Import incoming data first.", parent=self)
            return
        self._sync_data_controls()
        if self.mapping_report and self.mapping_report.blocked:
            self.show_page("Data")
            self.status.set("Fix the marked fields before analyzing.")
            return
        try:
            config = self.config()
        except ValueError:
            messagebox.showerror(
                "Check threshold",
                "Enter a numeric deviation threshold between 1 and 100.",
                parent=self,
            )
            return
        current, reference = self.current, self.reference
        self._job("analysis", lambda: (engine.analyze(current, reference, config), config))

    def _rules_dialog(self):
        if self.busy:
            return
        if not self.current:
            messagebox.showinfo("Choose data", "Import data before defining rules.", parent=self)
            return
        window = tk.Toplevel(self)
        window.title("Surge — Rules")
        window.geometry("860x620")
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()
        body = tk.Frame(window, bg=BG, padx=18, pady=18)
        body.pack(fill="both", expand=True)
        self._label(body, "Match a field to a value.")
        self._label(
            body, "CSV equality uses Text. Numeric comparisons accept numbers stored as text."
        )
        pending = json.loads(json.dumps(self.rules))
        table = self._table(body, ["Name", "Field", "Condition", "Value", "Priority"], height=5)
        operations = {
            "greater than": "gt",
            "at least": "ge",
            "less than": "lt",
            "at most": "le",
            "equals": "eq",
            "does not equal": "ne",
        }
        labels = {v: k for k, v in operations.items()}

        def refresh():
            table.delete(*table.get_children())
            for i, rule in enumerate(pending):
                table.insert(
                    "",
                    "end",
                    iid=str(i),
                    values=(
                        rule["name"],
                        rule["field"],
                        labels[rule["op"]],
                        json.dumps(rule["value"], ensure_ascii=False),
                        rule.get("priority", "Notice"),
                    ),
                )

        refresh()
        form = tk.Frame(body, bg=BG)
        form.pack(fill="x", pady=12)
        name, field = tk.StringVar(), tk.StringVar(value=self.current.fields[0])
        operation, value, kind = (
            tk.StringVar(value="greater than"),
            tk.StringVar(),
            tk.StringVar(value="Number"),
        )
        priority = tk.StringVar(value="Notice")
        widgets = [
            ("Rule name", ttk.Entry(form, textvariable=name)),
            (
                "Field",
                ttk.Combobox(
                    form, textvariable=field, values=self.current.fields, state="readonly"
                ),
            ),
            (
                "Condition",
                ttk.Combobox(
                    form, textvariable=operation, values=list(operations), state="readonly"
                ),
            ),
            (
                "Value type",
                ttk.Combobox(
                    form, textvariable=kind, values=["Number", "Text", "Boolean"], state="readonly"
                ),
            ),
            ("Value", ttk.Entry(form, textvariable=value)),
            (
                "Priority",
                ttk.Combobox(
                    form, textvariable=priority, values=engine.PRIORITIES, state="readonly"
                ),
            ),
        ]
        for i, (title, widget) in enumerate(widgets):
            tk.Label(form, text=title, bg=BG, fg=INK, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(0, 14), pady=4
            )
            widget.grid(row=i, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        def add():
            try:
                target = value.get()
                if kind.get() == "Number":
                    target = engine.number(target)
                    if target is None:
                        raise ValueError("Enter a finite number.")
                elif kind.get() == "Boolean":
                    if target.lower() not in ("true", "false"):
                        raise ValueError("Enter true or false for a Boolean value.")
                    target = target.lower() == "true"
                candidate = pending + [
                    {
                        "name": name.get(),
                        "field": field.get(),
                        "op": operations[operation.get()],
                        "value": target,
                    }
                ]
                if priority.get() != "Notice":
                    candidate[-1]["priority"] = priority.get()
                config = self.config()
                config["rules"] = candidate
                config["features"] = []
                engine.validate_config(config, self.current, self.reference)
                pending[:] = candidate
                refresh()
                name.set("")
                value.set("")
            except (ValueError, TypeError) as exc:
                messagebox.showerror("Check rules", str(exc), parent=window)

        def remove():
            for i in sorted((int(i) for i in table.selection()), reverse=True):
                del pending[i]
            refresh()

        def apply():
            self.rules = pending
            self._changed()
            self.rule_label.configure(text=f"{len(pending)} rules")
            window.destroy()

        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x")
        ttk.Button(actions, text="Add rule", command=add).pack(side="left")
        ttk.Button(actions, text="Remove selected", command=remove).pack(side="left", padx=8)
        ttk.Button(actions, text="Apply rules", command=apply, style="Accent.TButton").pack(
            side="right"
        )

    def _search_changed(self, *_):
        if self._search_timer is not None:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(150, self._render_findings)

    def _focus_search(self, _=None):
        if not self.result:
            self.show_page("Data")
            return "break"
        self.show_page("Findings")
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")
        return "break"

    def _clear_search(self, _=None):
        self.search.set("")
        self._render_findings()
        self.search_entry.focus_set()
        return "break"

    def _render_findings(self, reveal_row=None):
        if self._search_timer is not None:
            self.after_cancel(self._search_timer)
            self._search_timer = None
        previous_selection = self.findings.selection()
        self._chart_reveal = reveal_row
        self.findings.delete(*self.findings.get_children())
        if not self.result:
            self._search_result = None
            self._search_index = {}
            self.filter_note.configure(
                text="Priority keeps gaps visible. Search filters the list; exports use priority.",
                fg=MUTED,
            )
            self.summary_label.configure(text="No results yet")
            self._write(
                self.detail,
                (
                    "Import data and Analyze to inspect findings."
                    if not self.current
                    else "Analyze the loaded data to inspect findings."
                ),
            )
            self._plot()
            return
        summary = self.result["summary"]
        if self.result is not self._search_result:
            self._search_index = investigation.search_index(
                self.current, self.run_config, self.result
            )
            self._search_result = self.result
        query = self.search.get()
        shown = 0
        hidden_gaps = 0
        for record in self.result["records"]:
            if record["row"] != reveal_row and not investigation.matches(
                self._search_index[record["row"]], query
            ):
                hidden_gaps += bool(record["gaps"])
                continue
            if record["row"] != reveal_row and not workflow.visible(
                record, self.run_config, self.minimum_priority.get(), self.only_leads.get()
            ):
                continue
            shown += 1
            reason = (
                "; ".join(e.get("name", e["field"]) for e in record["evidence"])
                or "; ".join(record["gaps"])
                or "No configured condition matched"
            )
            priority = workflow.priority(record, self.run_config)
            self.findings.insert(
                "",
                "end",
                iid=str(record["row"]),
                tags=(priority or record["status"],),
                values=(record["row"], priority or "—", record["status"], reason),
            )
        self.summary_label.configure(
            text=f"{shown:,} shown / {summary['total']:,}   ·   All: {summary['Review']:,} need review · {summary['Unknown']:,} unknown"
        )
        self.filter_note.configure(
            text=(
                f"{hidden_gaps:,} {'record' if hidden_gaps == 1 else 'records'} with gaps hidden by search. Clear to see them. "
                if hidden_gaps
                else "Priority keeps gaps visible. "
            )
            + "Search filters the list; exports use priority.",
            fg=AMBER if hidden_gaps else MUTED,
        )
        children = self.findings.get_children()
        if children:
            self.findings.selection_set(
                str(reveal_row)
                if reveal_row is not None
                else (
                    previous_selection[0]
                    if previous_selection and previous_selection[0] in children
                    else children[0]
                )
            )
            self.findings.see(self.findings.selection()[0])
            self._inspect()
        else:
            if query.strip():
                self._write(
                    self.detail,
                    "No records match this search and filters.\n\nClear search or adjust Findings only and Priority. The full case is unchanged.",
                )
            elif summary["Review"] == 0 and summary["Unknown"] == 0:
                self._write(
                    self.detail,
                    "No configured condition matched.\n\nThis does not establish that the data is safe. Clear Findings only to inspect the records.",
                )
            else:
                self._write(
                    self.detail,
                    "No records match these filters.\n\nChoose All priority and clear Findings only to inspect all records.",
                )
        self._plot()

    def _inspect(self, *_):
        if not self.result or not self.findings.selection():
            return
        row = int(self.findings.selection()[0])
        record = self.result["records"][row - 1]
        lines = []

        def add(text="", tag=""):
            lines.append((text, tag))

        if not record["evidence"]:
            add(
                "Cannot fully assess this record."
                if record["gaps"]
                else "No configured condition matched."
            )
            add()
        groups = {}
        for item in record["evidence"]:
            groups.setdefault(item["field"], []).append(item)
        field = chart.signal(record)
        if field is not None and field not in groups:
            # A chart point may have no finding; show its measurement without
            # presenting a below-threshold value as a matched condition.
            groups[field] = [
                {
                    "kind": "measurement",
                    "score": record["scores"][field],
                    "threshold": self.run_config["threshold"],
                    **engine.profile_for_record(self.result, record, field),
                }
            ]
        original = self.current.rows[row - 1]
        for field, items in groups.items():
            add(f"{field}: {json.dumps(original[field], ensure_ascii=False)}", "value")
            for item in items:
                if item["kind"] == "deviation":
                    add(
                        f"Deviation: {item['score']:.2f}  ·  Review at: {item['threshold']:g}",
                        "evidence",
                    )
                    add(f"Reference median: {item['reference_center']:g}", "value")
                    if self.show_details.get():
                        add(
                            f"Used as number: {item['value']:g} · Scale: {item['scale']:g}", "value"
                        )
                        add(f"Method: {item['method']}", "muted")
                elif item["kind"] == "measurement":
                    add(
                        f"Deviation: {item['score']:.2f}  ·  Below review at: {item['threshold']:g}",
                        "muted",
                    )
                    add(f"Reference median: {item['center']:g}", "value")
                    if self.show_details.get():
                        add(f"Scale: {item['scale']:g} · Method: {item['method']}", "muted")
                else:
                    add(f"Matched: {item['name']}", "evidence")
                    add(
                        f"Condition: {comparison.OPERATORS[item['operator']]} {json.dumps(item['expected'], ensure_ascii=False)}"
                    )
            add()
        if record["scores"]:
            if record.get("reference_group"):
                group = record["reference_group"]
                add(
                    f"Reference group: {json.dumps(dict(zip(group['fields'], group['values'])), ensure_ascii=False)} · {group['mode']} · {group['reference_rows']} reference records",
                    "muted",
                )
            add("A reference median is not a safe limit.", "muted")
            if self.show_details.get():
                add("Deviation = distance from the median / scale.", "muted")
                add(f"Reference: {self.reference.name}", "muted")
                add(f"Reference SHA-256: {self.reference.digest}", "value")
            add()
        if record["gaps"]:
            for gap in record["gaps"]:
                add(f"Check: {gap}", "gap")
            add()
        add(
            f"Result: {record['status']}  ·  Priority: {workflow.priority(record, self.run_config) or 'None'}"
        )
        add(f"Record: {row}  ·  ID: {record['event_id']}", "value")
        add(f"Session: {record['session']}", "value")
        add(f"Time: {time_label(record, self.run_config, self.current.rows[row - 1])}", "value")
        for role, item in workflow.context_values(
            self.current.rows[row - 1], self.run_config
        ).items():
            add(
                f"{role}: {json.dumps(item['value'], ensure_ascii=False) if item['value'] is not None else 'Unavailable'} (from {item['field']})"
            )
        add(f"Source: {self.current.name}", "muted")
        add(f"SHA-256: {self.current.digest[:12]}… · source record {row}", "muted")
        if self.show_values.get():
            add()
            add(f"Source SHA-256: {self.current.digest}", "value")
            for field, value in self.current.rows[row - 1].items():
                add(f"{field}: {json.dumps(value, ensure_ascii=False)}", "value")
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        for text, tag in lines:
            self.detail.insert("end", text + "\n", (tag,) if tag else ())
        self.detail.configure(state="disabled")
        self.detail.yview_moveto(0)
        self._plot()

    def _plot(self):
        canvas = self.timeline
        canvas.delete("all")
        self._chart_points = []
        self.chart_readout.configure(text="")
        self.chart_return.pack_forget()
        if not self.result or not self.run_config["features"]:
            self.chart_frame.pack_forget()
            return
        self.chart_frame.pack(side="bottom", fill="x", pady=(12, 0), before=self.findings.master)
        width = max(canvas.winfo_width(), 180)
        self.chart_readout.configure(wraplength=width - 24)
        threshold = self.run_config["threshold"]
        records = self.result["records"]
        self._chart_points = chart.points(records, width, threshold)
        if not self._chart_points:
            canvas.create_text(12, 45, text="No numeric values to plot.", anchor="w", fill=MUTED)
            return
        canvas.create_text(
            12,
            12,
            text="Max deviation / threshold · capped at 2×",
            anchor="w",
            fill=MUTED,
            font=("Consolas", 9),
        )
        canvas.create_line(58, 54, width - 18, 54, fill=LINE, dash=(4, 3))
        canvas.create_text(12, 26, text="2×", anchor="w", fill=MUTED)
        canvas.create_text(12, 54, text="1×", anchor="w", fill=MUTED)
        canvas.create_text(12, 82, text="0", anchor="w", fill=MUTED)
        for point in self._chart_points:
            color = ACCENT if point.score < threshold else AMBER
            canvas.create_line(point.x, chart.BASE_Y, point.x, point.y, fill=color)
            canvas.create_oval(
                point.x - 2, point.y - 2, point.x + 2, point.y + 2, fill=color, outline=""
            )
        if self.findings.selection():
            row = int(self.findings.selection()[0])
            record = records[row - 1]
            x = chart.x_for_row(row, len(records), width)
            canvas.create_line(x, 23, x, 86, fill=MUTED, dash=(2, 3))
            field = chart.signal(record)
            suffix = " · outside filters" if row == self._chart_reveal else ""
            text = f"Record {row}{suffix}"
            if field is not None:
                raw = json.dumps(self.current.rows[row - 1][field], ensure_ascii=False)
                score = record["scores"][field]
                shown_raw = raw if len(raw) <= 100 else raw[:97] + "… (full value in inspector)"
                text += f" · {field}: {shown_raw}\nDeviation: {score!r}"
                y = chart.BASE_Y - min(score / threshold, 2) * 28
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, outline=INK, width=2)
                peak = next((p for p in self._chart_points if p.row == row), None)
                if peak and peak.count > 1:
                    text += f" · peak of {peak.count} records in this column"
                if peak is None:
                    self._chart_points.append(chart.Point(row, field, score, x, y))
            else:
                text += " · No numeric value available"
            self.chart_readout.configure(text=text)
        else:
            self.chart_readout.configure(text="Click a point to inspect it.")
        if self._chart_reveal is not None:
            self.chart_return.pack(anchor="w", padx=12, pady=(0, 4))
        canvas.create_text(
            width / 2,
            101,
            text="All records in source order · click / ← →",
            fill=MUTED,
            font=("Consolas", 9),
        )

    def _chart_click(self, event):
        if not self.result:
            return
        point = chart.hit(self._chart_points, event.x, event.y)
        if point is not None:
            self.timeline.focus_set()
            self._select_chart_record(point.row)

    def _select_chart_record(self, row):
        record = self.result["records"][row - 1]
        visible = investigation.matches(
            self._search_index[row], self.search.get()
        ) and workflow.visible(
            record, self.run_config, self.minimum_priority.get(), self.only_leads.get()
        )
        self._render_findings(reveal_row=None if visible else row)
        self.findings.selection_set(str(row))
        self.findings.focus(str(row))
        self.findings.see(str(row))
        self._inspect()

    def _chart_step(self, direction):
        if not self.result or not self.findings.selection():
            return "break"
        row = int(self.findings.selection()[0])
        rows = [r["row"] for r in self.result["records"] if r["scores"]]
        candidates = [r for r in rows if r > row] if direction > 0 else [r for r in rows if r < row]
        if candidates:
            self._select_chart_record(candidates[0] if direction > 0 else candidates[-1])
        return "break"

    def _render_health(self):
        summary = self.result["summary"]
        lines = [
            f"Data: {self.current.name}",
            f"Fingerprint (SHA-256): {self.current.digest}",
            f"Reference: {self.reference.name if self.reference else 'None'}",
        ]
        if self.reference:
            lines.append(f"Reference fingerprint (SHA-256): {self.reference.digest}")
        lines.extend(
            [
                "",
                f"Records: {summary['total']:,}",
                f"Needs review: {summary['Review']:,}",
                f"Unknown: {summary['Unknown']:,}",
                f"No finding: {summary['No finding']:,}",
                f"Records with gaps: {summary['rows_with_gaps']:,}",
                "",
                *self._settings_lines(self.run_config),
            ]
        )
        for field, profile in self.result["profiles"].items():
            lines.extend(
                [
                    "",
                    f"{field}: median {profile['center']:g}; scale {profile['scale']:g}.",
                    f"Method: {profile['method']}. Valid reference values: {profile['valid_reference_rows']}; missing: {profile['missing_reference_rows']}.",
                ]
            )
        lines.extend(
            [
                "",
                "Constant references use 1% of the absolute median as scale, with a 1e-9 minimum.",
                "Deviation = distance from the median / scale. The threshold sets when to flag it.",
                "",
                f"Engine: {self.result['engine']}",
                "Imported records are unverified claims. Fingerprints do not prove who collected them.",
                "Findings need review. Accuracy has not been measured against independent labels.",
            ]
        )
        self._write(self.health, "\n".join(lines))

    @staticmethod
    def _settings_lines(config):
        lines = [
            f"Values: {', '.join(config['features']) or 'None'}",
            f"Deviation threshold: {config['threshold']:g}",
            f"Session: {config['session'] or NONE}; record ID: {config['event_id'] or NONE}",
            f"Time: {config['time'] or NONE}; format: {config['time_format']}",
        ]
        operators = {"gt": ">", "ge": ">=", "lt": "<", "le": "<=", "eq": "=", "ne": "!="}
        lines.extend(
            f"Rule {r['name']}: {r['field']} {operators[r['op']]} {json.dumps(r['value'], ensure_ascii=False)}; priority {r.get('priority', 'Notice')}"
            for r in config["rules"]
        )
        lines.extend(f"{role}: from {field}" for role, field in config.get("context", {}).items())
        return lines

    def _save(self):
        if self.busy or not self.result:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save a new evidence case",
            defaultextension=".json",
            initialfile="investigation.case.json",
            filetypes=[("Evidence case", "*.json")],
        )
        if path:
            current, reference, config, result = (
                self.current,
                self.reference,
                self.run_config,
                self.result,
            )
            self._job("save", lambda: engine.save_case(path, current, reference, config, result))

    def _open(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self, title="Open evidence case", filetypes=[("Evidence case", "*.json")]
        )
        if path:
            self._job("open", lambda: engine.open_case(path))

    def _compare(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            parent=self, title="Choose comparison case", filetypes=[("Evidence case", "*.json")]
        )
        if path:
            self._job("compare", lambda: engine.open_case(path))

    def _render_comparison(self):
        selected = self.changed_list.selection()
        self._clear_comparison()
        if not self.result:
            self.comparison_note.set("Analyze the current data to compare a saved case.")
            return
        if not self.previous:
            self.comparison_note.set("Choose a saved case to compare.")
            return
        current = (self.current, self.reference, self.run_config, self.result)
        note, rows = comparison.rows(current, self.previous)
        changes = comparison.changed_records(current, self.previous)
        self.comparison_note.set(note)
        self.changed_records_button.configure(
            text=f"Changed records ({len(changes):,})", state="normal" if changes else "disabled"
        )
        if not changes:
            self.compare_records = False
        self.settings_button.configure(
            style="TButton" if self.compare_records else "Accent.TButton"
        )
        self.changed_records_button.configure(
            style="Accent.TButton" if self.compare_records else "TButton"
        )
        if self.compare_records:
            # Keep unchanged observed values visible beside changed decisions.
            self.changes_filter.configure(state="disabled")
            self.changes_filter.pack_forget()
            self.changed_list_frame.pack(side="left", fill="y", padx=(0, 8), before=self.comparison)
            for row, reason in changes:
                kinds = reason.split(", ")
                short = kinds[0] if len(kinds) == 1 else f"{kinds[0]} +{len(kinds) - 1}"
                self.changed_list.insert("", "end", iid=str(row), values=(row, short))
            row = (
                selected[0]
                if selected and self.changed_list.exists(selected[0])
                else str(changes[0][0])
            )
            self.changed_list.selection_set(row)
            self.changed_list.see(row)
            self._inspect_comparison()
        else:
            self.comparison.show(
                [row for row in rows if row.changed or not self.differences_only.get()],
                self._comparison_sources(),
            )

    def _clear_comparison(self):
        self.comparison.clear()
        self.changed_list.delete(*self.changed_list.get_children())
        self.changed_list_frame.pack_forget()
        self.changed_records_button.configure(
            text="Changed records", state="disabled", style="TButton"
        )
        self.changes_filter.configure(state="normal")
        self.changes_filter.pack(side="left", padx=16)

    def _comparison_sources(self):
        return (
            source_label(self.current, self.reference),
            source_label(self.previous[0], self.previous[1]),
        )

    def _comparison_mode(self, records):
        self.compare_records = records
        self._render_comparison()

    def _inspect_comparison(self, *_):
        if (
            not self.compare_records
            or not self.result
            or not self.previous
            or not self.changed_list.selection()
        ):
            return
        current = (self.current, self.reference, self.run_config, self.result)
        if not comparison.paired(current, self.previous):
            return
        row = int(self.changed_list.selection()[0])
        self.comparison.show(
            comparison.record_rows(current, self.previous, row), self._comparison_sources()
        )


if __name__ == "__main__":
    Workbench().mainloop()
