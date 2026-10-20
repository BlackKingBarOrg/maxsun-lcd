"""Background service.

- Every image dropped into inbox/ gets a panel-sized copy in ready/.
- The selected image (see library.read_selection) is kept on the LCD.
- With a slideshow on, the selection moves to the next ready/ image every N
  seconds. Picking an image by hand restarts the clock from that image.
- Every few seconds it checks the panel is still there and still in real-time
  mode; after a replug or suspend it falls back to idle and shows "Loading...",
  so the daemon re-initialises it and sends the image again.
- Its state goes to $XDG_RUNTIME_DIR/maxsun-lcd.json for the bar widget.
"""
import json
import logging
import signal
import sys
import time
from pathlib import Path

from PIL import Image
from watchfiles import Change, watch

from . import library as lib
from .device import MODE_IDLE, DeviceNotFound, Lcd

TICK_MS = 500
KEEPALIVE_S = 5

log = logging.getLogger("maxsun-lcd")


class Daemon:
    def __init__(self):
        self.inbox = lib.inbox_dir()
        self.ready = lib.ready_dir()
        self.lcd = None
        self.device = "missing"
        self.error = ""
        self.shown = None  # (name, mtime_ns, colour settings) on the panel
        self.backlight = None  # level last sent; None = send again
        self.checked_at = float("-inf")  # last connect attempt / keep-alive
        # Slideshow clock: restarts whenever the selection or interval changes.
        self.slide_key = None
        self.slide_at = 0.0
        self.status = ""
        self.failed = {}  # inbox path -> mtime_ns that could not be decoded

    # ------------------------------------------------------------ images

    def process(self, src: Path):
        if not (src.is_file() and lib.is_inbox_image(src)):
            return
        dst = self.ready / lib.ready_name(src)
        mtime = src.stat().st_mtime_ns
        if self.failed.get(src) == mtime:
            return  # retried once the file changes, not on every rescan
        if dst.exists() and dst.stat().st_mtime_ns >= mtime:
            return
        try:
            lib.fit_to_panel(src, dst)
        except Exception as e:  # half-copied or not really an image
            log.warning("skip %s: %s", src.name, e)
            self.failed[src] = mtime
            return
        self.failed.pop(src, None)
        log.info("ready: %s -> %s", src.name, dst.name)
        if not (self.ready / lib.read_selection()).is_file():
            lib.write_selection(dst.name)

    def process_all(self):
        for src in sorted(self.inbox.iterdir(), key=lambda p: p.stat().st_mtime):
            self.process(src)

    # ------------------------------------------------------------ device

    def disconnect(self, state, error=""):
        if self.lcd:
            self.lcd.close()
        self.lcd, self.device, self.error, self.shown = None, state, error, None
        self.backlight = None

    def connect(self):
        try:
            lcd = Lcd().open()
        except DeviceNotFound:
            return self.disconnect("missing")
        except PermissionError as e:
            return self.disconnect("no-permission", str(e))
        if lcd.init() is None:
            lcd.close()
            return self.disconnect("error", "no reply to handshake")
        log.info("panel connected")
        self.lcd, self.device, self.error, self.shown = lcd, "connected", "", None

    def check_alive(self):
        reply = self.lcd.handshake()
        if reply is None:
            return self.disconnect("error", "no reply to handshake")
        if reply[20] == MODE_IDLE:
            log.info("panel fell back to idle; re-initialising")
            self.lcd.clear_overlay()
            self.shown = self.backlight = None

    def apply_backlight(self, level):
        if level == self.backlight:
            return
        self.lcd.set_backlight(level)
        self.backlight = level
        log.info("backlight %d", level)

    def show_selection(self, adjust):
        name = lib.read_selection()
        path = self.ready / name
        if not name or not path.is_file():
            return
        colour = {k: v for k, v in adjust.items() if k != "backlight"}
        key = (name, path.stat().st_mtime_ns, tuple(colour.items()))
        if key == self.shown:
            return
        with Image.open(path) as im:
            self.lcd.show(lib.apply_adjust(im, colour))
        if key[:2] != (self.shown or ())[:2]:
            log.info("showing %s", name)
        self.shown = key

    def advance_slideshow(self, now):
        on, seconds = lib.read_slideshow()
        interval, selected = (seconds if on else 0), lib.read_selection()
        if (interval, selected) != self.slide_key:
            self.slide_key, self.slide_at = (interval, selected), now
            return
        if not interval or now - self.slide_at < interval:
            return
        names = lib.ready_images()
        if len(names) < 2:
            return
        nxt = names[(names.index(selected) + 1) % len(names)] if selected in names else names[0]
        lib.write_selection(nxt)
        self.slide_key, self.slide_at = (interval, nxt), now

    def tick(self):
        now = time.monotonic()
        self.advance_slideshow(now)
        try:
            if now - self.checked_at >= KEEPALIVE_S:
                self.checked_at = now
                # Catches files that landed before the watcher started (or
                # any event it missed); unchanged files cost one stat each.
                self.process_all()
                if self.lcd is None:
                    self.connect()
                else:
                    self.check_alive()
            if self.lcd:
                adjust = lib.read_adjust()
                self.apply_backlight(adjust["backlight"])
                self.show_selection(adjust)
        except OSError as e:  # unplugged mid-write, etc.
            log.warning("panel error: %s", e)
            self.disconnect("error", str(e))
        self.write_status()

    def write_status(self):
        rotating, seconds = lib.read_slideshow()
        status = json.dumps({
            "device": self.device,
            "error": self.error,
            "selected": lib.read_selection(),
            "slideshow": rotating,
            "interval": seconds,
            "adjust": lib.read_adjust(),
            "inbox": str(self.inbox),
            "ready": str(self.ready),
        })
        # Ticks are frequent; only touch the file (and wake the bar) on change.
        if status != self.status:
            lib.write_atomic(lib.status_file(), status.encode())
            self.status = status

    # ------------------------------------------------------------ main loop

    def run(self):
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.ready.mkdir(parents=True, exist_ok=True)
        lib.state_dir().mkdir(parents=True, exist_ok=True)
        self.tick()
        for changes in watch(self.inbox, lib.state_dir(), debounce=150,
                             rust_timeout=TICK_MS, yield_on_timeout=True):
            for change, path in changes:
                path = Path(path)
                if change != Change.deleted and path.parent == self.inbox:
                    self.process(path)
            self.tick()


def run():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    daemon = Daemon()
    try:
        daemon.run()
    except KeyboardInterrupt:  # watchfiles turns SIGTERM/SIGINT into this
        pass
    finally:
        daemon.disconnect("missing")
        lib.status_file().unlink(missing_ok=True)
