"""`make site`, step 3: tie the page to the files it loads.

  .venv/bin/python -m tools.site_stamp
site/index.html loads four scripts from site/shared/. Each link carries `?v=` and the first eight characters of
that file's SHA-256, so a browser or a host never pairs a cached old data file with a new page. The page changes
only when a file it loads changed, so running this twice in a row changes nothing. It also writes the data's date
into the footer's "Data through", which shows before the scripts have loaded.
"""
import hashlib
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site" / "index.html"
SCRIPTS = ("catalog.js", "data.js", "charts.js", "viz.js")

html = PAGE.read_text()
for name in SCRIPTS:
    path = ROOT / "site" / "shared" / name
    if not path.exists():
        sys.exit(f"{path.relative_to(ROOT)} is missing: run `make site` from the start")
    tag = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    html, found = re.subn(rf'(src="shared/{re.escape(name)})(?:\?v=[^"]*)?"', rf'\1?v={tag}"', html)
    if found != 1:
        sys.exit(f"site/index.html should load shared/{name} exactly once, found {found}")
# The footer's "Data through" is in the page itself, so it is right while the scripts are still loading (they set it again)
as_of = re.search(r'"asOf":"(\d{4}-\d{2}-\d{2})"', (ROOT / "site" / "shared" / "data.js").read_text()[:400])
if as_of:
    d = date.fromisoformat(as_of.group(1))
    html = re.sub(r"(<b data-asof>)[^<]*(</b>)", rf"\g<1>{d.day} {d:%b %Y}\g<2>", html)
if html != PAGE.read_text():
    PAGE.write_text(html)
print("site/index.html loads the four files in site/shared/ by their hashes")
