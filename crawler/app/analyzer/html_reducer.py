from __future__ import annotations

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


_STRIP_TAGS = {"script", "style", "svg", "noscript", "iframe", "link", "meta", "input", "button"}
_MAX_TEXT_CHARS = 80
_MAX_REPEATED = 2


def reduce_html(html: str, max_text_chars: int = _MAX_TEXT_CHARS, max_repeated: int = _MAX_REPEATED) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(attrs={"style": True}):
        del tag["style"]

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr not in ("class", "id", "href", "src", "data-src", "name", "type", "value", "selected", "checked", "action", "method"):
                del tag[attr]

    _truncate_text(soup, max_text_chars)
    _collapse_empty(soup)
    _compress_repeated(soup, max_repeated)

    return str(soup)


def _truncate_text(soup: BeautifulSoup, max_chars: int) -> None:
    for tag in soup.find_all(True):
        if tag.name in ("a", "option", "td", "th", "span", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "strong", "em", "label"):
            for child in list(tag.children):
                if isinstance(child, NavigableString) and not isinstance(child, Comment):
                    text = str(child).strip()
                    if len(text) > max_chars:
                        child.replace_with(NavigableString(text[:max_chars] + "…"))


def _collapse_empty(soup: BeautifulSoup) -> None:
    changed = True
    while changed:
        changed = False
        for tag in soup.find_all(True):
            children = [c for c in tag.children if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]
            if not children and tag.name not in ("br", "hr", "img"):
                tag.decompose()
                changed = True


def _compress_repeated(soup: BeautifulSoup, max_repeated: int) -> None:
    for parent in soup.find_all(True):
        children = [c for c in parent.children if isinstance(c, Tag)]
        if len(children) <= max_repeated:
            continue
        groups: dict[str, list[Tag]] = {}
        for child in children:
            cls = " ".join(child.get("class", []))
            key = f"{child.name}.{cls}"
            groups.setdefault(key, []).append(child)
        for key, group in groups.items():
            if len(group) > max_repeated:
                omitted = len(group) - max_repeated
                for extra in group[max_repeated:]:
                    extra.replace_with(Comment(f" [{omitted} more {key} omitted] "))
