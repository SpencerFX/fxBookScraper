"""Browser access for the myfxbook crawler.

myfxbook is behind Cloudflare in "challenge on every request" mode. The only thing
that works reliably is driving your *real* Brave/Chrome over the DevTools protocol:

  1. Fully quit Brave.
  2. Relaunch it with a debug port:
       & "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe" --remote-debugging-port=9222
  3. In that Brave, open https://www.myfxbook.com/systems and solve Cloudflare once.
  4. Run the crawler. It attaches to that browser and navigates it.

One manual solve covers a long run of automated navigations. When Cloudflare does
re-challenge mid-crawl, the crawler pauses and waits (no clicking) for you to solve
it in the Brave window, then continues. Progress is checkpointed either way.
"""

import json
import time
import random
from pathlib import Path

from patchright.sync_api import sync_playwright


CF_TITLE_MARKERS = ("just a moment", "attention required", "checking your browser",
                    "moment...", "しばらくお待ちください")


class CloudflareBlocked(RuntimeError):
    """Raised when a challenge is up and not solved within the allotted time."""


class Browser:
    def __init__(self, config, profile_dir=None):
        bcfg = config.get("browser", {}) or {}
        self.cdp_url = bcfg.get("cdp_url", "http://127.0.0.1:9222")
        self.accept_language = bcfg.get("accept_language", "en-US,en;q=0.9")
        self.nav_timeout = int(bcfg.get("nav_timeout_ms", 60000))
        self.networkidle_ms = int(bcfg.get("networkidle_ms", 20000))
        self.settle_ms = int(bcfg.get("settle_ms", 2500))
        self.challenge_wait_s = int(bcfg.get("challenge_auto_wait_s", 25))
        self.manual_solve_timeout_s = int(bcfg.get("manual_solve_timeout_s", 900))

        ccfg = config.get("collector", {}) or {}
        self.delay = float(ccfg.get("request_delay_seconds", 2.0))
        self.new_tab = bool(bcfg.get("new_tab", False))

        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._last_nav = 0.0

    # -- lifecycle -----------------------------------------------------------

    def start(self):
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(self.cdp_url)
        except Exception as exc:
            self._pw.stop()
            raise RuntimeError(
                f"Cannot attach to Brave at {self.cdp_url}. Launch Brave with "
                f"--remote-debugging-port=9222 and open myfxbook once.\n  {exc}"
            )
        self._ctx = (self._browser.contexts[0] if self._browser.contexts
                     else self._browser.new_context())
        try:
            self._ctx.set_extra_http_headers({"Accept-Language": self.accept_language})
        except Exception:
            pass
        try:
            self._ctx.add_cookies([{"name": "locale", "value": "en",
                                    "domain": ".myfxbook.com", "path": "/"}])
        except Exception:
            pass
        # a concurrent second run must NOT grab the same tab another run is
        # driving (they'd fight over navigation) - open a fresh tab instead
        self._page = self._ctx.new_page() if self.new_tab else self._pick_page()
        return self

    def _pick_page(self):
        for pg in self._ctx.pages:
            if "myfxbook.com" in (pg.url or ""):
                return pg
        return self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def close(self):
        # detach only — never kill the user's browser
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()
        self._browser = self._pw = self._ctx = self._page = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
        return False

    @property
    def page(self):
        return self._page

    # -- cloudflare --------------------------------------------------------------

    def looks_blocked(self, page=None):
        page = page or self._page
        try:
            title = (page.title() or "").strip().lower()
        except Exception:
            return True
        if any(m in title for m in CF_TITLE_MARKERS):
            return True
        try:
            if page.locator("#challenge-form, #challenge-running").count():
                return True
        except Exception:
            pass
        return False

    def _wait_clear(self, url, budget_s):
        deadline = time.time() + budget_s
        announced = False
        ticks = 0
        while time.time() < deadline:
            if not self.looks_blocked():
                if announced:
                    print("  ...Cloudflare cleared, continuing.", flush=True)
                    time.sleep(1.5)
                return True
            if not announced:
                print("\n" + "=" * 70, flush=True)
                print("  CLOUDFLARE — solve it in the Brave window (no rush).", flush=True)
                print(f"  {url}", flush=True)
                print("=" * 70, flush=True)
                announced = True
            ticks += 1
            if ticks % 6 == 0:
                print(f"  waiting for solve... {int(deadline - time.time())}s left",
                      flush=True)
            time.sleep(5)
        return not self.looks_blocked()

    def clear_challenge(self, url="(current page)"):
        if not self.looks_blocked():
            return
        if self._wait_clear(url, self.challenge_wait_s):
            return
        if self._wait_clear(url, self.manual_solve_timeout_s):
            try:
                self._page.wait_for_load_state("networkidle", timeout=self.networkidle_ms)
            except Exception:
                pass
            return
        raise CloudflareBlocked(url)

    # -- navigation -----------------------------------------------------------

    def _throttle(self):
        target = self.delay + random.uniform(0.0, self.delay * 0.5)
        elapsed = time.time() - self._last_nav
        if elapsed < target:
            time.sleep(target - elapsed)
        self._last_nav = time.time()

    def goto(self, url, wait_selector=None, capture=None, attempts=3):
        """Navigate the attached browser to `url`, clearing Cloudflare if needed.

        `capture` is accepted for API compatibility but CDP-mode collectors get
        their JSON via `fetch_text` / `fetch_json` instead. Returns (html, []).
        """
        self._throttle()
        for attempt in range(attempts):
            try:
                self._page.goto(url, wait_until="domcontentloaded",
                                timeout=self.nav_timeout)
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(2 ** attempt)
                continue
            if self.looks_blocked():
                self.clear_challenge(url)
            try:
                self._page.wait_for_load_state("networkidle",
                                               timeout=self.networkidle_ms)
            except Exception:
                pass
            if wait_selector:
                try:
                    self._page.wait_for_selector(wait_selector, timeout=15000)
                except Exception:
                    pass
            if not self.looks_blocked():
                break
            time.sleep(3 * (attempt + 1))
        self._page.wait_for_timeout(self.settle_ms)
        return self._page.content(), []

    # -- same-origin fetch from the cleared page ---------------------------------

    def fetch_text(self, path, method="GET", form=None, headers=None):
        """Run fetch() inside the current page. BEST-EFFORT: a Cloudflare block on a
        data fetch returns the 403 rather than forcing a manual solve (those fetches
        are what draw most of the extra challenges). Callers treat a block as
        'no data for this system' and move on; navigation still solves normally."""
        js = """
        async ({path, method, form, headers}) => {
          const opt = {method, credentials:'include', headers: headers || {}};
          if (form) {
            opt.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8';
            opt.headers['X-Requested-With'] = 'XMLHttpRequest';
            opt.body = new URLSearchParams(form).toString();
          }
          try {
            const r = await fetch(path, opt);
            const t = await r.text();
            return {status: r.status, body: t};
          } catch (e) { return {status: 0, body: String(e)}; }
        }"""
        res = self._page.evaluate(js, {"path": path, "method": method,
                                       "form": form or None, "headers": headers or None})
        return res["status"], res["body"]

    def goto_json(self, url):
        """Fetch a JSON endpoint via NAVIGATION (challenges far less than fetch()).
        Returns parsed JSON or None. Solves a real navigation challenge if one appears."""
        self._throttle()
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=self.nav_timeout)
        except Exception:
            return None
        if self.looks_blocked():
            try:
                self.clear_challenge(url)
            except CloudflareBlocked:
                return None
        for extractor in ("document.body ? document.body.innerText : ''",
                          "document.querySelector('pre') ? document.querySelector('pre').innerText : ''"):
            try:
                txt = self._page.evaluate(extractor)
                if txt and txt.strip().startswith(("{", "[")):
                    return json.loads(txt)
            except Exception:
                continue
        return None

    def fetch_json(self, path, method="GET", form=None):
        status, body = self.fetch_text(path, method=method, form=form)
        try:
            return status, json.loads(body)
        except Exception:
            return status, None

    def cf_cookies(self):
        try:
            return {c["name"]: c["value"] for c in self._ctx.cookies()
                    if c["name"] in ("cf_clearance", "__cf_bm")}
        except Exception:
            return {}
