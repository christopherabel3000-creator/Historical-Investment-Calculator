# Saves the app icon (1024 x 1024), the launch image (2732 x 2732) and the website icons from tools/icon.html.
# From the repo root: python3 tools/icon.py
# Then copy AppIcon-1024.png and the launch image into ios/App/App/Assets.xcassets (this script does it).
import asyncio, pathlib
from PIL import Image
from playwright.async_api import async_playwright
ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "tools" / "icon.html").as_uri()
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", args=["--no-sandbox"])
        for name, q, n in (("/tmp/AppIcon-1024.png", "", 1024), ("/tmp/splash-2732.png", "?splash", 2732)):
            pg = await b.new_page(viewport={"width": n, "height": n})
            await pg.goto(PAGE + q); await pg.wait_for_timeout(200)
            await pg.screenshot(path=name, clip={"x": 0, "y": 0, "width": n, "height": n})
            await pg.close()
        await b.close()
asyncio.run(main())
icon = Image.open("/tmp/AppIcon-1024.png").convert("RGB")  # the App Store icon must have no transparency
assets = ROOT / "ios/App/App/Assets.xcassets"
icon.save(assets / "AppIcon.appiconset/AppIcon-512@2x.png")
splash = Image.open("/tmp/splash-2732.png").convert("RGB")
for f in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
    splash.save(assets / "Splash.imageset" / f)
(ROOT / "icons").mkdir(exist_ok=True)
for name, n in (("icon-512.png", 512), ("apple-touch-icon.png", 180), ("favicon-32.png", 32)):
    icon.resize((n, n), Image.LANCZOS).save(ROOT / "icons" / name)
print("Saved the app icon, launch image and website icons.")
