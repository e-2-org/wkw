"""
Copy the WordPress site's ordinary pages (not the names) into the Jekyll site in docs/pages/.

The pages' text is in the database as raw WordPress content, which needs WordPress's filters to
become HTML, so this reads the pages as a running copy of the site renders them (see
tools/README.md) and keeps what is inside <main>. Links are rewritten to work from the site's
base URL, images are pointed at docs/assets/img/uploads/, and the search forms use the static
search page. This only needed doing once: the pages are now edited in docs/.

Usage: python3 -I tools/import_pages.py [http://localhost:8099]
"""
import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SITE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8099"

# WordPress path -> (its file in docs/pages/, extra body classes). Each page keeps its WordPress
# URL through its permalink
PAGES = {
    "/what/": ("what.html", "wp-singular page page-id-19 what"),
    "/questions/": ("questions.html", "wp-singular page page-id-20 questions"),
    "/contact/": ("contact.html", "wp-singular page page-id-21 contact"),
    "/contact-2/": ("contact-2.html", "wp-singular page page-id-7619 contact-2"),
    "/blog/": ("blog.html", "blog"),
    "/64/": ("64.html", "wp-singular post-template-default single single-post postid-64 single-format-standard"),
    "/author/nat/": ("author-nat.html", "archive author author-nat author-1"),
    "/category/uncategorized/": ("category-uncategorized.html", "archive category category-uncategorized category-1"),
    "/nonexistent-page/": ("404.html", "error404"),
}

OLD_HOSTS = r"(?:https?://(?:culturalcartography\.net|wkw\.test|localhost:8099))"


def url(path):
    return "{{ '" + path + "' | relative_url }}"


def rewrite(main):
    # images in the uploads folder
    main = re.sub(OLD_HOSTS + r"/wp-content/uploads/\d{4}/\d{2}/([^\"' ]+)",
                  lambda m: url("/assets/img/uploads/" + m.group(1)), main)
    # the old MediaWiki site's pages became names
    main = re.sub(OLD_HOSTS + r"/wiki/index\.php\?title=([^\"&]+)",
                  lambda m: url("/names/" + re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-") + "/"), main)
    main = re.sub(OLD_HOSTS + r"(/[^\"' ]*)", lambda m: url(m.group(1)), main)
    # search forms go to the static search page
    main = re.sub(r'<form method="get" class="search-form" action="[^"]*">',
                  '<form method="get" class="search-form" action="' + url("/search/") + '">', main)
    main = main.replace('name="s"', 'name="q"')
    return main


def main():
    for path, (out, body_class) in PAGES.items():
        try:
            page = urllib.request.urlopen(SITE + path).read().decode()
        except urllib.error.HTTPError as e:  # the 404 page
            page = e.read().decode()
        title = html.unescape(re.search(r"<title>(.*?)</title>", page).group(1))
        title = title.rsplit(" – Who Knew Whom", 1)[0]
        inner = re.search(r'<main class="site-main" id="main">(.*?)</main>', page, re.S).group(1)
        inner = rewrite(inner.strip())
        front = ["---", "permalink: " + ("/404.html" if out == "404.html" else path),
                 f"title: {title!r}" if "'" not in title else f'title: "{title}"', f"body_class: {body_class}", "---"]
        f = DOCS / "pages" / out
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("\n".join(front) + "\n" + inner + "\n")
        print(out, title)


if __name__ == "__main__":
    main()
