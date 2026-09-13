"""Collect one system: navigate the attached browser to its page, then pull the
history + daily-series JSON via same-origin fetch from that (Cloudflare-cleared) tab.
"""

import json
import random
import time
from datetime import datetime, timezone

from parser.system import history_total, parse_trades_fragment


HISTORY_FIRST = "/systemPageGetHistoryFirstPage.json"
# paging endpoint candidates (first that returns usable HTML wins)
HISTORY_PAGE_CANDIDATES = [
    "/systemPageGetHistoryFirstPage.json",
    "/systemPageGetHistory.json",
    "/systemGetHistoryPage.json",
    "/getHistoryPage.json",
]
CHARTS = "/private/charts.json"


class SystemCollector:
    def __init__(self, browser, config):
        self.browser = browser
        ccfg = config.get("collector", {}) or {}
        self.history_max_pages = int(ccfg.get("history_max_pages", 60))
        self._page_ep = None  # resolved once per run

    # ---------------------------------------------------------------- public

    def collect(self, system, want_history=True, want_daily=True):
        url = system["url"]
        stats_html, _ = self.browser.goto(url)
        sid = system["system_id"]

        history_fragments = []
        if want_history:
            history_fragments = self._collect_history(sid)

        charts_obj = None
        if want_daily:
            charts_obj = self._collect_daily(sid)

        return {
            "system_id": sid,
            "url": url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "stats_html": stats_html,
            "history_fragments": history_fragments,
            "charts_obj": charts_obj,
        }

    # ---------------------------------------------------------------- history

    def _collect_history(self, sid):
        status, data = self.browser.fetch_json(HISTORY_FIRST, method="POST",
                                               form={"accountOid": sid})
        frag = self._fragment(data)
        if not frag:
            return []
        frags = [frag]

        total = history_total(frag) or 0

        def sigs(fr):
            return {(t.get("openTime"), t.get("symbol"), t.get("closeTime"),
                     t.get("profit")) for t in parse_trades_fragment(fr)}

        seen = sigs(frag)
        if total <= len(seen) or not seen:
            return frags

        page = 2
        while len(frags) < self.history_max_pages and len(seen) < total:
            nxt = self._history_page(sid, page)
            if not nxt:
                break
            new = sigs(nxt) - seen
            if not new:
                break                 # endpoint ignored the page param
            frags.append(nxt)
            seen |= new
            page += 1
            time.sleep(0.4)
        return frags

    def _history_page(self, sid, page):
        form = {"accountOid": sid, "pageNumber": page, "page": page, "p": page}
        if self._page_ep:
            _, data = self.browser.fetch_json(self._page_ep, method="POST", form=form)
            return self._fragment(data)
        for ep in HISTORY_PAGE_CANDIDATES:
            status, data = self.browser.fetch_json(ep, method="POST", form=form)
            frag = self._fragment(data)
            if frag:
                self._page_ep = ep
                return frag
        return None

    @staticmethod
    def _fragment(data):
        if isinstance(data, dict) and not data.get("error"):
            c = data.get("content")
            if isinstance(c, dict):
                return c.get("history") or c.get("historyHtml")
            if isinstance(c, str):
                return c
        return None

    # ---------------------------------------------------------------- daily

    def _collect_daily(self, sid):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        qs = (f"?startDate=2005-01-01&endDate={today}"
              f"&showLots=true&showPips=true&showChange=false&showSymbolPips=false"
              f"&showMain=true&selectedTime=1&chartType=1&period=6&l=s"
              f"&accountOid={sid}&rand={random.random()}")
        # best-effort fetch() from the member page (navigating to /private/* draws
        # a challenge nearly every time; a blocked fetch just yields no daily data)
        _status, data = self.browser.fetch_json(CHARTS + qs)
        return data if isinstance(data, dict) else None
