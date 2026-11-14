"""`make site`, step 2: export the warehouse's table catalog for the dashboard's table browser.

  .venv/bin/python -m tools.site_catalog
Reads data/gold/_catalog.json (written by `make catalog`) and the dbt manifest (written by
`make warehouse`), and writes site/shared/catalog.js. Nothing in the warehouse is opened.

Each table carries its direct sources, as the catalog names them, kept to the sources
the dbt lineage confirms. Each field carries its own sources only when its name or the
first sentence of its description names one ("Captured revenue per DefiLlama", "Volume per
NearBlocks."); otherwise it reads the table's, which is certain only when the table has
one source. Date fields and the fields of the grain are keys: they place a row, so they
never add a source. Tables built from other tables' rows (dq_reconciliation) are marked
"v": which sources a query reads there depends on the rows it keeps.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "gold" / "_catalog.json"
MANIFEST = ROOT / "warehouse" / "target" / "manifest.json"
OUT = ROOT / "site" / "shared" / "catalog.js"

# Source ids are the site's (shared/viz.js SOURCES); the order breaks no ties, the lineage does
PATTERNS = [
    ("hos", r"vote\.dao|venear\.dao|house of stake"),
    ("rpc", r"\brpc\b|archival|read on chain|protocol config|lockup contract"),
    ("fastnear", r"fastnear|wallet transfers"),
    ("neardata", r"neardata"),
    ("nearblocks", r"nearblocks|/v1/charts|/v3/"),
    ("defillama", r"defillama"),
    ("revenue", r"revenue\.near\.org|revenue page"),
    ("dune", r"\bdune\b"),
    ("explorer", r"intents explorer|1click|oneclick"),
    ("gov", r"gov\.near\.org|governance forum"),
    ("coinmetrics", r"coin ?metrics"),
    ("coinbase", r"coinbase"),
    ("bitwise", r"bitwise"),
    ("sosovalue", r"sosovalue"),
    ("github", r"github"),
    ("registry", r"\bregistry\b"),
    ("nearcatalog", r"near catalog|nearcatalog"),
    ("rhea", r"\brhea\b"),
]

# The same lineage walk as tools/site_data.py, so both files agree
PREFIX = {"revenue_page": "revenue", "intents_explorer": "explorer", "oneclick": "explorer", "dune_public": "dune", "nrr_fund": "bitwise"}
SEEDS = {"etf_nrr_history": "sosovalue", "dune_queries": "dune"}
manifest = json.loads(MANIFEST.read_text())


def source_id(unique_id):
    name = unique_id.split(".")[-1]
    if unique_id.startswith("seed."):
        return SEEDS.get(name, "registry")
    if name == "rpc__hos_proposals":
        return "hos"
    return PREFIX.get(name.split("__")[0], name.split("__")[0])


def roots(node, seen):
    found = set()
    for parent in manifest["parent_map"].get(node, []):
        if parent in seen or parent.endswith(".dim_date"):
            continue
        seen.add(parent)
        if parent.startswith(("source.", "seed.")):
            found.add(source_id(parent))
        else:
            found |= roots(parent, seen)
    return found


gold_nodes = {v["name"]: k for k, v in manifest["nodes"].items() if v["resource_type"] == "model" and v.get("schema", "").endswith("gold")}
lineage = {name: roots(node, set()) for name, node in gold_nodes.items()}


def named(text):
    """Source ids a piece of text names, in PATTERNS order."""
    t = text.lower().replace("_", " ")
    return [sid for sid, pat in PATTERNS if re.search(pat, t)]


def first_sentence(text):
    return re.split(r"(?<=[a-z0-9)\]])\.\s", text or "", maxsplit=1)[0]


tables = json.loads(CATALOG.read_text())
by_name = {t["table"]: t for t in tables}
direct = {}


def table_sources(name, depth=0):
    """A table's direct sources: those its catalog entry names, or those of the tables it names."""
    if name in direct:
        return direct[name]
    t = by_name[name]
    text = t.get("sources") or ""
    ids = named(text)
    for ref in re.findall(r"\b(?:fct|dim)_[a-z0-9_]+", text):
        if ref in by_name and ref != name and depth < 4:
            ids += table_sources(ref, depth + 1)
    lin = lineage.get(name, set())
    if text.strip() == "derived":
        ids = []
    elif not ids or re.search(r"gold tables|silver tables|data/bronze", text):
        ids = sorted(lin)
    kept = [i for i in dict.fromkeys(ids) if i in lin] or list(dict.fromkeys(ids))
    direct[name] = kept
    return kept


out = {}
for t in tables:
    name = t["table"]
    tsrc = table_sources(name)
    grain = [g.strip() for g in (t.get("grain") or "").split(",") if g.strip()]
    lin = lineage.get(name, set())
    cols = []
    for c in t["columns"]:
        key = c["name"] in grain or c["type"].startswith(("DATE", "TIMESTAMP"))
        own = named(c["name"]) or named(first_sentence(c.get("description")))
        own = [i for i in own if i in lin or i in tsrc]
        cols.append([c["name"], c["type"], c.get("unit") or "", c.get("description") or "", own if (own and not key and own != tsrc) else 0, 1 if key else 0])
    out[name] = {"a": t["area"], "d": t.get("description") or "", "g": grain, "n": t.get("rows"), "f": t.get("first"), "l": t.get("last"), "s": tsrc, "c": cols}
    if re.search(r"gold tables|silver tables|data/bronze", t.get("sources") or ""):
        out[name]["v"] = 1

payload = {"tables": out, "fields": sum(len(v["c"]) for v in out.values())}
OUT.write_text("window.LCAT = " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + ";\n")
print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB): {len(out)} tables, {payload['fields']} fields")
