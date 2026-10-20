"""The image folders and the current selection, shared by the CLI and the daemon.

    <root>/inbox/   images dropped in by the user, left untouched
    <root>/ready/   panel-sized copies (412x960 PNG), one per inbox image

The selection is the file name of one image in ready/, kept in
$XDG_STATE_HOME/maxsun-lcd/selected so it survives reboots. Next to it,
slideshow.json says whether to rotate through ready/ and how often; the
interval is kept while rotation is off so switching back restores it.
adjust.json holds the colour correction applied on the way to the panel
(ready/ files stay untouched) and the hardware backlight level.
"""
import json
import os
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from .device import HEIGHT, WIDTH

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def root_dir():
    return Path(os.environ.get("MAXSUN_LCD_ROOT", Path.home() / "Pictures" / "MaxsunLCD"))


def inbox_dir():
    return root_dir() / "inbox"


def ready_dir():
    return root_dir() / "ready"


def state_dir():
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "maxsun-lcd"


def selection_file():
    return state_dir() / "selected"


def status_file():
    """Daemon status for the bar widget; lives in the runtime dir, gone at logout."""
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "maxsun-lcd.json"


def write_atomic(path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def is_inbox_image(path: Path):
    # Browsers and copy tools write to dotfiles or .part/.crdownload first.
    return not path.name.startswith(".") and path.suffix.lower() in IMAGE_SUFFIXES


def ready_name(src: Path):
    return src.stem + ".png"


def fit_to_panel(src: Path, dst: Path):
    """Center-crop to the panel's aspect ratio, then scale to 412x960."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode != "RGB":
            rgba = im.convert("RGBA")
            im = Image.new("RGB", rgba.size, (0, 0, 0))
            im.paste(rgba, mask=rgba.getchannel("A"))
        out = ImageOps.fit(im, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    tmp = dst.with_name(f".{dst.name}.tmp")
    out.save(tmp, "PNG")
    tmp.replace(dst)


def read_selection():
    try:
        return selection_file().read_text().strip()
    except FileNotFoundError:
        return ""


def write_selection(name: str):
    write_atomic(selection_file(), name.encode() + b"\n")


def ready_images():
    """Newest first, the same order as the bar widget's grid."""
    paths = [p for p in ready_dir().iterdir()
             if not p.name.startswith(".") and p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    return [p.name for p in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)]


DEFAULT_SECONDS = 5


def slideshow_file():
    return state_dir() / "slideshow.json"


def read_slideshow():
    """(rotating, seconds); never set means a fixed image and 5 s."""
    try:
        data = json.loads(slideshow_file().read_text())
        return bool(data.get("on")), max(1, int(data.get("seconds", DEFAULT_SECONDS)))
    except (FileNotFoundError, ValueError, TypeError, AttributeError):
        return False, DEFAULT_SECONDS


def adjust_file():
    return state_dir() / "adjust.json"


# name: (default, min, max). Percentages except hue (degrees) and backlight,
# which is the panel's own 1-10 level (duty cycle = level², so 10 = 100%).
ADJUST_RANGES = {
    "backlight": (10, 1, 10),
    "brightness": (100, 0, 200),
    "contrast": (100, 0, 200),
    "saturation": (100, 0, 200),
    "hue": (0, -180, 180),
    "red": (100, 0, 200),
    "green": (100, 0, 200),
    "blue": (100, 0, 200),
}


def read_adjust():
    try:
        data = json.loads(adjust_file().read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    out = {}
    for name, (default, lo, hi) in ADJUST_RANGES.items():
        try:
            out[name] = max(lo, min(hi, int(data.get(name, default))))
        except (TypeError, ValueError):
            out[name] = default
    return out


def write_adjust(changes):
    """Merge {name: value} into adjust.json; values are clamped to their range."""
    data = read_adjust()
    for name, value in changes.items():
        _, lo, hi = ADJUST_RANGES[name]
        data[name] = max(lo, min(hi, int(value)))
    write_atomic(adjust_file(), json.dumps(data).encode())


def reset_adjust():
    adjust_file().unlink(missing_ok=True)


def apply_adjust(img, adj):
    """Colour-correct an RGB image for the panel; untouched settings cost nothing."""
    img = img.convert("RGB")
    if adj["hue"]:
        shift = round(adj["hue"] / 360 * 256)
        h, s, v = img.convert("HSV").split()
        h = h.point([(x + shift) % 256 for x in range(256)])
        img = Image.merge("HSV", (h, s, v)).convert("RGB")
    for name, enhancer in (("saturation", ImageEnhance.Color),
                           ("contrast", ImageEnhance.Contrast),
                           ("brightness", ImageEnhance.Brightness)):
        if adj[name] != 100:
            img = enhancer(img).enhance(adj[name] / 100)
    gains = (adj["red"], adj["green"], adj["blue"])
    if gains != (100, 100, 100):
        img = Image.merge("RGB", [
            band.point([min(255, round(x * g / 100)) for x in range(256)])
            for band, g in zip(img.split(), gains)
        ])
    return img


def write_slideshow(on=None, seconds=None):
    cur_on, cur_seconds = read_slideshow()
    data = {"on": cur_on if on is None else on,
            "seconds": cur_seconds if seconds is None else max(1, int(seconds))}
    write_atomic(slideshow_file(), json.dumps(data).encode())
