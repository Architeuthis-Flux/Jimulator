# SPDX-License-Identifier: MIT
"""One battery run as a single HTML file that opens anywhere and asks nothing.

The file is the page (index.html with lab.css and lab.js inlined) plus
window.LAB_STATIC = {info, run, cases, when}: what the server would have
answered. It carries no token, no path under the home directory, and not the
KiCad sheet backdrop (10 MB); the sheet tab says so.
"""
import json
import os
import time
from pathlib import Path

import ceiling
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


def write(path, variant_spec, baseline_spec=None, classes=("dense", "real", "stress", "beyond", "edge")):
    """Runs the battery and writes the file; returns its size in bytes."""
    case_list = lab.battery(list(classes))
    v = variants.resolve(variant_spec)
    results = runner.run_battery(v, case_list)
    base_v = base = None
    if baseline_spec:
        base_v = variants.resolve(baseline_spec)
        base = runner.run_battery(base_v, case_list)
    run = server.run_answer(v, results, base_v, base)
    for which in (run["variant"], run["baseline"]):
        if which:
            which["name"] = _shown_name(which["name"])
    info = dict(server.info(), sheet=False, variants=[], solver=False)
    html = page({"info": info, "run": run, "when": time.strftime("%Y-%m-%d"),
                 "cases": {r["case"]: {"result": r, "paint": ceiling.painted(r)} for r in results}})
    Path(path).write_text(html, encoding="utf-8")
    return len(html.encode())
