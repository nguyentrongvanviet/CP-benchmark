"""Parse public HTML without executing scripts or treating page content as instructions."""

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .store import digest


class BlockedError(RuntimeError):
    """An access challenge, restriction, or unavailable public source. Never bypass it."""


class RobotsDisallowed(BlockedError):
    """This particular URL is disallowed by robots.txt."""


def parse_statement(html, provenance):
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".problem-statement")
    if root is None:
        raise BlockedError(
            "No problem-statement found: login/challenge, PDF-only, or markup changed"
        )

    rich_html = str(root)

    def text(selector):
        node = root.select_one(selector)
        return node.get_text("\n", strip=True) if node else None

    def pre_text(pre):
        # Codeforces uses both <br> and <div class=test-example-line> for line breaks.
        for br in pre.select("br"):
            br.replace_with("\n")
        lines = pre.select(".test-example-line")
        return "\n".join(line.get_text() for line in lines) if lines else pre.get_text()

    inputs = [pre_text(x) for x in root.select(".sample-test .input pre")]
    outputs = [pre_text(x) for x in root.select(".sample-test .output pre")]
    samples = [{"input": i, "output": o} for i, o in zip(inputs, outputs)]
    description = []
    for child in root.find_all(recursive=False):
        if not set(child.get("class", [])).intersection(
            {
                "header",
                "input-specification",
                "output-specification",
                "sample-tests",
                "note",
            }
        ):
            description.append(child.get_text("\n", strip=True))
    editorials = []
    for a in soup.select("a[href]"):
        if (
            re.search(r"editorial|tutorial", a.get_text(), re.I)
            and "/blog/entry/" in a["href"]
        ):
            url = urljoin("https://codeforces.com", a["href"])
            if url not in editorials:
                editorials.append(url)
    data = dict(
        title=text(".title"),
        rich_html=rich_html,
        description="\n\n".join(description),
        input_format=text(".input-specification"),
        output_format=text(".output-specification"),
        note=text(".note"),
        time_limit=text(".time-limit"),
        memory_limit=text(".memory-limit"),
        input_file=text(".input-file"),
        output_file=text(".output-file"),
        examples=samples,
        editorial_urls=editorials,
        source_kind="codeforces_html",
        provenance=provenance,
        interaction_detected=bool(re.search(r"\binteractive\b", root.get_text(), re.I)),
        sample_pair_mismatch=len(inputs) != len(outputs),
    )
    data["content_sha256"] = digest((data["description"] or "").encode())
    return data


def parse_source(html):
    node = BeautifulSoup(html, "html.parser").select_one("#program-source-text")
    if node is None or not node.get_text().strip():
        raise BlockedError(
            "Accepted submission exists, but its source is not publicly accessible"
        )
    return node.get_text()
