"""Structural + visual QA for the What You Say Next speaker site via headless Chrome CDP."""
import base64, json, subprocess, time, urllib.request, sys
from pathlib import Path
import websocket

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
PROFILE = '/tmp/mj-qa-cdp-profile'
PORT = 9455
URL = 'http://127.0.0.1:8765/'
EV = Path(__file__).resolve().parent / 'site' / 'evidence'
EV.mkdir(parents=True, exist_ok=True)

VIEWPORTS = [
    ('rework-desktop-1440', 1440, 1000, 1, False, False),
    ('rework-desktop-1280', 1280, 900, 1, False, False),
    ('rework-tablet-834', 834, 1112, 1, True, False),
    ('rework-mobile-390', 390, 844, 2, True, False),
    ('rework-mobile-360', 360, 780, 2, True, False),
    ('rework-mobile-390-full', 390, 844, 2, True, True),
    ('rework-desktop-1440-full', 1440, 1000, 1, False, True),
]

CHECK_JS = r"""
(() => {
  const out = {};
  const de = document.documentElement;
  out.innerWidth = window.innerWidth;
  out.scrollWidth = de.scrollWidth;
  out.overflowX = de.scrollWidth - window.innerWidth;
  const overflowing = [];
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right > window.innerWidth + 1.5 || r.left < -1.5) {
      overflowing.push({tag: el.tagName.toLowerCase(), cls: el.className && String(el.className).slice(0,60), left: Math.round(r.left), right: Math.round(r.right)});
    }
  });
  out.overflowingElements = overflowing.slice(0, 12);
  out.overflowingCount = overflowing.length;

  // clipped text: scrollWidth wider than clientWidth on headings / brand
  const clipped = [];
  document.querySelectorAll('h1,h2,h3,.brand-name,.brand-tag,.button,.eyebrow,.topic p').forEach(el => {
    if (el.scrollWidth > el.clientWidth + 1) {
      clipped.push({tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0,40), scrollW: el.scrollWidth, clientW: el.clientWidth, text: el.textContent.trim().slice(0,40)});
    }
  });
  out.clipped = clipped;

  const brand = document.querySelector('header .brand');
  const br = brand.getBoundingClientRect();
  const svg = brand.querySelector('svg').getBoundingClientRect();
  const menu = document.querySelector('.menu');
  const mr = menu.getBoundingClientRect();
  const menuVisible = getComputedStyle(menu).display !== 'none';
  out.brand = {x: +br.x.toFixed(1), y: +br.y.toFixed(1), w: +br.width.toFixed(1), h: +br.height.toFixed(1)};
  out.brandSvg = {w: +svg.width.toFixed(1), h: +svg.height.toFixed(1)};
  out.brandImages = document.querySelectorAll('header .brand img').length;
  out.brandSvgPaths = brand.querySelectorAll('svg path').length;
  out.menu = {visible: menuVisible, w: +mr.width.toFixed(1), h: +mr.height.toFixed(1)};
  out.brandMenuGap = menuVisible ? +(mr.left - br.right).toFixed(1) : null;
  out.navDisplay = getComputedStyle(document.querySelector('nav')).display;

  const hero = document.querySelector('.hero').getBoundingClientRect();
  out.heroHeight = Math.round(hero.height);
  out.heroTopClearance = Math.round(document.querySelector('.hero .eyebrow').getBoundingClientRect().top - br.bottom);

  // tap targets
  const small = [];
  document.querySelectorAll('a.button, nav a, .menu, .resource').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.height < 40) small.push({cls: String(el.className).slice(0,30), text: el.textContent.trim().slice(0,28), h: Math.round(r.height)});
  });
  out.smallTapTargets = small;

  out.docHeight = de.scrollHeight;
  const shells = [...document.querySelectorAll('.shell')].map(s => Math.round(s.getBoundingClientRect().width));
  out.shellWidth = shells[0];
  out.shellWidthsUnique = [...new Set(shells)];
  const fonts = {
    brandName: getComputedStyle(document.querySelector('.brand-name')).fontFamily,
    h1: getComputedStyle(document.querySelector('h1')).fontFamily,
  };
  out.fonts = fonts;
  out.h1FontSize = getComputedStyle(document.querySelector('h1')).fontSize;
  return JSON.stringify(out);
})()
"""


def main():
    p = subprocess.Popen([CHROME, '--headless=new', '--hide-scrollbars', '--disable-gpu',
                          f'--remote-debugging-port={PORT}', '--remote-allow-origins=*',
                          f'--user-data-dir={PROFILE}', 'about:blank'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results = {}
    try:
        pages = None
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                pages = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=1))
                if pages:
                    break
            except Exception:
                time.sleep(.25)
        if not pages:
            raise RuntimeError('CDP not ready')
        page = next(x for x in pages if x.get('type') == 'page')
        ws = websocket.create_connection(page['webSocketDebuggerUrl'], origin=f'http://localhost:{PORT}', timeout=30)
        state = {'id': 0}

        def call(method, params=None):
            state['id'] += 1
            mid = state['id']
            ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get('id') == mid:
                    if 'error' in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get('result', {})

        call('Page.enable')
        for name, w, h, dsf, mobile, full in VIEWPORTS:
            call('Emulation.setDeviceMetricsOverride', {'width': w, 'height': h, 'deviceScaleFactor': dsf, 'mobile': mobile})
            call('Page.navigate', {'url': URL})
            time.sleep(2.2)
            # force reveals visible for full-page shots
            if full:
                call('Runtime.evaluate', {'expression': "document.querySelectorAll('.reveal').forEach(e=>e.classList.add('visible'))"})
                time.sleep(.6)
            raw = call('Runtime.evaluate', {'expression': CHECK_JS, 'returnByValue': True})['result']['value']
            data = json.loads(raw)
            data['viewport'] = f'{w}x{h}@{dsf}'
            results[name] = data
            shot = call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': full})
            out = EV / f'{name}.png'
            out.write_bytes(base64.b64decode(shot['data']))
            data['screenshot'] = str(out)

        # zoomed logo crop at 4x for crispness inspection
        call('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 400, 'deviceScaleFactor': 4, 'mobile': False})
        call('Page.navigate', {'url': URL})
        time.sleep(2)
        box = json.loads(call('Runtime.evaluate', {'expression':
            "JSON.stringify((r=>({x:r.x-10,y:r.y-10,width:r.width+20,height:r.height+20}))(document.querySelector('header .brand').getBoundingClientRect()))",
            'returnByValue': True})['result']['value'])
        shot = call('Page.captureScreenshot', {'format': 'png', 'clip': {**box, 'scale': 4}})
        (EV / 'rework-logo-zoom.png').write_bytes(base64.b64decode(shot['data']))
        results['logoZoom'] = str(EV / 'rework-logo-zoom.png')
        print(json.dumps(results, indent=1))
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


if __name__ == '__main__':
    main()
