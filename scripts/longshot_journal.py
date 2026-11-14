"""Live, read-only adventure companion. No game assets, save parsing or memory writes.

The trail is a record of movement, not a floor plan. Waypoints are the player's
notes, kept separately per launcher profile. Unknown game values stay unknown.
"""
import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hookshot_ctl import Bridge, Failed
from longshot_launcher_core import plain_path

TOKEN = "PouchData.Item_Token_Gold.StockNum"
PIECES = "PouchData.Obj_Heart_Piece.StockNum"
WATCH = [TOKEN, PIECES]
MAX_PINS = 200
STALE_SECONDS = 2.0


def number(value, minimum, maximum):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and minimum <= value <= maximum


def sample_of(message):
    """Accept only bounded samples from the native bridge's OoT event."""
    if not isinstance(message, dict) or message.get("event") != "oot":
        return None
    game = message.get("game")
    if not isinstance(game, dict):
        return None
    scene, position = game.get("map"), game.get("pos")
    if not isinstance(scene, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,63}", scene):
        return None
    if not isinstance(position, list) or len(position) != 3 or not all(number(v, -1e6, 1e6) for v in position):
        return None
    if game.get("age") not in ("child", "adult") or not number(game.get("frame"), 0, 2**53):
        return None
    if game.get("loading") is not False or game.get("event") is not False:
        return None
    result = dict(map=scene, pos=tuple(position), age=game["age"], frame=game["frame"])
    for key, limit in (("life", 1000), ("max_life", 1000), ("rupees", 99999)):
        value = game.get(key)
        result[key] = value if number(value, 0, limit) else None
    facing = game.get("facing")
    result["facing"] = facing % 360 if number(facing, -360, 360) else None
    flags = game.get("flags")
    flags = flags if isinstance(flags, dict) else {}
    for key, flag, limit in (("tokens", TOKEN, 100), ("pieces", PIECES, 3)):
        value = flags.get(flag)
        result[key] = value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= limit else None
    return result


def area_name(scene):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", scene).replace("_", " ")


class Journal:
    def __init__(self):
        self.current = None
        self.received = 0.0
        self.connected = False
        self.trails = {}
        self.feed = deque(maxlen=24)
        self.break_trail = True

    def disconnect(self):
        self.connected = False
        self.current = None
        self.trails.clear()
        self.break_trail = True
        self.feed.clear()

    def ingest(self, message, now=None):
        now = time.monotonic() if now is None else now
        sample = sample_of(message)
        if sample is None:
            self.break_trail = True
            self.received = 0.0
            return False
        previous = self.current
        if previous and sample["frame"] <= previous["frame"]:
            # Repeated samples never refresh the live indicator. A frame rewind
            # is a new process/session and must not generate fictional pickups.
            if sample["frame"] == previous["frame"]:
                return False
            self.disconnect()
            previous = None
        key = (sample["map"], sample["age"])
        same_area = previous and key == (previous["map"], previous["age"])
        continuous = same_area and not self.break_trail and now - self.received <= STALE_SECONDS
        if not same_area:
            self.feed.appendleft("Entered " + area_name(sample["map"]) + " (" + sample["age"] + ")")
        elif continuous:
            for field, label in (("tokens", "Gold Skulltula tokens"), ("pieces", "Heart pieces"), ("max_life", "Maximum health")):
                before, after = previous.get(field), sample.get(field)
                if before is not None and after is not None and after > before:
                    self.feed.appendleft(f"{label}: {after / 4:g} hearts" if field == "max_life" else f"{label}: {after}")
                elif before is not None and after is not None and after < before:
                    self.feed.appendleft("Progress changed; a previous save may have been loaded.")
                    self.break_trail = True
                    continuous = False
                    break
        if key not in self.trails:
            if len(self.trails) >= 8:
                del self.trails[next(iter(self.trails))]
            self.trails[key] = deque(maxlen=1200)
        trail = self.trails[key]
        point = sample["pos"]
        last = previous["pos"] if same_area else None
        distance = math.dist(point, last) if last else 0
        if not continuous or distance > 30 or (last and abs(point[1] - last[1]) > 5):
            if trail and trail[-1] is not None:
                trail.append(None)
        if not trail or trail[-1] is None or math.dist(trail[-1], point) >= 0.5:
            trail.append(point)
        self.current, self.received, self.connected, self.break_trail = sample, now, True, False
        return True

    def live(self, now=None):
        now = time.monotonic() if now is None else now
        return self.connected and not self.break_trail and self.current is not None and now - self.received <= STALE_SECONDS


