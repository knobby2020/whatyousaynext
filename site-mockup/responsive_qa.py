import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    import websocket
except ImportError:  # stdlib fallback keeps the existing QA command working
    import cdp_ws as websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
URL = "http://127.0.0.1:8765/"
PORT = 9555
PROFILE = "/tmp/matthew-responsive-qa-profile"
OUT = Path(__file__).parent / "site" / "evidence"
VIEWPORTS = [
    (320, 844, "qa-mobile-320"),
    (390, 844, "brand-mobile-true-390"),
    (414, 896, "qa-mobile-414"),
    (600, 900, "qa-edge-600"),
    (601, 900, "qa-edge-601"),
    (605, 900, "qa-edge-605"),
    (611, 900, "qa-edge-611"),
    (680, 900, "qa-edge-680"),
    (681, 900, "qa-edge-681"),
    (768, 1024, "qa-tablet-768"),
    (899, 900, "qa-edge-899"),
    (900, 900, "qa-edge-900"),
    (901, 900, "qa-edge-901"),
    (902, 900, "qa-edge-902"),
    (1024, 900, "qa-tablet-1024"),
    (1440, 1100, "brand-desktop"),
    (1920, 1080, "qa-desktop-1920"),
]


def wait_for_page():
    deadline = time.time() + 15
    endpoint = f"http://127.0.0.1:{PORT}/json"
    while time.time() < deadline:
        try:
            pages = json.load(urllib.request.urlopen(endpoint, timeout=1))
            if pages:
                return next(page for page in pages if page.get("type") == "page")
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Chrome CDP did not become ready")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = [
        CHROME,
        "--headless=new",
        "--hide-scrollbars",
        "--disable-gpu",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "about:blank",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        page = wait_for_page()
        ws = websocket.create_connection(
            page["webSocketDebuggerUrl"], origin=f"http://localhost:{PORT}", timeout=20
        )
        next_id = 0

        def call(method, params=None):
            nonlocal next_id
            next_id += 1
            mid = next_id
            ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg.get("result", {})

        call("Network.enable")
        call("Network.setCacheDisabled", {"cacheDisabled": True})
        results = []
        for width, height, name in VIEWPORTS:
            call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": width <= 768,
                },
            )
            call("Page.navigate", {"url": URL})
            time.sleep(1)
            expression = r"""
            (() => {
              const q = s => document.querySelector(s);
              const rect = s => q(s) ? Object.fromEntries(
                ['x','y','width','height','top','right','bottom','left'].map(k => [k, q(s).getBoundingClientRect()[k]])
              ) : null;
              const textRect = s => {
                const el = q(s);
                if (!el || getComputedStyle(el).display === 'none') return null;
                const range = document.createRange();
                range.selectNodeContents(el);
                const r = range.getBoundingClientRect();
                return Object.fromEntries(['x','y','width','height','top','right','bottom','left'].map(k => [k, r[k]]));
              };
              const font = s => q(s) ? parseFloat(getComputedStyle(q(s)).fontSize) : null;
              const old = document.body.style.overflowX;
              document.body.style.overflowX = 'visible';
              const metrics = {
                viewport: {width: innerWidth, height: innerHeight},
                scrollWidth: document.documentElement.scrollWidth,
                documentHeight: document.documentElement.scrollHeight,
                brand: rect('.brand'),
                brandMark: rect('.brand-mark, .brand img'),
                menu: rect('.menu'),
                hero: rect('.hero'),
                shell: rect('.hero .shell'),
                heroCopy: rect('.hero-copy'),
                heroIdentityText: textRect('.hero-identity'),
                heroNameplate: rect('.hero-nameplate'),
                heroFootText: textRect('.hero-foot'),
                heroNameplateDisplay: q('.hero-nameplate') ? getComputedStyle(q('.hero-nameplate')).display : null,
                mobileEyebrowDisplay: q('.eyebrow-mobile') ? getComputedStyle(q('.eyebrow-mobile')).display : null,
                motionReady: document.documentElement.classList.contains('motion-ready'),
                heroTransform: q('.hero-media') ? getComputedStyle(q('.hero-media')).transform : null,
                logoComplete: Boolean(q('.brand-mark img')?.complete),
                logoNatural: q('.brand-mark img') ? [q('.brand-mark img').naturalWidth, q('.brand-mark img').naturalHeight] : null,
                bookVisual: rect('.book-visual'),
                bookCover: rect('.book-cover'),
                credentialImage: rect('.credential-image'),
                credentialBadge: rect('.credential-badge'),
                sectionOrder: [...document.querySelectorAll('main section[id]')].map(el => el.id),
                arcTrack: rect('.arc-track'),
                arcStages: [...document.querySelectorAll('.arc-stage')].map(el => {
                  const r = el.getBoundingClientRect();
                  return {lead: el.querySelector('h3').textContent.trim(), left: r.left, right: r.right, width: r.width, height: r.height};
                }),
                fontSizes: {
                  heroEyebrow: font('.hero .eyebrow'),
                  heroIdentity: font('.hero-identity'),
                  body: font('.hero-lede')
                },
                logoText: q('.brand')?.innerText.trim() || q('.brand img')?.alt || '',
                title: document.title
              };
              document.body.style.overflowX = old;
              return metrics;
            })()
            """
            evaluated = call(
                "Runtime.evaluate", {"expression": expression, "returnByValue": True}
            )
            metrics = evaluated["result"]["value"]
            metrics["name"] = name
            metrics["overflow"] = metrics["scrollWidth"] - metrics["viewport"]["width"]
            results.append(metrics)
            shot = call(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
            )
            (OUT / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))

        report = Path(__file__).parent / "responsive-qa-report.json"
        report.write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
        print(f"report={report}")
        failures = []
        for item in results:
            if item["overflow"] != 0:
                failures.append(f"{item['name']}: horizontal overflow {item['overflow']}px")
            if not item["motionReady"]:
                failures.append(f"{item['name']}: motion layer did not initialize")
            if not item["logoComplete"] or item["logoNatural"] != [512, 512]:
                failures.append(f"{item['name']}: official logo asset incomplete or wrong dimensions")
            if item["viewport"]["width"] > 680:
                if item["heroNameplateDisplay"] == "none":
                    failures.append(f"{item['name']}: desktop/tablet nameplate hidden")
                n, c = item["heroNameplate"], item["heroCopy"]
                if n and c and not (n["left"] >= c["right"] or n["right"] <= c["left"] or n["top"] >= c["bottom"] or n["bottom"] <= c["top"]):
                    failures.append(f"{item['name']}: nameplate overlaps hero copy")
                f = item["heroFootText"]
                if n and f and not (n["left"] >= f["right"] or n["right"] <= f["left"] or n["top"] >= f["bottom"] or n["bottom"] <= f["top"]):
                    failures.append(f"{item['name']}: nameplate overlaps hero footer tagline")
                i = item["heroIdentityText"]
                if n and i and not (n["left"] >= i["right"] or n["right"] <= i["left"] or n["top"] >= i["bottom"] or n["bottom"] <= i["top"]):
                    failures.append(f"{item['name']}: nameplate overlaps hero identity text")
            else:
                if item["heroNameplateDisplay"] != "none" or item["mobileEyebrowDisplay"] == "none":
                    failures.append(f"{item['name']}: mobile identity adaptation is incorrect")
            if item["sectionOrder"][:4] != ["about", "topics", "method", "book"]:
                failures.append(f"{item['name']}: section order is {item['sectionOrder']}")
            if [s["lead"] for s in item["arcStages"]] != ["Tension", "Better language", "Clear decision"]:
                failures.append(f"{item['name']}: arc stage leads are {[s['lead'] for s in item['arcStages']]}")
            for stage in item["arcStages"]:
                if stage["left"] < -1 or stage["right"] > item["viewport"]["width"] + 1:
                    failures.append(f"{item['name']}: arc stage '{stage['lead']}' spans {stage['left']}–{stage['right']} outside the viewport")
                if stage["width"] < 120 or stage["height"] < 60:
                    failures.append(f"{item['name']}: arc stage '{stage['lead']}' collapsed to {stage['width']}x{stage['height']}")
            if item["viewport"]["width"] <= 414:
                if item["menu"] and (item["menu"]["width"] < 44 or item["menu"]["height"] < 44):
                    failures.append(f"{item['name']}: menu target under 44px")
                for label, size in item["fontSizes"].items():
                    floor = 16 if label == "body" else 11
                    if size is not None and size < floor:
                        failures.append(f"{item['name']}: {label} font {size}px below {floor}px")
        call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
        call("Page.navigate", {"url": URL})
        time.sleep(1)
        reduced = call("Runtime.evaluate", {"expression": "getComputedStyle(document.querySelector('.hero-media')).animationName", "returnByValue": True})["result"]["value"]
        if reduced != "none":
            failures.append(f"reduced-motion: hero animation remains active ({reduced})")
        arc_reduced = call("Runtime.evaluate", {"expression": """(() => {
          const stages = [...document.querySelectorAll('.arc-stage')];
          return {opacity: stages.map(el => parseFloat(getComputedStyle(el).opacity)),
            duration: stages.map(el => getComputedStyle(el).transitionDuration),
            line: getComputedStyle(document.querySelector('.arc-track'), '::after').transform,
            scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior};
        })()""", "returnByValue": True})["result"]["value"]
        if len(arc_reduced["opacity"]) != 3 or any(o < 0.99 for o in arc_reduced["opacity"]):
            failures.append(f"reduced-motion: arc stages not fully visible ({arc_reduced['opacity']})")
        if any(d != "0s" for d in arc_reduced["duration"]):
            failures.append(f"reduced-motion: arc stage transitions remain active ({arc_reduced['duration']})")
        if arc_reduced["line"] != "none":
            failures.append(f"reduced-motion: arc connector is still transformed ({arc_reduced['line']})")
        if arc_reduced["scrollBehavior"] != "auto":
            failures.append(f"reduced-motion: scroll-behavior is {arc_reduced['scrollBehavior']}")
        if failures:
            print("FAILURES")
            for failure in failures:
                print(f"- {failure}")
            raise SystemExit(1)
        print("RESPONSIVE_QA=PASS")
    finally:
        if ws is not None:
            ws.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
