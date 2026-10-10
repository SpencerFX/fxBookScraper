"""Parse the rendered /systems directory listing (table id=systemsContTable).

Row layout (10 <td>), headers: '', System, '', Gain, Drawdown, Monthly, Yearly,
Badges, Performance, ''.  td[1]/td[2] carry the /members/<user>/<name>/<id> link.
"""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from parser.stats import number, clean_text


_MEMBER_RE = re.compile(r"/members/([^/]+)/([^/]+)/(\d+)")


def _has_member_href(value):
    return bool(value) and _MEMBER_RE.search(value) is not None


def _member_ident(href):
    m = _MEMBER_RE.search(href or "")
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def parse_systems_page(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="systemsContTable")
    rows_src = (table.find("tbody").find_all("tr") if table and table.find("tbody")
               else [])

    out = {}
    for tr in rows_src:
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue
        ident = None
        for td in tds[:3]:
            a = td.find("a", href=_has_member_href)
            if a:
                ident = _member_ident(a["href"])
                if ident:
                    break
        if not ident:
            continue
        user, name, sid = ident
        namecell = clean_text(tds[2].get_text(" ")) if len(tds) > 2 else name
        out[sid] = {
            "system_id": sid,
            "username": user,
            "system_name": name,
            "display_name": namecell or name,
            "url": f"{base_url}/members/{user}/{name}/{sid}",
            "list_gain": number(tds[3].get_text()) if len(tds) > 3 else None,
            "list_drawdown": number(tds[4].get_text()) if len(tds) > 4 else None,
            "list_monthly": number(tds[5].get_text()) if len(tds) > 5 else None,
            "list_yearly": number(tds[6].get_text()) if len(tds) > 6 else None,
        }

    # fallback: any /members/ links on the page (keeps us working if the table id changes)
    if not out:
        for a in soup.find_all("a", href=_has_member_href):
            ident = _member_ident(a["href"])
            if not ident:
                continue
            user, name, sid = ident
            out.setdefault(sid, {
                "system_id": sid, "username": user, "system_name": name,
                "display_name": clean_text(a.get_text(" ")) or name,
                "url": f"{base_url}/members/{user}/{name}/{sid}",
            })
    return list(out.values())


def last_page_number(html):
    """Total page count from the .pagination control (links are /systems/<N>)."""
    soup = BeautifulSoup(html, "lxml")
    ul = soup.find("ul", class_=lambda c: c and "pagination" in c)
    scope = ul if ul else soup
    nums = [int(m.group(1))
            for a in scope.find_all("a", href=True)
            for m in [re.search(r"/systems/(\d+)(?:$|[?#])", a["href"])] if m]
    return max(nums) if nums else None
