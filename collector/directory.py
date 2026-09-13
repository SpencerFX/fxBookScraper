"""Crawl the /systems directory. myfxbook paginates by PATH: /systems, /systems/2,
/systems/3, ... (the `?p=` query param is ignored). ~16 systems per page.
"""

from parser.directory import parse_systems_page, last_page_number

SYSTEMS_READY_SELECTOR = "#systemsContTable tbody tr, a[href*='/members/']"


class DirectoryCrawler:
    def __init__(self, browser, base_url, systems_url):
        self.browser = browser
        self.base_url = base_url
        self.systems_url = systems_url.rstrip("/")

    def _page_url(self, page):
        return self.systems_url if page <= 1 else f"{self.systems_url}/{page}"

    def discover(self, max_pages=0, on_page=None, empty_streak_stop=2, safety_cap=80):
        discovered = {}
        empty_streak = 0
        page = 1
        total_pages = None

        while page <= safety_cap:
            url = self._page_url(page)
            try:
                html, _ = self.browser.goto(url, wait_selector=SYSTEMS_READY_SELECTOR)
                systems = parse_systems_page(html, self.base_url)
            except Exception as exc:  # one bad page must not abort discovery
                print(f"[directory] p{page}: ERROR {exc!r} — skipping")
                systems, html = [], ""

            if total_pages is None:
                total_pages = last_page_number(html)
                if total_pages:
                    print(f"[directory] pagination reports ~{total_pages} pages")

            before = len(discovered)
            for s in systems:
                discovered.setdefault(s["system_id"], s)
            added = len(discovered) - before
            print(f"[directory] p{page}: {len(systems)} rows, +{added} new "
                  f"({len(discovered)} total)")

            if on_page:
                on_page(page, list(discovered.values()))

            empty_streak = empty_streak + 1 if len(systems) == 0 else 0
            if empty_streak >= empty_streak_stop:
                break
            if max_pages and page >= max_pages:
                break
            if total_pages and page >= total_pages and len(systems) == 0:
                break
            page += 1

        return list(discovered.values())
