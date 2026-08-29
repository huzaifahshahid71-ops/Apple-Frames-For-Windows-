from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
PNG = ROOT / "apple_frames_studio_icon.png"
ICO = ROOT / "apple_frames_studio.ico"
SIZE = 1024


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def build_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = rounded_mask(SIZE - 120, 210)

    grad = Image.new("RGBA", (SIZE - 120, SIZE - 120))
    px = grad.load()
    top = (42, 115, 235)
    bottom = (80, 63, 226)
    for y in range(grad.height):
        t = y / max(1, grad.height - 1)
        r = round(top[0] * (1 - t) + bottom[0] * t)
        g = round(top[1] * (1 - t) + bottom[1] * t)
        b = round(top[2] * (1 - t) + bottom[2] * t)
        for x in range(grad.width):
            px[x, y] = (r, g, b, 255)
    img.paste(grad, (60, 60), mask)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle((101, 100, 923, 924), radius=168, outline=(100, 159, 247, 230), width=12)

    mark = (202, 219, 255, 255)
    w = 13
    segments = [
        ((121, 230), (191, 230)), ((121, 230), (121, 301)),
        ((833, 230), (905, 230)), ((905, 230), (905, 301)),
        ((121, 690), (121, 760)), ((121, 760), (191, 760)),
        ((833, 760), (905, 760)), ((905, 690), (905, 760)),
    ]
    for a, b in segments:
        d.line((*a, *b), fill=mark, width=w)

    d.rounded_rectangle((157, 266, 877, 727), radius=108, fill=(239, 243, 255, 255))
    d.rounded_rectangle((184, 293, 850, 701), radius=84, fill=(19, 29, 53, 255))
    d.rounded_rectangle((195, 306, 839, 688), radius=72, outline=(83, 161, 247, 255), width=9)

    d.rounded_rectangle((250, 366, 547, 627), radius=38, fill=(239, 242, 255, 255))
    d.rounded_rectangle((575, 366, 781, 476), radius=32, fill=(190, 204, 244, 255))
    d.rounded_rectangle((575, 505, 781, 627), radius=32, fill=(143, 158, 232, 255))
    return img


def main() -> None:
    icon = build_icon()
    icon.save(PNG, format="PNG", optimize=True)
    icon.save(
        ICO,
        format="ICO",
        sizes=[
            (16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
            (48, 48), (64, 64), (96, 96), (128, 128), (256, 256),
        ],
    )
    print(f"Generated {PNG.name} and {ICO.name}")


if __name__ == "__main__":
    main()
