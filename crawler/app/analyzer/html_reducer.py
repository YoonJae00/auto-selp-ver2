from __future__ import annotations

from bs4 import BeautifulSoup, Comment, NavigableString, Tag


_STRIP_TAGS = {"script", "style", "svg", "noscript", "iframe", "link", "meta"}
# 크롬(사이트 공통 프레임) 태그 — drop_chrome=True일 때만 태그명 기준으로 제거.
# 클래스 매칭은 오탐 위험이 커서 하지 않는다. 카테고리는 nav 안에 있으므로
# 카테고리 축소에는 drop_chrome를 쓰지 않는다.
_CHROME_TAGS = {"header", "footer", "nav", "aside"}
_MAX_TEXT_CHARS = 80
_MAX_REPEATED = 2
# 자식 없이도 보존할 태그 — void/폼 입력 요소는 LLM이 로그인 폼·hidden 상품코드·
# maxq 품절지표를 보려면 남아 있어야 한다.
_KEEP_EMPTY_TAGS = ("br", "hr", "img", "input", "textarea", "select")


def reduce_html(
    html: str,
    max_text_chars: int = _MAX_TEXT_CHARS,
    max_repeated: int = _MAX_REPEATED,
    drop_chrome: bool = False,
) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()

    if drop_chrome:
        for tag in soup(list(_CHROME_TAGS)):
            tag.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(attrs={"style": True}):
        del tag["style"]

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr not in ("class", "id", "href", "src", "data-src", "name", "type", "value", "selected", "checked", "action", "method"):
                del tag[attr]
        if tag.name == "input" and tag.has_attr("value") and _is_sensitive_input(tag):
            del tag["value"]

    _truncate_text(soup, max_text_chars)
    _collapse_empty(soup)
    _compress_repeated(soup, max_repeated)

    return str(soup)


def _is_sensitive_input(tag: Tag) -> bool:
    input_type = str(tag.get("type") or "").strip().lower()
    identity = " ".join(
        str(tag.get(attr) or "") for attr in ("name", "id", "class")
    ).lower()
    return input_type == "password" or any(
        marker in identity
        for marker in ("token", "csrf", "auth", "pass", "pwd", "secret", "session")
    )


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
            if not children and tag.name not in _KEEP_EMPTY_TAGS:
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
