"""MkDocs hooks for search and answer engines.

* Writes each figure's numbers into the page as ordinary tables, so readers and
  crawlers that do not run scripts still get them.
* Renders the ``faq`` list in a page's front matter as visible questions and as
  FAQPage structured data, from one source.
* Adds structured data to every page.
* Writes ``llms.txt`` and ``llms-full.txt`` into the built site.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

PEN = re.compile(r'<div class="pen" data-figure="(?P<name>\w+)"(?: data-scenarios="(?P<only>[\w,]+)")?></div>')
_pages: dict[str, dict] = {}


def on_pre_build(config, **kwargs):
    _pages.clear()


def _figure(config, name: str) -> dict:
    path = Path(config["docs_dir"]) / "assets" / "figures" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _value(value, digits: int) -> str:
    return "None" if value is None else f"{value:.{digits}f}"


def _table(head: list[str], rows: list[list[str]], cls: str = "") -> str:
    attr = f' class="{cls}"' if cls else ""
    header = "".join(f'<th scope="col">{escape(h)}</th>' for h in head)
    body = "".join(
        "<tr>" + f'<th scope="row">{escape(row[0])}</th>'
        + "".join(f"<td>{escape(cell)}</td>" for cell in row[1:]) + "</tr>"
        for row in rows
    )
    return f"<table{attr}><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def _matrix_table(data: dict) -> str:
    head = ["Mistake"] + [c["label"] for c in data["columns"]]
    rows = [[row["label"]] + [_value(row["scores"][c["key"]], c["digits"]) for c in data["columns"]]
            for row in data["rows"]]
    return _table(head, rows, "pen-static")


def _scenario_table(scenario: dict) -> str:
    control, metrics = scenario["control"], scenario["metrics"]
    labels = control.get("valueLabels")
    unit = f" ({control['unit']})" if control.get("unit") else ""
    head = [control["label"] + unit] + [m["label"] for m in metrics]
    rows = []
    for i, (value, frame) in enumerate(zip(control["values"], scenario["frames"])):
        first = labels[i] if labels else f"{value:g}"
        rows.append([first] + [_value(frame["scores"][m["key"]], m["digits"]) for m in metrics])
    return f"<p>{escape(scenario['label'])}</p>" + _table(head, rows)


def _expand_figure(match: re.Match, config) -> str:
    name, only = match["name"], match["only"]
    data = _figure(config, name)
    if name == "matrix":
        # The script replaces this table with the interactive one.
        return f'<div class="pen" data-figure="matrix">{_matrix_table(data)}</div>'
    scenarios = data["scenarios"]
    if only:
        wanted = only.split(",")
        scenarios = [s for s in scenarios if s["id"] in wanted]
    tables = "".join(_scenario_table(s) for s in scenarios)
    return (f'{match.group(0)}\n\n<details class="pen-data"><summary>Numbers behind this figure</summary>'
            f"{tables}</details>")


def on_page_markdown(markdown, page, config, files, **kwargs):
    source = markdown
    markdown = PEN.sub(lambda m: _expand_figure(m, config), markdown)
    faq = page.meta.get("faq") or []
    if faq:
        questions = "".join(f"\n### {item['q']}\n\n{item['a']}\n" for item in faq)
        markdown = f"{markdown.rstrip()}\n\n## Common questions\n{questions}"
        source = f"{source.rstrip()}\n\n## Common questions\n{questions}"
    _pages[page.file.src_uri] = {"markdown": source, "meta": page.meta}
    return markdown


def on_page_context(context, page, config, nav, **kwargs):
    site = config["site_url"]
    url = page.canonical_url or site
    title = page.meta.get("title") or page.title
    description = page.meta.get("description") or config["site_description"]
    software = {
        "@type": "SoftwareSourceCode",
        "@id": f"{site}#software",
        "name": config["site_name"],
        "description": config["site_description"],
        "url": site,
        "codeRepository": config["repo_url"],
        "programmingLanguage": ["Python", "Rust"],
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
    }
    graph: list[dict] = []
    if page.is_homepage:
        graph.append(software)
        graph.append({"@type": "WebSite", "@id": f"{site}#website", "name": config["site_name"], "url": site})
    else:
        graph.append({
            "@type": "TechArticle",
            "headline": title,
            "description": description,
            "url": url,
            "inLanguage": "en",
            "about": software,
            "isPartOf": {"@type": "WebSite", "name": config["site_name"], "url": site},
        })
        trail = [(config["site_name"], site), (title, url)]
        graph.append({
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": name, "item": item}
                for i, (name, item) in enumerate(trail, start=1)
            ],
        })
    faq = page.meta.get("faq") or []
    if faq:
        graph.append({
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": item["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
                for item in faq
            ],
        })
    text = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    # "</" would end the script element early.
    page.meta["jsonld"] = text.replace("</", "<\\/")
    return context


def on_post_build(config, **kwargs):
    site = config["site_url"]
    out = Path(config["site_dir"])

    def address(src: str) -> str:
        stem = src[: -len(".md")]
        return site if stem == "index" else f"{site}{stem}/"

    order = ["index.md", "getting-started.md", "penalties.md", "choosing-metrics.md"]
    names = order + sorted(set(_pages) - set(order))
    names = [n for n in names if n in _pages]

    index = [f"# {config['site_name']}", "", f"> {config['site_description']}", "", "## Documentation", ""]
    full = [f"# {config['site_name']} documentation", ""]
    for name in names:
        meta = _pages[name]["meta"]
        title = meta.get("title") or name
        index.append(f"- [{title}]({address(name)}): {meta.get('description', '')}")
        body = PEN.sub("", _pages[name]["markdown"]).strip()
        full += [f"<!-- {address(name)} -->", "", body, ""]
    # The comparison is the most quotable thing on the site: give its numbers as text.
    data = _figure(config, "matrix")
    head = ["Mistake"] + [c["label"] for c in data["columns"]]
    table = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    for row in data["rows"]:
        cells = [_value(row["scores"][c["key"]], c["digits"]) for c in data["columns"]]
        table.append("| " + " | ".join([row["label"], *cells]) + " |")
    full += ["## Penalty comparison, computed by the library", "", *table, ""]
    (out / "llms.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    (out / "llms-full.txt").write_text("\n".join(full), encoding="utf-8")
