import base64, json, subprocess, time, urllib.request
from pathlib import Path
import websocket
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
profile='/tmp/matthew-mobile-cdp-profile'
cmd=[chrome,'--headless=new','--hide-scrollbars','--disable-gpu','--remote-debugging-port=9444','--remote-allow-origins=*',f'--user-data-dir={profile}','about:blank']
p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    deadline=time.time()+15
    pages=None
    while time.time()<deadline:
        try:
            pages=json.load(urllib.request.urlopen('http://127.0.0.1:9444/json',timeout=1))
            if pages: break
        except Exception:
            time.sleep(.2)
    if not pages: raise RuntimeError('CDP did not become ready')
    page=next(x for x in pages if x.get('type')=='page')
    ws=websocket.create_connection(page['webSocketDebuggerUrl'],origin='http://localhost:9444',timeout=20)
    next_id=0
    def call(method,params=None):
        nonlocal_id=None
        global next_id
        next_id+=1
        mid=next_id
        ws.send(json.dumps({'id':mid,'method':method,'params':params or {}}))
        while True:
            msg=json.loads(ws.recv())
            if msg.get('id')==mid:
                if 'error' in msg: raise RuntimeError(msg['error'])
                return msg.get('result',{})
    call('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
    call('Page.navigate',{'url':'http://127.0.0.1:8765/'})
    time.sleep(2)
    metrics=call('Runtime.evaluate',{'expression':"JSON.stringify({innerWidth,scrollWidth:document.documentElement.scrollWidth,menu:getComputedStyle(document.querySelector('.menu')).display,title:document.title})",'returnByValue':True})
    print(metrics['result']['value'])
    shot=call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
    out=Path('/Users/antonio.server/.hermes/workspace/clients/matthew-johnson-nexphrase/site-mockup/site/evidence/brand-mobile-true-390.png')
    out.write_bytes(base64.b64decode(shot['data']))
    print(out)
finally:
    p.terminate()
    try: p.wait(timeout=5)
    except subprocess.TimeoutExpired: p.kill()
