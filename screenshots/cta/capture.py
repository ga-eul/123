import json
import time
import base64
import requests
import websocket

CDP = "http://localhost:9333"
URL = "https://ga-eul.github.io/123/baemin_club_landing.html"
OUT = "C:/Users/user/Desktop/GTM 실습/screenshots/cta"

CTAS = {
    "header_cta": "header_cta",
    "hero_primary_cta": "hero_primary_cta",
    "sticky_cta": "sticky_cta",
    "final_app_store": "final_app_store",
    "final_google_play": "final_google_play",
}

class CDPSession:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=20)
        self.msg_id = 0

    def send(self, method, params=None):
        self.msg_id += 1
        payload = {"id": self.msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(payload))
        return self.msg_id

    def recv_until(self, target_id):
        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == target_id:
                return data

    def call(self, method, params=None):
        mid = self.send(method, params)
        return self.recv_until(mid)


def new_tab():
    r = requests.put(f"{CDP}/json/new?about:blank")
    r.raise_for_status()
    return r.json()


def close_tab(tab_id):
    requests.get(f"{CDP}/json/close/{tab_id}")


def main():
    tab = new_tab()
    sess = CDPSession(tab["webSocketDebuggerUrl"])

    sess.call("Page.enable")
    sess.call("Emulation.setDeviceMetricsOverride", {
        "width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True
    })
    sess.call("Page.navigate", {"url": URL})
    time.sleep(3.5)  # let fonts/scripts settle

    vw = sess.call("Runtime.evaluate", {"expression": "window.innerWidth", "returnByValue": True})
    print("innerWidth via CDP:", vw["result"]["result"]["value"])

    # 1) Full page screenshot (natural scroll position, sticky bar hidden as real users see it pre-scroll)
    full = sess.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    with open(f"{OUT}/mobile_390_viewport.png", "wb") as f:
        f.write(base64.b64decode(full["result"]["data"]))

    # 2) Per-CTA precise crops via element clip
    for name, cta_id in CTAS.items():
        if cta_id == "sticky_cta":
            sess.call("Runtime.evaluate", {"expression": "window.scrollTo(0,0)"})
            time.sleep(0.3)
            # Force the sticky bar into its shown state for this capture only
            sess.call("Runtime.evaluate", {"expression": "document.getElementById('stickyCta').classList.add('show')"})
            time.sleep(0.3)
        else:
            scroll_expr = f"""
            (function(){{
              const el = document.querySelector('[data-cta-id="{cta_id}"]');
              const r = el.getBoundingClientRect();
              const target = window.scrollY + r.top - (window.innerHeight/2 - r.height/2);
              window.scrollTo(0, Math.max(0, target));
            }})()
            """
            sess.call("Runtime.evaluate", {"expression": scroll_expr})
            time.sleep(0.6)

        rect_expr = f"""
        (function(){{
          const el = document.querySelector('[data-cta-id="{cta_id}"]');
          const r = el.getBoundingClientRect();
          return JSON.stringify({{x:r.x, y:r.y, width:r.width, height:r.height, scrollY:window.scrollY}});
        }})()
        """
        rect_res = sess.call("Runtime.evaluate", {"expression": rect_expr, "returnByValue": True})
        rect = json.loads(rect_res["result"]["result"]["value"])
        print(name, rect)

        pad = 14
        clip = {
            "x": max(0, rect["x"] - pad),
            "y": max(0, rect["y"] + rect["scrollY"] - pad),
            "width": rect["width"] + pad * 2,
            "height": rect["height"] + pad * 2,
            "scale": 1,
        }
        shot = sess.call("Page.captureScreenshot", {"format": "png", "clip": clip})
        with open(f"{OUT}/{name}.png", "wb") as f:
            f.write(base64.b64decode(shot["result"]["data"]))

        if cta_id == "sticky_cta":
            sess.call("Runtime.evaluate", {"expression": "document.getElementById('stickyCta').classList.remove('show')"})

    sess.ws.close()
    close_tab(tab["id"])
    print("done")


if __name__ == "__main__":
    main()
