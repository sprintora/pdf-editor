"""Creates the Microsoft Store tile/icon images from static/logo.png.
Run:  python store/make_assets.py      (the finished images are already included)"""
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "store", "assets")
LISTING = os.path.join(ROOT, "store", "listing")
os.makedirs(OUT, exist_ok=True)
os.makedirs(LISTING, exist_ok=True)

logo = Image.open(os.path.join(ROOT, "static", "logo.png")).convert("RGBA")      # full logo, 512 px
pictogram = logo.crop((102, 29, 408, 335))                                         # document + pencil only
NAVY = logo.getpixel((256, 40))[:3]                                                # background colour of the logo


def square(img, size):
    return img.resize((size, size), Image.LANCZOS)


def on_canvas(img, size_wh, fill, inner):
    canvas = Image.new("RGBA", size_wh, fill)
    pic = img.resize((inner, inner), Image.LANCZOS)
    canvas.alpha_composite(pic, ((size_wh[0] - inner) // 2, (size_wh[1] - inner) // 2))
    return canvas


def save(img, name):
    img.save(os.path.join(OUT, name), optimize=True)


# name, base size; every logo also gets a 200% version
for name, size in [("Square150x150Logo", 150), ("SmallTile", 71), ("LargeTile", 310), ("StoreLogo", 50)]:
    save(square(logo, size), f"{name}.png")
    save(square(logo, size * 2), f"{name}.scale-200.png")

# app icon (taskbar, Start list, title bar): logo with transparent corners
save(square(logo, 44), "Square44x44Logo.png")
save(square(logo, 88), "Square44x44Logo.scale-200.png")
for target in (16, 24, 32, 48, 256):
    save(square(logo, target), f"Square44x44Logo.targetsize-{target}.png")
    save(square(logo, target), f"Square44x44Logo.altform-unplated_targetsize-{target}.png")

# wide tile: pictogram on the logo's navy background
save(on_canvas(pictogram, (310, 150), NAVY + (255,), 130), "Wide310x150Logo.png")
save(on_canvas(pictogram, (620, 300), NAVY + (255,), 260), "Wide310x150Logo.scale-200.png")

# Partner Center store-listing images
square(logo, 300).save(os.path.join(LISTING, "store_icon_300x300.png"), optimize=True)
big = Image.new("RGBA", (1080, 1080), (255, 255, 255, 0))
big.alpha_composite(logo.resize((1080, 1080), Image.LANCZOS))
big.save(os.path.join(LISTING, "store_icon_1080x1080.png"), optimize=True)
print("assets written to", OUT)
