"""Copy the pages in docs/ into a clone of the repository's wiki, for the
Sync the wiki workflow (.github/workflows/sync-wiki.yml).

Only link targets change; every other byte of a page is copied as it is,
so alerts, tables and code come through exactly:
- a link to another page loses its .md ("usage.md#x" becomes "usage#x"),
  since wiki pages have no extension;
- docs/README.md becomes the wiki's Home page, and links to it go there;
- a link out of docs/ ("../CHANGELOG.md") points at that file on GitHub,
  on the branch the wiki follows, since the wiki has no copy of it.
Links in code blocks and inline code are left alone. Everything already in
the wiki is removed first, so a page deleted from docs/ goes from the wiki
too, and a footer on every page says the wiki is a copy, edited in docs/.

Usage: python3 docs_to_wiki.py <docs folder> <wiki clone> <repository URL> <branch>
"""

import posixpath
import re
import shutil
import sys
from pathlib import Path

CODE = re.compile(r"^ *```.*?^ *```[^\n]*$|`[^`\n]*`", re.MULTILINE | re.DOTALL)
"""A fenced code block or an inline code span, whose text is left alone."""

LINK = re.compile(r"(\]\(<?)([^)\s>]+)|(^\[[^\]\n]+\]:[ \t]*<?)([^\s>]+)", re.MULTILINE)
"""A link's target, inline ("[text](target)") or in a reference definition
("[name]: target"), with what comes before it."""

FOOTER = ("This wiki is a copy of the [docs]({tree}) folder, updated with each release. "
          "To change a page, edit its file there: changes made here are overwritten.\n")
"""The wiki's footer, on every page. {tree} is the docs folder on GitHub."""


def page_name(path):
    """The wiki page for a docs file's path: its name without .md, and
    Home for README.md."""
    stem = posixpath.splitext(posixpath.basename(path))[0]
    return "Home" if stem == "README" else stem


def wiki_target(target, docs, blob):
    """target, a link in a page in the folder docs (relative to the
    repository's root), as the wiki needs it; blob is the URL files are
    linked at, e.g. "https://github.com/<owner>/<repo>/blob/master/"."""
    if target.startswith("#") or re.match(r"^[a-z][a-z+.-]*:", target):
        return target
    path, hash_, anchor = target.partition("#")
    resolved = posixpath.normpath(posixpath.join(docs, path))
    if resolved.startswith(docs + "/") and resolved.endswith(".md"):
        return page_name(resolved) + hash_ + anchor
    if resolved.startswith(docs + "/"):
        return target
    return blob + resolved + hash_ + anchor


def wiki_page(text, docs, blob):
    """text, a docs page, with its links rewritten for the wiki (see
    wiki_target()) and nothing else changed."""
    def rewrite(segment):
        return LINK.sub(lambda m: (m.group(1) or m.group(3)) + wiki_target(m.group(2) or m.group(4), docs, blob),
                        segment)
    out, last = [], 0
    for code in CODE.finditer(text):
        out += [rewrite(text[last:code.start()]), code.group()]
        last = code.end()
    return "".join([*out, rewrite(text[last:])])


def sync(docs_dir, wiki_dir, repo_url, branch):
    """Replace the contents of wiki_dir (a clone of the wiki) with the pages
    in docs_dir, the repository's docs folder, rewritten for the wiki, plus
    the footer. Files other than pages, such as images, are copied as they
    are. The wiki clone's .git is kept."""
    docs_dir, wiki_dir = Path(docs_dir), Path(wiki_dir)
    for entry in wiki_dir.iterdir():
        if entry.name == ".git":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    blob = f"{repo_url}/blob/{branch}/"
    for source in sorted(p for p in docs_dir.rglob("*") if p.is_file()):
        relative = source.relative_to(docs_dir).as_posix()
        if source.suffix == ".md":
            text = source.read_text(encoding="utf-8")
            (wiki_dir / f"{page_name(relative)}.md").write_text(wiki_page(text, docs_dir.name, blob), encoding="utf-8")
        else:
            (wiki_dir / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, wiki_dir / relative)
    (wiki_dir / "_Footer.md").write_text(FOOTER.format(tree=f"{repo_url}/tree/{branch}/{docs_dir.name}"),
                                         encoding="utf-8")


if __name__ == "__main__":
    sync(*sys.argv[1:5])
