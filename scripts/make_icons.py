"""Regenerate app/static/icons. Needs Pillow: docker run --rm -v "$PWD:/w" -w /w python:3.12-slim sh -c "pip install -q pillow && python scripts/make_icons.py" """
from PIL import Image, ImageDraw

def icon(size: int, path: str) -> None:
    s = 4  # supersample for smooth edges
    W = size * s
    img = Image.new("RGB", (W, W), (232, 89, 12))
    d = ImageDraw.Draw(img)
    for i in range(W):  # subtle vertical gradient
        t = i / W
        d.line([(0, i), (W, i)], fill=(int(245 - 30 * t), int(112 - 40 * t), int(40 - 30 * t)))
    u = W / 100
    white = (255, 255, 255)
    # bowl
    d.chord([20 * u, 30 * u, 80 * u, 82 * u], 0, 180, fill=white)
    d.rounded_rectangle([16 * u, 53 * u, 84 * u, 58 * u], radius=2.5 * u, fill=white)
    # steam
    for x in (38, 50, 62):
        d.arc([(x - 5) * u, 22 * u, (x + 5) * u, 34 * u], 90, 270, fill=white, width=int(3 * u))
        d.arc([(x - 5) * u, 32 * u, (x + 5) * u, 44 * u], 270, 90, fill=white, width=int(3 * u))
    img.resize((size, size), Image.LANCZOS).save(path)

for size, name in [(180, "apple-touch-icon"), (192, "icon-192"), (512, "icon-512")]:
    icon(size, f"app/static/icons/{name}.png")
