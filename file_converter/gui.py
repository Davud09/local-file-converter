import queue
import threading
import tkinter as tk
from collections.abc import Iterable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .errors import FileConverterError
from .registry import ConversionRoute
from .service import available_routes, convert_file, create_zip, extract_zip

BACKGROUND = "#090B0D"
SURFACE = "#111417"
SURFACE_RAISED = "#191D21"
SURFACE_HOVER = "#22272C"
BORDER = "#292F34"
INPUT_BACKGROUND = "#0D1012"
TEXT = "#ECEFF1"
MUTED = "#929BA1"
ACCENT = "#C4CDD2"
ACCENT_HOVER = "#D5DCE0"
SUCCESS = "#83C5A1"
ERROR = "#E18C8C"
RESULT_POLL_MS = 200


def default_output_path(
    source: Path, route: ConversionRoute, *, compact_json: bool = False
) -> Path:
    if (route.source_extension, route.target_extension) == (".json", ".json"):
        suffix = ".min.json" if compact_json else ".formatted.json"
        return source.with_name(f"{source.stem}{suffix}")
    return source.with_suffix(route.target_extension)


class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("File Converter")
        self.root.geometry("960x820")
        self.root.minsize(760, 700)
        self.root.configure(bg=BACKGROUND)

        self.routes = available_routes()
        self.route_by_label = {self._route_label(route): route for route in self.routes}
        self.route_by_source = {
            route.source_extension: route for route in reversed(self.routes)
        }
        self.results: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.busy = False
        self.zip_inputs: list[Path] = []
        self.action_buttons: list[tk.Button] = []

        self._configure_styles()
        self._build_window()
        self._poll_results()

    @staticmethod
    def _route_label(route: ConversionRoute) -> str:
        return f"{route.source_extension.upper()}  →  {route.target_extension.upper()}"

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TNotebook",
            background=BACKGROUND,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=BACKGROUND,
            foreground=MUTED,
            padding=(20, 12),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", SURFACE)],
            foreground=[("selected", ACCENT)],
        )
        style.configure(
            "TCombobox",
            fieldbackground=INPUT_BACKGROUND,
            background=SURFACE_RAISED,
            foreground=TEXT,
            arrowcolor=ACCENT,
            padding=10,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", INPUT_BACKGROUND)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", INPUT_BACKGROUND)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=SURFACE_RAISED,
            background=ACCENT,
            bordercolor=BACKGROUND,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=3,
        )

    def _build_window(self) -> None:
        outer = tk.Frame(self.root, bg=BACKGROUND, padx=38, pady=32)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        tk.Label(
            outer,
            text="FILE CONVERTER  /  WORKSPACE",
            bg=BACKGROUND,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            outer,
            text="A more considered way\nto convert files.",
            bg=BACKGROUND,
            fg=TEXT,
            font=("Segoe UI", 27, "bold"),
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(12, 8))
        tk.Label(
            outer,
            text=f"Carefully handled formats  ·  {len(self.routes)} conversion routes",
            bg=BACKGROUND,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=2, column=0, sticky="nw")

        self.tabs = ttk.Notebook(outer)
        self.tabs.grid(row=3, column=0, sticky="nsew", pady=(28, 0))
        self.convert_tab = tk.Frame(self.tabs, bg=BACKGROUND, padx=2, pady=18)
        self.zip_tab = tk.Frame(self.tabs, bg=BACKGROUND, padx=2, pady=18)
        self.tabs.add(self.convert_tab, text="  Convert files  ")
        self.tabs.add(self.zip_tab, text="  ZIP tools  ")
        self._build_convert_tab()
        self._build_zip_tab()

        self.status = tk.StringVar(value="Ready")
        footer = tk.Frame(outer, bg=BACKGROUND)
        footer.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        self.status_label = tk.Label(
            footer,
            textvariable=self.status,
            bg=BACKGROUND,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(
            footer, mode="indeterminate", style="Horizontal.TProgressbar", length=120
        )
        self.progress.grid(row=0, column=1, padx=(12, 0))

    def _card(self, parent: tk.Widget, *, padx: int = 24, pady: int = 22) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=SURFACE,
            padx=padx,
            pady=pady,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, 14))
        return card

    @staticmethod
    def _heading(parent: tk.Widget, text: str, *, row: int = 0) -> None:
        tk.Label(
            parent,
            text=text,
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 15))

    def _build_convert_tab(self) -> None:
        tab = self.convert_tab
        tab.columnconfigure(0, weight=1)
        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.compact_json_var = tk.BooleanVar(value=False)

        route_card = self._card(tab)
        route_card.columnconfigure(0, weight=1)
        self._heading(route_card, "01   CONVERSION")
        self.route_var = tk.StringVar()
        self.route_picker = ttk.Combobox(
            route_card,
            textvariable=self.route_var,
            values=tuple(self.route_by_label),
            state="readonly",
            font=("Segoe UI", 11),
        )
        self.route_picker.grid(row=1, column=0, sticky="ew")
        self.route_picker.bind("<<ComboboxSelected>>", self._on_route_changed)
        self.route_description = tk.Label(
            route_card,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.route_description.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        if self.routes:
            self.route_picker.current(0)

        source_card = self._card(tab)
        source_card.columnconfigure(0, weight=1)
        self._heading(source_card, "02   SOURCE FILE")
        self._path_row(
            source_card,
            self.source_var,
            row=1,
            button_text="Browse",
            command=self._browse_source,
        )
        self.compact_checkbox = tk.Checkbutton(
            source_card,
            text="Compact JSON output",
            variable=self.compact_json_var,
            bg=SURFACE,
            fg=MUTED,
            selectcolor=INPUT_BACKGROUND,
            activebackground=SURFACE_HOVER,
            activeforeground=TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            highlightthickness=0,
        )
        self.compact_checkbox.grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.compact_json_var.trace_add("write", self._on_json_option_changed)
        if self.routes:
            self._on_route_changed()

        output_card = self._card(tab)
        output_card.columnconfigure(0, weight=1)
        self._heading(output_card, "03   DESTINATION")
        self._path_row(
            output_card,
            self.destination_var,
            row=1,
            button_text="Save as",
            command=self._browse_destination,
        )

        action_row = tk.Frame(tab, bg=BACKGROUND)
        action_row.pack(fill="x", pady=(2, 0))
        self.convert_button = tk.Button(
            action_row,
            text="Convert  →",
            command=self._start_conversion,
            bg=ACCENT,
            fg=BACKGROUND,
            activebackground=ACCENT_HOVER,
            activeforeground=BACKGROUND,
            relief="flat",
            padx=27,
            pady=13,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        )
        self.convert_button.pack(side="right")
        self.action_buttons.append(self.convert_button)

    def _path_row(
        self,
        parent: tk.Widget,
        variable: tk.StringVar,
        *,
        row: int,
        button_text: str,
        command: Callable[[], None],
    ) -> None:
        holder = tk.Frame(parent, bg=SURFACE)
        holder.grid(row=row, column=0, sticky="ew")
        holder.columnconfigure(0, weight=1)
        entry = tk.Entry(
            holder,
            textvariable=variable,
            bg=INPUT_BACKGROUND,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        entry.grid(row=0, column=0, sticky="ew", ipady=11, padx=(0, 10))
        button = tk.Button(
            holder,
            text=button_text,
            command=command,
            bg=SURFACE_HOVER,
            fg=TEXT,
            activebackground=BORDER,
            activeforeground=TEXT,
            relief="flat",
            padx=16,
            pady=10,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        button.grid(row=0, column=1)

    def _build_zip_tab(self) -> None:
        self.zip_tabs = ttk.Notebook(self.zip_tab)
        self.zip_tabs.pack(fill="both", expand=True, pady=(0, 14))
        create_tab = tk.Frame(self.zip_tabs, bg=BACKGROUND, padx=4, pady=14)
        extract_tab = tk.Frame(self.zip_tabs, bg=BACKGROUND, padx=4, pady=14)
        self.zip_tabs.add(create_tab, text="  Create ZIP  ")
        self.zip_tabs.add(extract_tab, text="  Extract ZIP  ")

        create_card = self._card(create_tab)
        create_card.columnconfigure(0, weight=1)
        self._heading(create_card, "Add files or folders")
        self.zip_list = tk.Listbox(
            create_card,
            height=8,
            bg=INPUT_BACKGROUND,
            fg=TEXT,
            selectbackground=SURFACE_HOVER,
            selectforeground=ACCENT,
            relief="flat",
            font=("Segoe UI", 9),
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        self.zip_list.grid(row=1, column=0, columnspan=2, sticky="ew")
        controls = tk.Frame(create_card, bg=SURFACE)
        controls.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self._small_button(controls, "Add files", self._add_zip_files).pack(
            side="left", padx=(0, 8)
        )
        self._small_button(controls, "Add folder", self._add_zip_folder).pack(
            side="left", padx=(0, 8)
        )
        self._small_button(controls, "Remove selected", self._remove_zip_input).pack(
            side="left"
        )
        tk.Label(
            create_card,
            text="Archive name",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=3, column=0, sticky="w", pady=(18, 8))
        self.zip_output_var = tk.StringVar()
        self._path_row(
            create_card,
            self.zip_output_var,
            row=4,
            button_text="Save as",
            command=self._browse_zip_output,
        )
        self._small_button(
            create_tab, "Create ZIP archive", self._start_zip_creation, primary=True
        ).pack(anchor="e", pady=(0, 4))

        extract_card = self._card(extract_tab)
        extract_card.columnconfigure(0, weight=1)
        self._heading(extract_card, "Choose an archive and destination")
        self.zip_source_var = tk.StringVar()
        self._path_row(
            extract_card,
            self.zip_source_var,
            row=1,
            button_text="Browse ZIP",
            command=self._browse_zip_source,
        )
        tk.Label(
            extract_card,
            text="Extract to folder",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=2, column=0, sticky="w", pady=(18, 8))
        self.extract_destination_var = tk.StringVar()
        self._path_row(
            extract_card,
            self.extract_destination_var,
            row=3,
            button_text="Choose folder",
            command=self._browse_extract_destination,
        )
        self._small_button(
            extract_tab, "Extract ZIP", self._start_zip_extraction, primary=True
        ).pack(anchor="e", pady=(0, 4))

    def _small_button(
        self,
        parent: tk.Widget,
        text: str,
        command: Callable[[], None],
        *,
        primary: bool = False,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if primary else SURFACE_HOVER,
            fg=BACKGROUND if primary else TEXT,
            activebackground=ACCENT_HOVER if primary else BORDER,
            activeforeground=BACKGROUND if primary else TEXT,
            relief="flat",
            padx=14,
            pady=9,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        if primary:
            self.action_buttons.append(button)
        return button

    def _selected_route(self) -> ConversionRoute:
        return self.route_by_label[self.route_var.get()]

    def _on_route_changed(self, _event: tk.Event | None = None) -> None:
        route = self._selected_route()
        self.route_description.configure(text=route.description)
        is_json = route.target_extension == ".json"
        self.compact_checkbox.configure(state=tk.NORMAL if is_json else tk.DISABLED)
        if not is_json:
            self.compact_json_var.set(False)
        self._update_destination()

    def _on_json_option_changed(self, *_args: object) -> None:
        if not hasattr(self, "route_by_label") or not self.routes:
            return
        current = self._selected_route()
        if current.target_extension != ".json":
            return
        self._update_destination()

    def _browse_source(self) -> None:
        route = self._selected_route()
        source = filedialog.askopenfilename(
            title="Choose a file to convert",
            filetypes=[
                (f"{route.source_extension.upper()} files", f"*{route.source_extension}"),
                ("All files", "*.*"),
            ],
        )
        if not source:
            return
        self.source_var.set(source)
        path = Path(source)
        matching_route = self.route_by_source.get(path.suffix.lower())
        if matching_route is not None:
            self.route_var.set(self._route_label(matching_route))
            self._on_route_changed()
        self._update_destination()

    def _update_destination(self) -> None:
        source = self.source_var.get().strip()
        if not source:
            return
        route = self._selected_route()
        self.destination_var.set(
            str(
                default_output_path(
                    Path(source), route, compact_json=self.compact_json_var.get()
                )
            )
        )

    def _browse_destination(self) -> None:
        route = self._selected_route()
        current = self.destination_var.get().strip()
        if not current:
            self._update_destination()
            current = self.destination_var.get().strip()
        destination = filedialog.asksaveasfilename(
            title="Save converted file",
            initialfile=Path(current).name if current else "",
            initialdir=str(Path(current).parent) if current else None,
            defaultextension=route.target_extension,
            filetypes=[
                (f"{route.target_extension.upper()} files", f"*{route.target_extension}"),
                ("All files", "*.*"),
            ],
        )
        if destination:
            self.destination_var.set(destination)

    def _start_conversion(self) -> None:
        source = self.source_var.get().strip()
        destination = self.destination_var.get().strip()
        if not source or not destination:
            messagebox.showwarning(
                "Choose files", "Select an input file and output location first."
            )
            return
        compact_json = self.compact_json_var.get()
        self._start_background(
            lambda: convert_file(
                Path(source),
                Path(destination),
                compact_json=compact_json,
            ),
            f"Converted successfully: {Path(destination).name}",
        )

    def _add_zip_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Choose files to add")
        self._add_zip_paths(Path(path) for path in paths)

    def _add_zip_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose a folder to add")
        if path:
            self._add_zip_paths([Path(path)])

    def _add_zip_paths(self, paths: Iterable[Path]) -> None:
        for path in paths:
            if path not in self.zip_inputs:
                self.zip_inputs.append(path)
                self.zip_list.insert("end", str(path))
        if self.zip_inputs and not self.zip_output_var.get().strip():
            first = self.zip_inputs[0]
            self.zip_output_var.set(str(first.parent / "archive.zip"))

    def _remove_zip_input(self) -> None:
        selected = self.zip_list.curselection()
        for index in reversed(selected):
            self.zip_list.delete(index)
            del self.zip_inputs[index]

    def _browse_zip_output(self) -> None:
        destination = filedialog.asksaveasfilename(
            title="Save ZIP archive",
            defaultextension=".zip",
            filetypes=[("ZIP archives", "*.zip")],
        )
        if destination:
            self.zip_output_var.set(destination)

    def _start_zip_creation(self) -> None:
        destination = self.zip_output_var.get().strip()
        if not self.zip_inputs or not destination:
            messagebox.showwarning(
                "Choose files", "Add at least one file or folder and choose an archive name."
            )
            return
        self._start_background(
            lambda: create_zip(Path(destination), list(self.zip_inputs)),
            f"Created archive: {Path(destination).name}",
        )

    def _browse_zip_source(self) -> None:
        source = filedialog.askopenfilename(
            title="Choose a ZIP archive",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
        )
        if source:
            self.zip_source_var.set(source)
            self.extract_destination_var.set(str(Path(source).with_suffix("")))

    def _browse_extract_destination(self) -> None:
        destination = filedialog.askdirectory(title="Choose extraction folder")
        if destination:
            self.extract_destination_var.set(destination)

    def _start_zip_extraction(self) -> None:
        source = self.zip_source_var.get().strip()
        destination = self.extract_destination_var.get().strip()
        if not source or not destination:
            messagebox.showwarning(
                "Choose folders", "Choose a ZIP archive and an extraction folder."
            )
            return
        self._start_background(
            lambda: extract_zip(Path(source), Path(destination)),
            f"Extracted archive to: {Path(destination)}",
        )

    def _start_background(
        self, operation: Callable[[], None], success_message: str
    ) -> None:
        if self.busy:
            return
        self.busy = True
        for button in self.action_buttons:
            button.configure(state="disabled")
        self.progress.start(12)
        self.status.set("Working…")
        self.status_label.configure(fg=MUTED)

        def worker() -> None:
            # Keep file I/O off Tk's event loop; return results through the queue.
            try:
                operation()
            except (FileConverterError, OSError) as error:
                self.results.put((False, str(error)))
            else:
                self.results.put((True, success_message))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_results(self) -> None:
        try:
            succeeded, message = self.results.get_nowait()
        except queue.Empty:
            # Five idle checks per second reduce wakeups while keeping feedback quick.
            self.root.after(RESULT_POLL_MS, self._poll_results)
            return

        self.busy = False
        for button in self.action_buttons:
            button.configure(state="normal")
        self.progress.stop()
        self.status.set(message)
        self.status_label.configure(fg=SUCCESS if succeeded else ERROR)
        if succeeded:
            messagebox.showinfo("Done", message)
        else:
            messagebox.showerror("Could not complete", message)
        self.root.after(RESULT_POLL_MS, self._poll_results)


def main() -> None:
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
