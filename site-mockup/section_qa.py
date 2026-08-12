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
PORT = 9556
PROFILE = "/tmp/matthew-section-qa-profile"
OUT = Path(__file__).parent / "site" / "evidence"
CASES = [
    (1440, 1000, ".credential", "credential-desktop"),
    (390, 844, ".credential", "credential-mobile"),
    (1440, 1000, "#events", "events-desktop"),
    (1440, 1000, "#resources", "resources-desktop"),
    (390, 844, "#events", "events-mobile"),
    (390, 844, "#resources", "resources-mobile"),
    (1440, 1000, "#method", "method-desktop"),
    (1024, 900, "#method", "method-tablet"),
    (390, 844, "#method", "method-mobile"),
]
LEADS = ["Tension", "Better language", "Clear decision"]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--hide-scrollbars", "--disable-gpu",
        f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}", "about:blank"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1))
                page = next(p for p in pages if p.get("type") == "page")
                break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError("Chrome CDP did not become ready")
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], origin=f"http://localhost:{PORT}", timeout=20)
        next_id = 0
        def call(method, params=None):
            nonlocal next_id
            next_id += 1
            ws.send(json.dumps({"id": next_id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == next_id:
                    if "error" in msg: raise RuntimeError(msg["error"])
                    return msg.get("result", {})
        results=[]
        for width,height,selector,name in CASES:
            call("Emulation.setDeviceMetricsOverride", {"width":width,"height":height,"deviceScaleFactor":1,"mobile":width<=768})
            call("Page.navigate", {"url":URL}); time.sleep(1)
            call("Runtime.evaluate", {"expression":f"document.documentElement.style.scrollBehavior='auto'; scrollTo(0, document.querySelector('{selector}').offsetTop - 70);"})
            # The arc runs a .4s-delayed stagger on top of a .7s transition; let it land.
            time.sleep(1.8 if selector == "#method" else .35)
            expr=f"""(() => {{
              const section=document.querySelector('{selector}');
              const visible=e=>{{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight&&s.display!=='none'&&s.visibility!=='hidden'}};
              const rect=e=>{{const r=e.getBoundingClientRect();return {{x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom,right:r.right}}}};
              return {{name:'{name}', viewport:{{w:innerWidth,h:innerHeight}}, section:rect(section), overflow:document.documentElement.scrollWidth-innerWidth,
                events:[...document.querySelectorAll('.event')].map(e=>({{visible:visible(e),rect:rect(e)}})),
                badge:[...document.querySelectorAll('.credential-badge')].map(e=>({{complete:e.complete,naturalWidth:e.naturalWidth}})),
                form:document.querySelector('.signup')?{{rect:rect(document.querySelector('.signup')), visible:visible(document.querySelector('.signup')), action:document.querySelector('.signup').action}}:null,
                method:(()=>{{
                  const arc=document.querySelector('#method'), track=arc&&arc.querySelector('.arc-track');
                  if(!arc||!track) return null;
                  return {{order:[...document.querySelectorAll('main section[id]')].map(e=>e.id),
                    line:getComputedStyle(track,'::after').transform,
                    stages:[...arc.querySelectorAll('.arc-stage')].map(e=>({{lead:e.querySelector('h3').textContent.trim(),
                      opacity:parseFloat(getComputedStyle(e).opacity), rect:rect(e)}}))}};
                }})(),
                clipped:[...section.querySelectorAll('h2,h3,p,input:not([tabindex="-1"]),button')].filter(e=>{{const r=e.getBoundingClientRect();return r.left<0||r.right>innerWidth}}).map(e=>e.tagName+':'+e.textContent.trim().slice(0,40))}};
            }})()"""
            result=call("Runtime.evaluate", {"expression":expr,"returnByValue":True})["result"]["value"]
            results.append(result)
            shot=call("Page.captureScreenshot", {"format":"png","captureBeyondViewport":False})
            (OUT/f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
        print(json.dumps(results, indent=2))
        failures=[]
        for r in results:
            if r['overflow'] != 0: failures.append(f"{r['name']}: overflow {r['overflow']}")
            if r['clipped']: failures.append(f"{r['name']}: clipped {r['clipped']}")
            if r['name'].startswith('events') and not any(e['visible'] for e in r['events']): failures.append(f"{r['name']}: no visible event")
            if r['name'].startswith('resources') and not r['form']['visible']: failures.append(f"{r['name']}: form not visible")
            m = r.get('method')
            if not m:
                failures.append(f"{r['name']}: #method section or .arc-track missing")
                continue
            order = m['order']
            if 'method' not in order or order.index('topics') + 1 != order.index('method') or order.index('method') + 1 != order.index('book'):
                failures.append(f"{r['name']}: section order is {order}")
            if [s['lead'] for s in m['stages']] != LEADS:
                failures.append(f"{r['name']}: stage lead phrases are {[s['lead'] for s in m['stages']]}")
            if r['name'].startswith('method'):
                for s in m['stages']:
                    if s['opacity'] < .99 or s['rect']['w'] <= 0 or s['rect']['h'] <= 0:
                        failures.append(f"{r['name']}: stage '{s['lead']}' not revealed (opacity {s['opacity']}, {s['rect']['w']}x{s['rect']['h']})")
                if m['line'] not in ('none', 'matrix(1, 0, 0, 1, 0, 0)'):
                    failures.append(f"{r['name']}: connector line did not draw ({m['line']})")

        # Reduced motion: the sequence must be composed and readable with nothing left animating.
        call("Emulation.setEmulatedMedia", {"features":[{"name":"prefers-reduced-motion","value":"reduce"}]})
        call("Emulation.setDeviceMetricsOverride", {"width":1440,"height":1000,"deviceScaleFactor":1,"mobile":False})
        call("Page.navigate", {"url":URL}); time.sleep(1)
        rm = call("Runtime.evaluate", {"expression":"""(() => {
          const stages=[...document.querySelectorAll('.arc-stage')];
          return {scrollBehavior:getComputedStyle(document.documentElement).scrollBehavior,
            opacity:stages.map(e=>parseFloat(getComputedStyle(e).opacity)),
            duration:stages.map(e=>getComputedStyle(e).transitionDuration),
            node:stages.map(e=>getComputedStyle(e,'::before').transitionDuration),
            line:getComputedStyle(document.querySelector('.arc-track'),'::after').transform,
            lineDuration:getComputedStyle(document.querySelector('.arc-track'),'::after').transitionDuration};
        })()""","returnByValue":True})["result"]["value"]
        print(json.dumps({'reduced_motion': rm}, indent=2))
        if rm['scrollBehavior'] != 'auto': failures.append(f"reduced-motion: scroll-behavior is {rm['scrollBehavior']}")
        if len(rm['opacity']) != 3 or any(o < .99 for o in rm['opacity']): failures.append(f"reduced-motion: stage opacity {rm['opacity']}")
        for label in ('duration', 'node'):
            if any(d != '0s' for d in rm[label]): failures.append(f"reduced-motion: stage {label} {rm[label]}")
        if rm['lineDuration'] != '0s': failures.append(f"reduced-motion: connector transition {rm['lineDuration']}")
        if rm['line'] != 'none': failures.append(f"reduced-motion: connector transform {rm['line']}")

        if failures:
            raise SystemExit('SECTION_QA=FAIL\n'+'\n'.join(failures))
        print('SECTION_QA=PASS')
    finally:
        if ws: ws.close()
        proc.terminate()

if __name__=='__main__': main()
