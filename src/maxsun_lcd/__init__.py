import argparse
import os

from PIL import Image, ImageDraw, ImageFont

from .device import HEIGHT, WIDTH, Lcd


def _font(size):
    for path in ("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/noto/NotoSans-Bold.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def test_image():
    """Arrow pointing at the top of the panel, with 'UP' to spot mirroring."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = WIDTH // 2
    d.polygon([(cx, 80), (cx - 170, 330), (cx + 170, 330)], fill=(255, 255, 255))
    d.rectangle([cx - 60, 330, cx + 60, 700], fill=(255, 255, 255))
    d.text((cx, 820), "UP", font=_font(110), fill=(255, 200, 0), anchor="mm")
    return img


def select(name):
    from . import library as lib

    if not (lib.ready_dir() / name).is_file():
        raise SystemExit(f"not in {lib.ready_dir()}: {name}")
    lib.write_selection(name)


def slideshow(value):
    from . import library as lib

    lib.write_slideshow(on=value == "on")


def interval(value):
    from . import library as lib

    if not value.isdigit() or int(value) < 1:
        raise SystemExit("expected whole seconds, at least 1")
    lib.write_slideshow(seconds=int(value))


def adjust(args):
    import json

    from . import library as lib

    if args == ["reset"]:
        return lib.reset_adjust()
    if len(args) % 2:
        raise SystemExit("expected NAME VALUE pairs, or 'reset'")
    changes = {}
    for name, value in zip(args[::2], args[1::2]):
        if name not in lib.ADJUST_RANGES:
            raise SystemExit(f"unknown setting {name}; one of {', '.join(lib.ADJUST_RANGES)}")
        try:
            changes[name] = int(value)
        except ValueError:
            raise SystemExit(f"{name}: expected a whole number, got {value}")
    if changes:
        lib.write_adjust(changes)
    print(json.dumps(lib.read_adjust()))


def main() -> None:
    p = argparse.ArgumentParser(prog="maxsun-lcd", description="MAXSUN onboard LCD tool")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daemon", help="watch the image folders and keep the selection on the panel")
    sel = sub.add_parser("select", help="pick which ready/ image the daemon shows")
    sel.add_argument("name", help="file name inside ready/")
    slide = sub.add_parser("slideshow", help="rotate through ready/ images (on) or keep the selected one (off)")
    slide.add_argument("state", choices=["on", "off"])
    inter = sub.add_parser("interval", help="seconds between slideshow images (default 5)")
    inter.add_argument("seconds")
    adj = sub.add_parser(
        "adjust", help="colour correction and backlight: print, set NAME VALUE..., or reset",
        description="backlight 1-10 (panel hardware); brightness/contrast/saturation/red/green/blue "
                    "0-200 (percent, 100 = unchanged); hue -180..180 (degrees)")
    adj.add_argument("args", nargs="*")
    sub.add_parser("status", help="handshake and print the device status reply")
    sub.add_parser("test", help="show an arrow test pattern (bypasses the daemon)")
    show = sub.add_parser("show", help="show an image file (bypasses the daemon)")
    show.add_argument("image")
    args = p.parse_args()

    if args.cmd == "daemon":
        from .daemon import run
        return run()
    if args.cmd == "select":
        return select(args.name)
    if args.cmd == "slideshow":
        return slideshow(args.state)
    if args.cmd == "interval":
        return interval(args.seconds)
    if args.cmd == "adjust":
        return adjust(args.args)

    with Lcd() as lcd:
        if args.cmd == "status":
            reply = lcd.handshake()
            print(reply.hex(" ") if reply else "(no reply)")
            return
        lcd.init()
        img = test_image() if args.cmd == "test" else Image.open(args.image)
        lcd.show(img)
