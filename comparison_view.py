"""Aligned, wrapping comparison cells with a shared scroll position."""

import tkinter as tk
from tkinter import ttk


class ComparisonView(tk.Frame):
    def __init__(self, parent, *, background, foreground, muted, line, changed):
        super().__init__(parent, bg=background)
        self.colors = background, foreground, muted, line, changed
        self.cells = []
        self.rows = []
        self.labels = tk.Frame(self, bg=background)
        self.labels.pack(fill="x")
        self.labels.columnconfigure(0, minsize=180)
        self.labels.columnconfigure(1, weight=1, uniform="values")
        self.labels.columnconfigure(2, weight=1, uniform="values")
        self.labels.columnconfigure(3, minsize=88)
        self.source_cells = []
        self.canvas = tk.Canvas(
            self,
            bg=background,
            highlightthickness=1,
            highlightbackground=line,
            highlightcolor=changed,
            takefocus=True,
        )
        self.scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.body = tk.Frame(self.canvas, bg=background)
        self.body.columnconfigure(1, weight=1, uniform="values")
        self.body.columnconfigure(2, weight=1, uniform="values")
        self.body.columnconfigure(0, minsize=180)
        self.body.columnconfigure(3, minsize=72)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind(
            "<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Next>", lambda _: self.canvas.yview_scroll(1, "pages"))
        self.canvas.bind("<Prior>", lambda _: self.canvas.yview_scroll(-1, "pages"))

    def _wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        wrap = max(100, (event.width - 252) // 2 - 28)
        for cell in [*self.cells, *self.source_cells]:
            cell.configure(wraplength=wrap)

    def show(self, rows, sources=("", "")):
        self.rows = list(rows)
        for child in self.body.winfo_children():
            child.destroy()
        self.cells = []
        bg, fg, muted, line, changed = self.colors
        for child in self.labels.winfo_children():
            child.destroy()
        self.source_cells = []
        # Column labels are functional labels, not decorative section titles.
        for column, label in enumerate(("", "Current", "Previous", "")):
            if column in (1, 2) and sources[column - 1]:
                label += "\n" + sources[column - 1]
            cell = tk.Label(
                self.labels,
                text=label,
                bg=bg,
                fg=muted,
                anchor="nw",
                justify="left",
                font=("Consolas", 10),
            )
            cell.grid(row=0, column=column, sticky="nsew", padx=12, pady=(6, 12))
            if column in (1, 2):
                self.source_cells.append(cell)
        if not self.rows:
            tk.Label(
                self.body, text="No differences to show.", bg=bg, fg=muted, font=("Segoe UI", 11)
            ).grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=20)
        for index, row in enumerate(self.rows, 1):
            gridrow = index * 2
            tk.Frame(self.body, bg=line, height=1).grid(
                row=gridrow - 1, column=0, columnspan=4, sticky="ew"
            )
            for column, value in enumerate(
                (row.label, row.current, row.previous, "Changed" if row.changed else "Same")
            ):
                cell = tk.Label(
                    self.body,
                    text=value,
                    bg=bg,
                    fg=changed if row.changed and column else (fg if column in (1, 2) else muted),
                    font=("Consolas", 11 if column in (1, 2) else 10),
                    anchor="nw",
                    justify="left",
                    wraplength=156 if column == 0 else (65 if column == 3 else 260),
                )
                cell.grid(row=gridrow, column=column, sticky="nsew", padx=12, pady=12)
                cell.bind("<MouseWheel>", self._wheel)
                if column in (1, 2):
                    self.cells.append(cell)
        self.canvas.yview_moveto(0)
        self._resize(type("Size", (), {"width": max(self.canvas.winfo_width(), 600)})())

    def clear(self):
        self.rows = []
        self.cells = []
        self.source_cells = []
        for child in self.labels.winfo_children():
            child.destroy()
        for child in self.body.winfo_children():
            child.destroy()
