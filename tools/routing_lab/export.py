# SPDX-License-Identifier: MIT
"""One battery run as a single HTML file that opens anywhere and asks nothing.

The file is the page (index.html with lab.css and lab.js inlined) plus
window.LAB_STATIC = {info, run, cases, rank, when}: what the server would have
answered. It carries no token, no path under the home directory, and not the
KiCad sheet backdrop (10 MB); the sheet tab says so.
"""
import json
import os
import shutil
import time
from pathlib import Path

import arrangement
import ceiling
import fabric_view
import lab
import runner
import server
import variants


def page(static):
    """The page with its style, its script and its data inlined."""
    data = json.dumps(static, ensure_ascii=False)           # as written, so a home path with an accent is found
    data = data.replace(str(Path.home()), "~")              # e.g. a sanitizer trace naming the build directory
    data = data.replace("<", "\\u003c")                     # report text cannot close the script or open a comment
    html = (server.WEB_DIR / "index.html").read_text(encoding="utf-8")
    for tag, inline in (
            ('<link rel="stylesheet" href="lab.css">',
             "<style>\n%s</style>" % (server.WEB_DIR / "lab.css").read_text(encoding="utf-8")),
            ('<script>window.LAB_TOKEN = "__LAB_TOKEN__";</script>', "<script>window.LAB_STATIC = %s;\n</script>" % data),
            ('<script src="lab.js"></script>',
             "<script>\n%s</script>" % (server.WEB_DIR / "lab.js").read_text(encoding="utf-8"))):
        if tag not in html:
            raise ValueError("index.html no longer has %s; export.py must follow it" % tag)
        html = html.replace(tag, inline)
    return html


def _shown_name(name):
    """A variant named by a directory is shown by the directory's last part."""
    path = Path(name).expanduser()
    return path.resolve().name if os.sep in name and path.is_dir() else name


def write(path, variant_spec, baseline_spec=None, classes=("dense", "real", "stress", "beyond", "edge"),
          arrangement_name="v5", backdrop=None):
    """Runs the battery on an arrangement the firmware's router can route and
    writes the file; returns its size in bytes. The page is drawn on that
    arrangement's copper and lists no other, and carries the ranking kept for
    the variant on it when there is one ("rank", else None).

    With `backdrop` (a file name) the page has the KiCad sheet too: its data
    travels in the page ("sheet"), and the built backdrop is copied beside the
    page under that name, for the page to fetch when the sheet tab is opened.
    ValueError when the name is not a plain file name or the sheet is not built."""
    sheet_data = None
    if backdrop is not None:
        if not backdrop or Path(backdrop).name != backdrop:
            raise ValueError("the backdrop is a file name beside the page, not %r" % backdrop)
        built = server.SHEET_DIR / "backdrop.svg"
        overlay = server.SHEET_DIR / "overlay.json"
        if not (built.is_file() and overlay.is_file()):
            raise ValueError("the KiCad sheet has not been built: python3 tools/routing_lab/lab.py sheet")
        sheet_data = json.loads(overlay.read_text())
    case_list = lab.battery(list(classes))
    a = arrangement.load(arrangement_name)
    v = variants.resolve(variant_spec)
    results = runner.run_battery(v, case_list, arrangement=a)
    base_v = base = None
    if baseline_spec:
        base_v = variants.resolve(baseline_spec)
        base = runner.run_battery(base_v, case_list, arrangement=a)
    run = server.run_answer(v, results, base_v, base, a)
    for which in (run["variant"], run["baseline"]):
        if which:
            which["name"] = _shown_name(which["name"])
    info = dict(server.info(), sheet=sheet_data is not None, variants=[], solver=False, fabric=fabric_view.layout(a),
                nodes=server.nodes_of(a), pins=server.pins_of(a), arrangements=[server.arrangement_row(a)])
    ranking = server.ranking_on_file(v, a)
    if ranking:
        ranking["variant"] = run["variant"]         # the same router (it is found by its hash), under the name the page shows
    html = page({"info": info, "run": run, "when": time.strftime("%Y-%m-%d"), "rank": ranking,
                 "sheet": sheet_data, "backdrop": backdrop,
                 "cases": {r["case"]: {"result": r, "paint": ceiling.painted(r, a)} for r in results}})
    if backdrop:
        shutil.copyfile(server.SHEET_DIR / "backdrop.svg", Path(path).parent / backdrop)
    Path(path).write_text(html, encoding="utf-8")
    return len(html.encode())
