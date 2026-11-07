"""Checks that every link in the project's Markdown leads somewhere: the
README, the pages in docs/, the changelog and the files in .github. A
relative link must name a file that exists, and an #anchor must match a
heading in it, by the rules GitHub uses to make a heading's anchor. Links
to this repository's own files on GitHub, as in the issue forms and the
script's --help, must name a file that exists here too. Pure Python, so
it runs wherever the logic tests do."""

import importlib.util
import re
import unicodedata
from pathlib import Path
from types import ModuleType
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parent.parent
"""The repository's root folder."""


def load_docs_to_wiki() -> ModuleType:
    """.github/scripts/docs_to_wiki.py, which copies docs/ into the wiki, as a
    module: it's a script, not part of a package."""
    spec = importlib.util.spec_from_file_location("docs_to_wiki", ROOT / ".github" / "scripts" / "docs_to_wiki.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


docs_to_wiki = load_docs_to_wiki()
"""The wiki sync script, whose output is checked below like the docs."""

REPO = "https://github.com/tronyx/tronitor"
"""This repository on GitHub."""

BLOB = f"{REPO}/blob/master/"
"""Where the wiki's links out of docs/ point: files on master."""

REPO_URL = re.compile(r"https://github\.com/tronyx/tronitor/(?:blob|tree)/[^/\s]+/([^\s)\"'#]+)(#[^\s)\"']+)?")
"""A link to one of this repository's files on GitHub, on any branch: the
file's path, and its #anchor if it has one."""


def markdown_files(root: Path) -> list[Path]:
    """Every Markdown file of the project under root, but not the ones in
    a virtual environment or other folder a contributor may have added."""
    found = [root / name for name in ("README.md", "CHANGELOG.md", "LICENSE.md")]
    found += sorted((root / "docs").glob("**/*.md")) + sorted((root / ".github").glob("**/*.md"))
    return [path for path in found if path.is_file()]


def files_linking_to_the_repo(root: Path) -> list[Path]:
    """The files besides Markdown that link to this repository's files on
    GitHub: the issue forms, and the script, whose --help ends with one."""
    return sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.yml")) + [root / "tronitor.py"]


def without_code(text: str) -> str:
    """text with its fenced code blocks and inline code removed, since
    neither holds links or headings."""
    text = re.sub(r"^ *```.*?^ *```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def github_slug(heading: str) -> str:
    r"""The anchor GitHub gives a heading: lowercased, with letters, marks,
    numbers, "-" and "_" kept, spaces turned into hyphens, and everything
    else dropped, emoji included. An emoji's variation selector (U+FE0F)
    is a mark, so it stays: "⚙️ Configuration" becomes "️-configuration"."""
    kept = []
    for char in heading.strip().lower():
        if char == " ":
            kept.append("-")
        elif char in "-_" or unicodedata.category(char)[0] in "LMN":
            kept.append(char)
    return "".join(kept)


def anchors(path: Path) -> set[str]:
    """The anchors of every heading in the Markdown file at path. A
    repeated heading gets "-1", "-2" and so on, as on GitHub."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    for heading in re.findall(r"^#{1,6} +(.+?) *#* *$", without_code(path.read_text(encoding="utf-8")), re.MULTILINE):
        slug = github_slug(heading)
        count = seen.get(slug, 0)
        found.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return found


def problem_with(source: Path, root: Path, target_path: str, anchor: str) -> str | None:
    """Why a link from the file source to target_path (relative to root if
    it starts with "/", else to source's folder) with anchor ("" for none)
    leads nowhere, or None if it's fine."""
    target = (root / target_path.lstrip("/")) if target_path.startswith("/") else (source.parent / target_path)
    target = target.resolve() if target_path else source
    if not target.exists():
        return f"{target_path} doesn't exist"
    if anchor and target.suffix == ".md" and unquote(anchor) not in anchors(target):
        return f"{target_path or source.name} has no heading for #{anchor}"
    return None


def broken_links(root: Path) -> list[str]:
    """Every link under root that leads nowhere, as "file: link: why"."""
    problems = []
    for source in markdown_files(root):
        text = without_code(source.read_text(encoding="utf-8"))
        links = re.findall(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)", text)
        links += re.findall(r"^\[[^\]]+\]:\s*(\S+)", text, re.MULTILINE)
        for link in links:
            if re.match(r"^[a-z][a-z+.-]*:", link):
                continue
            path, _, anchor = link.partition("#")
            why = problem_with(source, root, unquote(path), anchor)
            if why:
                problems.append(f"{source.relative_to(root)}: {link}: {why}")
    for source in markdown_files(root) + files_linking_to_the_repo(root):
        for path, anchor in REPO_URL.findall(source.read_text(encoding="utf-8")):
            why = problem_with(source, root, "/" + path, anchor.lstrip("#"))
            if why:
                problems.append(f"{source.relative_to(root)}: {path}{anchor}: {why}")
    return problems


@pytest.mark.parametrize("heading, anchor", [
    ("🩺 Troubleshooting", "-troubleshooting"),
    ("⚙️ Configuration", "️-configuration"),
    ("⏰ Running from cron", "-running-from-cron"),
    ("📂 lock_dir on self-hosted servers (tronitor.toml)", "-lock_dir-on-self-hosted-servers-tronitortoml"),
], ids=["emoji dropped", "variation selector kept", "spaces become hyphens", "underscore and hyphen kept"])
def test_headings_get_the_anchors_github_gives_them(heading: str, anchor: str) -> None:
    """Headings of the kind this project's docs use, with the anchor GitHub
    gives each one: the emoji is dropped, but an emoji's variation selector
    (an invisible U+FE0F at the start of the second anchor) stays, spaces
    become hyphens, "_" and "-" stay, and other punctuation is dropped."""
    assert github_slug(heading) == anchor


def test_every_link_in_the_docs_leads_somewhere() -> None:
    """A page moved or renamed, or a heading reworded, breaks the links to
    it without a word, so every link is followed here instead."""
    assert broken_links(ROOT) == []


@pytest.mark.parametrize("target, expected", [
    ("usage.md#%EF%B8%8F-all-options", "usage#%EF%B8%8F-all-options"),
    ("./configuration.md", "configuration"),
    ("README.md", "Home"),
    ("../README.md", f"{BLOB}README.md"),
    ("../.github/CONTRIBUTING.md#%EF%B8%8F-making-a-change",
     f"{BLOB}.github/CONTRIBUTING.md#%EF%B8%8F-making-a-change"),
    ("../tests/test_docs.py", f"{BLOB}tests/test_docs.py"),
    ("#-troubleshooting", "#-troubleshooting"),
    ("https://example.com/notes.md", "https://example.com/notes.md"),
    ("images/shot.png", "images/shot.png"),
], ids=["page with anchor", "page in this folder", "the index", "out of docs", "out of docs with anchor",
        "not a page", "same page", "elsewhere", "image next to the pages"])
def test_wiki_links_lead_where_the_docs_links_do(target: str, expected: str) -> None:
    """A page link loses its .md, since wiki pages have none; the index is
    the wiki's Home; a link out of docs/ goes to the file on GitHub, since
    the wiki has no copy; the rest stay as they are."""
    assert docs_to_wiki.wiki_target(target, "docs", BLOB) == expected


def test_only_the_link_targets_change_in_a_wiki_page() -> None:
    """Alerts, tables, code and every other byte come through exactly;
    links in code are left alone."""
    page = (
        "# Title\n\n"
        "> [!NOTE]\n> See [usage](usage.md#x) and [the log](../CHANGELOG.md \"what's new\").\n\n"
        "| Page | Link |\n| --- | --- |\n| Home | [index](README.md) |\n\n"
        "```text\n[not a link](usage.md)\n```\n\n"
        "Inline `[code](cron.md)` stays, [ref][1] too.\n\n"
        "[1]: cron.md#-running-from-cron\n"
    )

    assert docs_to_wiki.wiki_page(page, "docs", BLOB) == (
        "# Title\n\n"
        f"> [!NOTE]\n> See [usage](usage#x) and [the log]({BLOB}CHANGELOG.md \"what's new\").\n\n"
        "| Page | Link |\n| --- | --- |\n| Home | [index](Home) |\n\n"
        "```text\n[not a link](usage.md)\n```\n\n"
        "Inline `[code](cron.md)` stays, [ref][1] too.\n\n"
        "[1]: cron#-running-from-cron\n"
    )


def test_the_wiki_copy_of_the_docs_has_no_broken_links(tmp_path: Path) -> None:
    """The real docs/, as the wiki gets it: the index becomes Home, a page
    no longer in docs/ is removed from the wiki but its .git is kept, every
    page has the same text but for its link targets, and every link leads
    to a wiki page and heading that exist, or to a file that exists here."""
    wiki = tmp_path / "wiki"
    (wiki / ".git").mkdir(parents=True)
    (wiki / ".git" / "HEAD").write_text("ref: refs/heads/master\n", encoding="utf-8")
    (wiki / "Old-page.md").write_text("# Gone from docs/\n", encoding="utf-8")

    docs_to_wiki.sync(ROOT / "docs", wiki, REPO, "master")

    pages = {p.name for p in wiki.glob("*.md")}
    docs = {"Home.md" if p.name == "README.md" else p.name for p in (ROOT / "docs").glob("*.md")}
    assert pages == docs | {"_Footer.md"}
    assert (wiki / ".git" / "HEAD").exists()
    problems = []
    for source in sorted((ROOT / "docs").glob("*.md")):
        copy = wiki / ("Home.md" if source.name == "README.md" else source.name)
        text, original = copy.read_text(encoding="utf-8"), source.read_text(encoding="utf-8")
        targets = re.compile(r"\]\(<?[^)\s>]+")
        assert targets.sub("](", text) == targets.sub("](", original), f"{copy.name} changed beyond its links"
        for link in re.findall(r"\]\(<?([^)\s>]+)", without_code(text)):
            if link.startswith(BLOB):
                path, _, anchor = link[len(BLOB):].partition("#")
                why = problem_with(source, ROOT, "/" + path, anchor)
            elif re.match(r"^[a-z][a-z+.-]*:", link):
                continue
            else:
                page, _, anchor = link.partition("#")
                why = problem_with(copy, wiki, (page + ".md") if page else "", anchor)
            if why:
                problems.append(f"{copy.name}: {link}: {why}")
    assert problems == []
    assert f"{REPO}/tree/master/docs" in (wiki / "_Footer.md").read_text(encoding="utf-8")


def test_a_broken_link_is_found(tmp_path: Path) -> None:
    """The check itself: a missing file, a missing heading, a link to a
    repeated heading that has no second copy, and a link to this
    repository on GitHub naming a missing file are each reported; the
    links that are fine, a link in a code block, and links elsewhere
    aren't."""
    (tmp_path / "docs").mkdir()
    (tmp_path / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
    (tmp_path / "tronitor.py").write_text('"""Full guide: https://example.com"""\n', encoding="utf-8")
    (tmp_path / "docs" / "page.md").write_text("# 📄 Page\n\n## ⚙️ Options\n\n## Twice\n\n## Twice\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Read me\n\n"
        "[fine](docs/page.md#%EF%B8%8F-options) [fine](docs/page.md#twice-1) [fine](#read-me)\n"
        "[gone](docs/missing.md) [no heading](docs/page.md#-optionz) [no third](docs/page.md#twice-2)\n"
        "[elsewhere](https://example.com/x.md#y)\n\n"
        "```text\n[in code](nowhere.md)\n```\n",
        encoding="utf-8")
    (tmp_path / ".github" / "ISSUE_TEMPLATE" / "bug.yml").write_text(
        "url: https://github.com/tronyx/tronitor/blob/master/docs/page.md#-page\n"
        "other: https://github.com/tronyx/tronitor/blob/master/docs/gone.md\n",
        encoding="utf-8")

    problems = broken_links(tmp_path)

    assert [p.replace("\\", "/") for p in problems] == [
        "README.md: docs/missing.md: docs/missing.md doesn't exist",
        "README.md: docs/page.md#-optionz: docs/page.md has no heading for #-optionz",
        "README.md: docs/page.md#twice-2: docs/page.md has no heading for #twice-2",
        ".github/ISSUE_TEMPLATE/bug.yml: docs/gone.md: /docs/gone.md doesn't exist",
    ]
