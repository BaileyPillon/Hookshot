"""Longshot's local mod manager. Standard-library Tk; no network or downloads."""
import argparse
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import longshot_mods as mods


class Manager:
    def __init__(self, window, folder=None):
        self.window, self.folder, self.layers = window, folder, []
        window.title("Longshot — Mods")
        window.geometry("1000x650")
        window.minsize(760, 480)
        style = ttk.Style(window)
        style.configure("Treeview", rowheight=29)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        pane = ttk.Frame(window, padding=20)
        pane.pack(fill="both", expand=True)
        ttk.Label(pane, text="Mods", style="Title.TLabel").pack(anchor="w")
        ttk.Label(pane, text="Enable mods and choose their priority. Changes take effect the next time you start the game.").pack(anchor="w", pady=(5, 16))
        toolbar = ttk.Frame(pane)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Choose mods folder…", command=self.choose).pack(side="left")
        self.path_text = tk.StringVar(value="No folder selected")
        ttk.Label(toolbar, textvariable=self.path_text).pack(side="left", padx=12)
        table = ttk.Frame(pane)
        table.pack(fill="both", expand=True, pady=(16, 12))
        self.tree = ttk.Treeview(table, columns=("state", "name", "files", "status"), show="headings", selectmode="browse")
        for col, title, width in (("state", "State", 70), ("name", "Mod · later rows take priority", 360), ("files", "Files", 70), ("status", "Compatibility", 210)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=60, stretch=col in ("name", "status"))
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        actions = ttk.Frame(pane)
        actions.pack(fill="x")
        self.buttons = []
        for label, callback in (("Enable", lambda: self.change(True)), ("Disable", lambda: self.change(False)),
                                ("Move earlier", lambda: self.move(-1)), ("Move later", lambda: self.move(1))):
            button = ttk.Button(actions, text=label, command=callback, state="disabled")
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="right")
        self.status = tk.StringVar(value="Choose a folder to see its mods.")
        ttk.Label(pane, textvariable=self.status, wraplength=900).pack(anchor="w", pady=(12, 6))
        self.details = tk.Text(pane, height=7, wrap="word", font=("Segoe UI", 10), padx=10, pady=8, state="disabled")
        self.details.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        if folder:
            self.refresh()

    def choose(self):
        chosen = filedialog.askdirectory(title="Choose the experimental game's mods folder", parent=self.window)
        if chosen:
            self.folder = Path(chosen)
            self.refresh()

    def show_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def selected(self, _event=None):
        selection = self.tree.selection()
        for button in self.buttons:
            button.configure(state="normal" if selection else "disabled")
        if selection:
            layer = next(m for m in self.layers if m["name"] == selection[0])
            notes = list(layer["errors"])
            if layer["exefs_unsupported"]:
                notes.append("This mod includes ExeFS patches. Longshot only loads its RomFS files.")
            collisions = [c for c in mods.conflicts(self.layers) if layer["name"] in c["layers"]]
            notes += [f"{c['path']}\n  Winner: {c['winner']}" for c in collisions[:100]]
            self.show_details("\n\n".join(notes) or "No detected file conflicts. In-game compatibility still depends on the mod.")

    def refresh(self, focus=None):
        if not self.folder:
            return
        try:
            self.layers = mods.scan(self.folder)
            self.tree.delete(*self.tree.get_children())
            for layer in self.layers:
                status = "Needs attention" if layer["errors"] else "RomFS only; ExeFS ignored" if layer["exefs_unsupported"] else "No reported mismatch"
                self.tree.insert("", "end", iid=layer["name"], values=("On" if layer["enabled"] else "Off", layer["name"], len(layer["files"]), status))
            self.path_text.set(str(self.folder))
            conflicts = mods.conflicts(self.layers)
            self.status.set(f"{len(self.layers)} mods · {sum(m['enabled'] for m in self.layers)} enabled · {len(conflicts)} overlapping files. The last enabled mod wins each overlap.")
            self.show_details("Select a mod to see compatibility notes and which files overlap." if self.layers else "No mods found. Put each mod in its own folder containing a romfs folder, then refresh.")
            if focus in self.tree.get_children():
                self.tree.selection_set(focus)
                self.tree.see(focus)
            self.selected()
        except (OSError, ValueError) as error:
            self.status.set("The folder could not be read. Choose another folder or fix the reported problem.")
            messagebox.showerror("Could not read mods", str(error), parent=self.window)

    def change(self, enabled):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            mods.set_enabled(self.folder, selected[0], enabled)
            self.refresh(selected[0])
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not change this mod", str(error), parent=self.window)

    def move(self, direction):
        selected = self.tree.selection()
        if not selected:
            return
        names = [m["name"] for m in self.layers]
        i = names.index(selected[0])
        j = i + direction
        if j < 0 or j >= len(names):
            return
        names[i], names[j] = names[j], names[i]
        try:
            mods.set_order(self.folder, names)
            self.refresh(selected[0])
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not change load order", str(error), parent=self.window)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mods", type=Path)
    args = parser.parse_args()
    root = tk.Tk()
    Manager(root, args.mods)
    root.mainloop()


if __name__ == "__main__":
    main()