class Waypoints:
    def __init__(self, path):
        self.path = plain_path(path, directory=False)
        self.items = []
        self.original = None
        if self.path.exists():
            if self.path.stat().st_size > 256 * 1024:
                raise ValueError("Waypoint file is too large; it was left unchanged.")
            self.original = self.path.read_bytes()
            data = json.loads(self.original.decode("utf-8"))
            if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("waypoints"), list):
                raise ValueError("Unrecognized waypoint file; it was left unchanged.")
            if len(data["waypoints"]) > MAX_PINS or not all(self.valid(p) for p in data["waypoints"]):
                raise ValueError("Invalid waypoint data; the file was left unchanged.")
            if len({p["id"] for p in data["waypoints"]}) != len(data["waypoints"]):
                raise ValueError("Duplicate waypoint IDs; the file was left unchanged.")
            self.items = data["waypoints"]

    @staticmethod
    def valid(p):
        return (isinstance(p, dict) and isinstance(p.get("id"), str) and re.fullmatch(r"[a-f0-9]{32}", p["id"])
                and isinstance(p.get("label"), str) and 0 < len(p["label"]) <= 80
                and not any(ord(c) < 32 for c in p["label"])
                and isinstance(p.get("map"), str) and re.fullmatch(r"[A-Za-z0-9_]{1,63}", p["map"])
                and p.get("age") in ("child", "adult") and isinstance(p.get("pos"), list)
                and len(p["pos"]) == 3 and all(number(v, -1e6, 1e6) for v in p["pos"]))

    def replace(self, items):
        plain_path(self.path, directory=False)
        current = self.path.read_bytes() if self.path.exists() else None
        if current != self.original:
            raise ValueError("These waypoints changed in another window. Reopen the journal before editing them.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        plain_path(self.path.parent)
        data = json.dumps(dict(schema=1, waypoints=items), ensure_ascii=False, indent=2)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.items = items
            self.original = self.path.read_bytes()
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def add(self, sample, label):
        item = dict(id=uuid.uuid4().hex, map=sample["map"], age=sample["age"], pos=list(sample["pos"]), label=label.strip())
        if len(self.items) >= MAX_PINS:
            raise ValueError("This profile has 200 waypoints. Remove one before adding another.")
        if not self.valid(item):
            raise ValueError("Use a waypoint name of 1–80 characters on a valid live position.")
        self.replace(self.items + [item])

    def remove(self, identifier):
        self.replace([p for p in self.items if p["id"] != identifier])


class Reader(threading.Thread):
    """One local connection; deliberately sends only a bounded subscription."""
    def __init__(self, endpoint):
        super().__init__(daemon=True)
        self.endpoint, self.messages, self.stop = endpoint, queue.Queue(maxsize=8), threading.Event()

    def publish(self, message):
        # A modal or busy UI must not make a queued old sample look fresh.
        message = dict(message, _received=time.monotonic())
        try:
            self.messages.put_nowait(message)
        except queue.Full:
            try:
                self.messages.get_nowait()
            except queue.Empty:
                pass
            self.messages.put_nowait(message)

    def run(self):
        while not self.stop.is_set():
            bridge = None
            try:
                bridge = Bridge(self.endpoint, timeout=0.5)
                bridge.send(dict(id=1, cmd="subscribe", events=["oot"], every=6, flags=WATCH))
                while not self.stop.is_set():
                    try:
                        message = bridge.line(0.5)
                    except Failed as error:
                        if error.code == 3:
                            continue
                        raise
                    if message is None:
                        break
                    if message.get("id") == 1 and not message.get("ok"):
                        self.publish(dict(error="This game build does not support live tracking. Update the experimental build."))
                        self.stop.wait(2)
                        break
                    if message.get("event") == "oot":
                        self.publish(message)
            except (Failed, OSError, ValueError):
                pass
            finally:
                if bridge:
                    bridge.close()
                self.publish(dict(disconnected=True))
            self.stop.wait(1)


class JournalWindow:
    def __init__(self, window, endpoint, notes, profile="", start_reader=True):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.window, self.journal = window, Journal()
        self.notes = Waypoints(notes)
        self.reader = Reader(endpoint)
        self.error = None
        self.after_id = None
        self.expanded_geometry = "970x710"
        self.compact = tk.BooleanVar(value=False)
        window.title("Adventure Journal — Longshot" + (f" · Profile {profile}" if profile else ""))
        window.geometry("970x710")
        window.minsize(820, 620)
        window.protocol("WM_DELETE_WINDOW", self.close)
        pane = ttk.Frame(window, padding=20)
        pane.pack(fill="both", expand=True)
        top = ttk.Frame(pane)
        top.pack(fill="x")
        ttk.Label(top, text="Adventure Journal", font=("Segoe UI", 20, "bold")).pack(side="left")
        self.on_top = tk.BooleanVar()
        ttk.Checkbutton(top, text="Keep on top", variable=self.on_top,
                        command=lambda: window.attributes("-topmost", self.on_top.get())).pack(side="right")
        ttk.Checkbutton(top, text="Compact", variable=self.compact, command=self.toggle_compact).pack(side="right", padx=10)
        self.status = tk.StringVar(value="Waiting for Longshot. Load a save to begin.")
        ttk.Label(pane, textvariable=self.status, wraplength=880).pack(anchor="w", pady=(6, 18))
        self.stats = tk.StringVar(value="Hearts —     Rupees —     Gold Skulltulas —     Heart pieces —")
        ttk.Label(pane, textvariable=self.stats, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 16))
        self.details = ttk.Frame(pane)
        self.details.pack(fill="both", expand=True)
        body = ttk.Frame(self.details)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)
        self.heading = tk.StringVar(value="Your route")
        ttk.Label(body, textvariable=self.heading, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(body, text="Waypoints in this area", font=("Segoe UI", 13, "bold")).grid(row=0, column=1, sticky="w", padx=(18, 0), pady=(0, 8))
        self.canvas = tk.Canvas(body, background="#152822", highlightthickness=0, width=510, height=330)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _: self.draw())
        side = ttk.Frame(body)
        side.grid(row=1, column=1, sticky="nsew", padx=(18, 0))
        self.list = ttk.Treeview(side, columns=("label", "distance"), show="headings", height=7, selectmode="browse")
        self.list.heading("label", text="Name")
        self.list.heading("distance", text="Distance")
        self.list.column("label", width=155, minwidth=100)
        self.list.column("distance", width=80, minwidth=70, stretch=False)
        self.list.pack(fill="both", expand=True)
        self.list.bind("<<TreeviewSelect>>", lambda _: self.draw())
        self.label = tk.StringVar()
        ttk.Label(side, text="Name the shown spot").pack(anchor="w", pady=(12, 4))
        self.entry = ttk.Entry(side, textvariable=self.label)
        self.entry.pack(fill="x")
        self.entry.bind("<Return>", lambda _: self.mark())
        row = ttk.Frame(side)
        row.pack(fill="x", pady=(8, 0))
        self.mark_button = ttk.Button(row, text="Mark shown spot", command=self.mark, state="disabled")
        self.mark_button.pack(side="left")
        ttk.Button(row, text="Remove selected", command=self.remove).pack(side="right")
        ttk.Label(body, text="Trail only, not a floor plan. North is up. Breaks mark transitions or long jumps.",
                  wraplength=500).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.distance = tk.StringVar(value="Select a waypoint to see its direction.")
        ttk.Label(body, textvariable=self.distance, wraplength=310).grid(row=2, column=1, sticky="w", padx=(18, 0), pady=(8, 0))
        ttk.Label(self.details, text="This session", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(18, 6))
        self.feed = tk.StringVar(value="Area visits and collection changes will appear here.")
        ttk.Label(self.details, textvariable=self.feed, justify="left", wraplength=870).pack(anchor="w")
        ttk.Label(self.details, text="Waypoints are personal notes for this profile. Live counters do not mark individual collectible locations.",
                  wraplength=880).pack(anchor="w", pady=(14, 0))
        if start_reader:
            self.reader.start()
        self.tick()

    def toggle_compact(self):
        if self.compact.get():
            self.expanded_geometry = self.window.geometry()
            self.details.pack_forget()
            self.window.minsize(560, 190)
            self.window.geometry("560x190")
        else:
            self.details.pack(fill="both", expand=True)
            self.window.minsize(820, 620)
            self.window.geometry(self.expanded_geometry)

    def mark(self):
        if not self.journal.connected or not self.journal.current:
            self.status.set("Wait for a gameplay position before marking a spot.")
            return
        try:
            self.notes.add(self.journal.current, self.label.get())
            self.label.set("")
            self.update_rows()
            self.draw()
        except (ValueError, OSError) as error:
            self.messagebox.showerror("Waypoint could not be saved", str(error), parent=self.window)

    def remove(self):
        selected = self.list.selection()
        if not selected:
            return
        if self.messagebox.askyesno("Remove waypoint", "Remove this personal waypoint? Game progress is unchanged.", parent=self.window):
            try:
                self.notes.remove(selected[0])
                self.update_rows()
                self.draw()
            except (OSError, ValueError) as error:
                self.messagebox.showerror("Waypoint could not be removed", str(error), parent=self.window)

    def visible_pins(self):
        current = self.journal.current
        return [p for p in self.notes.items if current and (p["map"], p["age"]) == (current["map"], current["age"])]

    def update_rows(self):
        pins = self.visible_pins()
        identifiers = {p["id"] for p in pins}
        for iid in self.list.get_children():
            if iid not in identifiers:
                self.list.delete(iid)
        current = self.journal.current
        for p in pins:
            values = (p["label"], f"{math.dist(p['pos'], current['pos']):.0f} m")
            if self.list.exists(p["id"]):
                self.list.item(p["id"], values=values)
            else:
                self.list.insert("", "end", iid=p["id"], values=values)

    def draw(self):
        canvas, sample = self.canvas, self.journal.current
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if not sample:
            self.distance.set("Select a waypoint to see its direction.")
            canvas.create_text(width / 2, height / 2, text="Your trail begins when you enter the game.", fill="#e2eee6", width=max(100, width - 40))
            return
        trail = self.journal.trails.get((sample["map"], sample["age"]), [])
        pins = self.visible_pins()
        selected = self.list.selection()
        points = [p for p in trail if p is not None] + [p["pos"] for p in pins] + [sample["pos"]]
        xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
        zmin, zmax = min(p[2] for p in points), max(p[2] for p in points)
        scale = min(max(1, width - 72) / max(30, xmax - xmin), max(1, height - 72) / max(30, zmax - zmin))
        cx, cz = (xmin + xmax) / 2, (zmin + zmax) / 2
        def project(p):
            return width / 2 + (p[0] - cx) * scale, height / 2 + (p[2] - cz) * scale
        prior = None
        for point in trail:
            if point is not None and prior is not None:
                canvas.create_line(*project(prior), *project(point), fill="#80b79c", width=2)
            prior = point
        for pin in pins:
            x, y = project(pin["pos"])
            active = pin["id"] in selected
            canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#efd093" if active else "#b4d0c2", outline="")
            if active:
                canvas.create_line(*project(sample["pos"]), x, y, fill="#efd093", dash=(4, 4))
                canvas.create_text(max(80, min(width - 80, x)), max(16, y - 13), text=pin["label"], fill="#fff1d5", width=150)
                a, b = sample["pos"], pin["pos"]
                bearing = (math.degrees(math.atan2(b[0] - a[0], -(b[2] - a[2]))) + 360) % 360
                direction = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((bearing + 22.5) // 45) % 8]
                distance = math.dist(a, b)
                self.distance.set("You are at this waypoint." if distance < 0.5 else
                                  f"{distance:.0f} m {direction} · height difference {b[1] - a[1]:+.0f} m")
        if not selected:
            self.distance.set("Select a waypoint to see its direction.")
        x, y = project(sample["pos"])
        canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill="#f5faf7", outline="#152822", width=2)
        if sample["facing"] is not None:
            radians = math.radians(sample["facing"])
            canvas.create_line(x, y, x + math.sin(radians) * 18, y + math.cos(radians) * 18, fill="#f5faf7", width=2, arrow="last")
        canvas.create_text(width - 18, 18, text="N", fill="#e2eee6")
        canvas.create_line(18, height - 22, 18 + 10 * scale, height - 22, fill="#c9ddcf", width=2)
        canvas.create_text(18, height - 10, anchor="w", text="10 m", fill="#c9ddcf")

    def tick(self):
        while True:
            try:
                message = self.reader.messages.get_nowait()
            except queue.Empty:
                break
            if message.get("disconnected"):
                self.journal.disconnect()
            elif message.get("error"):
                self.error = message["error"]
            else:
                if self.journal.ingest(message, now=message["_received"]):
                    self.error = None
        sample = self.journal.current
        live = self.journal.live()
        self.mark_button.configure(state="normal" if sample and self.journal.connected else "disabled")
        if sample:
            scene = area_name(sample["map"])
            self.heading.set(scene + " · " + sample["age"].title())
            self.status.set(("Live · " + scene + " · " + sample["age"].title()) if live else
                            "Paused, loading or waiting for a fresh sample. Last position shown.")
            def value(key, scale=1):
                return "—" if sample[key] is None else f"{sample[key] / scale:g}"
            separator = "\n" if self.compact.get() else "     "
            self.stats.set(f"Hearts {value('life', 4)} / {value('max_life', 4)}     Rupees {value('rupees')}" + separator +
                           f"Gold Skulltulas {value('tokens')} / 100     Heart pieces {value('pieces')} / 4")
        else:
            self.status.set(self.error or "Waiting for Longshot. Use Play with journal, then load a save.")
            self.heading.set("Your route")
            self.stats.set("Hearts —     Rupees —" + ("\n" if self.compact.get() else "     ") + "Gold Skulltulas —     Heart pieces —")
        self.feed.set("\n".join(list(self.journal.feed)[:3]) or "Area visits and collection changes will appear here.")
        if not self.compact.get():
            self.update_rows()
            self.draw()
        self.after_id = self.window.after(200, self.tick)

    def close(self):
        self.reader.stop.set()
        if self.after_id is not None:
            self.window.after_cancel(self.after_id)
        self.window.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--notes", required=True, type=Path)
    parser.add_argument("--profile", default="")
    args = parser.parse_args()
    import tkinter as tk
    window = tk.Tk()
    JournalWindow(window, args.socket, args.notes, args.profile)
    window.mainloop()


if __name__ == "__main__":
    main()
