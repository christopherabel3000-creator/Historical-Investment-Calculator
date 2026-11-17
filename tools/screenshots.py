# Takes the App Store screenshots: six for iPhone 6.3" (1206 x 2622) and six for iPad 13" (2064 x 2752).
# Build and serve the app's files first: node scripts/build-www.js, then python3 -m http.server 8780 --directory www
# Then: python3 tools/screenshots.py appstore/screenshots
import asyncio, sys
from playwright.async_api import async_playwright
OUT = sys.argv[1]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", args=["--no-sandbox"])
        for dev, w, h, scale in (("iphone", 402, 874, 3), ("ipad", 1032, 1376, 2)):
            ctx = await b.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale, color_scheme="light", has_touch=True, is_mobile=True)
            pg = await ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.goto("http://localhost:8780/index.html"); await pg.wait_for_timeout(1200)
            async def shot(name, sel=None, pad=16):
                await pg.evaluate("document.activeElement && document.activeElement.blur()")
                if sel: await pg.evaluate("([s,p]) => { const e = document.querySelector(s); window.scrollTo(0, e.getBoundingClientRect().top + window.scrollY - p); }", [sel, pad])
                else: await pg.evaluate("window.scrollTo(0,0)")
                await pg.wait_for_timeout(300)
                await pg.screenshot(path=f"{OUT}/{dev}-{name}.png")
            await shot("01-start")
            await pg.click("label[for=freq-monthly]"); await pg.fill("#amount", "500")
            await pg.select_option("#year", "2000"); await pg.wait_for_timeout(400)
            await shot("02-results", "#results-h")
            await shot("03-growth", "#chart-h")
            await shot("06-best-worst", "#ext-h")
            await shot("04-will-it-last", "#wd-summary" if dev == "iphone" else "#wd-h")
            await pg.click("label[for=wd-mode-need]"); await pg.fill("#wd-amount", "5,000"); await pg.select_option("#wd-per", "12")
            await pg.wait_for_timeout(900)
            await shot("05-how-much", "#wd-summary" if dev == "iphone" else "#wd-h")
            print(dev, "errors:", errs)
            await ctx.close()
        await b.close()
asyncio.run(main())
