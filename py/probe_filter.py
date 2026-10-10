"""One-off: inspect the myfxbook filtered-search results page (the losing-accounts
filter URL) to see whether it reuses #systemsContTable (so parser/directory.py just
works) or needs a different parser. Uses a FRESH browser tab (new_tab=True) so it
does not interfere with any other run already driving the shared Brave instance.
"""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.browser import Browser

URL = sys.argv[1] if len(sys.argv) > 1 else (
    "https://www.myfxbook.com/systems?p=1&profitType=1&profitValue=-0.01&drawType=1"
    "&drawValue=50&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30"
    "&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2"
    "&lastTraded=90&regulationType=1&tradesType=0&size=15&pt=6&sb=19&st=2"
    "&sb=19&st=2&sb=19&st=2"
)


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    cfg.setdefault("browser", {})["new_tab"] = True
    with Browser(cfg) as b:
        html, _ = b.goto(URL)
        print("title:", b.page.title())
        print("html len:", len(html))
        with open("data/probe_filter.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("saved -> data/probe_filter.html")

        from parser.directory import parse_systems_page, last_page_number
        systems = parse_systems_page(html, "https://www.myfxbook.com")
        print("parse_systems_page found:", len(systems))
        for s in systems[:5]:
            print("  ", s)
        print("last_page_number:", last_page_number(html))

        has_cont_table = "systemsContTable" in html
        print("has #systemsContTable:", has_cont_table)
        import re
        for pat in (r'id="([a-zA-Z]*[Ss]ystem[a-zA-Z]*Table)"',
                    r'id="([a-zA-Z]*[Rr]esult[a-zA-Z]*)"',
                    r'class="pagination[^"]*"'):
            found = set(re.findall(pat, html))
            if found:
                print(f"  matches for {pat}: {found}")


if __name__ == "__main__":
    main()
