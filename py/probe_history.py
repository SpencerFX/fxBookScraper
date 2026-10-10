"""Verify: GET /paging.html + the paging-btn `params` querystring returns the
next page of the closed-trades history table."""

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.browser import Browser

SID = sys.argv[1] if len(sys.argv) > 1 else "3534905"
URL = sys.argv[2] if len(sys.argv) > 2 else \
    f"https://www.myfxbook.com/members/FERRARI2009/ic-markets/{SID}"


def close_times(html):
    # each data row's 2nd date cell (close date), format 'MM/DD/YYYY HH:MM' or similar
    return re.findall(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", html or "")[:10]


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    with Browser(cfg) as b:
        b.goto(URL)
        print("title:", b.page.title())

        st, data = b.fetch_json("/systemPageGetHistoryFirstPage.json",
                                method="POST", form={"accountOid": SID})
        frag1 = ""
        if isinstance(data, dict):
            c = data.get("content")
            frag1 = c.get("history") if isinstance(c, dict) else (c or "")
        m = re.search(r'a\.paging-btn"\s+params="([^"]+)"[^>]*page="2"', frag1) \
            or re.search(r'params="([^"]+)"\s+page="2"', frag1)
        params = m.group(1) if m else None
        print("page1 rows (close times):", close_times(frag1))
        print("page2 params:", params)
        if not params:
            print("!! no page-2 params found"); return

        # THE CALL: GET /paging.html + params
        st, body = b.fetch_text("/paging.html" + params)
        print(f"\nGET /paging.html  status={st}  len={len(body)}")
        has_table = "tradingHistoryTable" in body
        print("contains #tradingHistoryTable:", has_table)
        print("page2 rows (close times):", close_times(body))
        act = re.search(r'<li class="active"[^>]*>\s*<a[^>]*page="(\d+)"', body)
        print("active page in response:", act.group(1) if act else "?")

        with open("data/probe_paging_p2.html", "w", encoding="utf-8") as f:
            f.write(body)
        print("saved -> data/probe_paging_p2.html")


if __name__ == "__main__":
    main()
