import re
import unicodedata
from collections.abc import Iterable


MAX_TOKENS = 9
MAX_LENGTH = 50


def _tokens(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[_\W]+", " ", value, flags=re.UNICODE)
    return tuple(value.split())


def _fits(tokens: tuple[str, ...] | list[str]) -> bool:
    return (
        bool(tokens)
        and len(tokens) <= MAX_TOKENS
        and len(" ".join(tokens)) <= MAX_LENGTH
        and all(sum(item.casefold() == token.casefold() for item in tokens) <= 2 for token in tokens)
    )


def _overlap(left: list[str], right: tuple[str, ...]) -> int:
    for size in range(min(len(left), len(right)), 0, -1):
        if tuple(token.casefold() for token in left[-size:]) == tuple(token.casefold() for token in right[:size]):
            return size
    return 0


def _without_brand(tokens: tuple[str, ...], brand_tokens: tuple[str, ...]) -> tuple[str, ...]:
    brand = {token.casefold() for token in brand_tokens}
    result: list[str] = []
    for token in tokens:
        if token.casefold() not in brand and sum(item.casefold() == token.casefold() for item in result) < 2:
            result.append(token)
    return tuple(result)


def _fallback(brand_tokens: tuple[str, ...], *values: object) -> str:
    for value in values:
        tokens = _without_brand(_tokens(value), brand_tokens)
        if tokens:
            result: list[str] = []
            for token in tokens:
                if _fits([*result, token]):
                    result.append(token)
                else:
                    break
            if result:
                return " ".join(result)
    return ""


def generate_product_name(
    keywords: Iterable[object] | None,
    refined_name: object,
    brand_name: object = None,
    original_name: object = None,
) -> str:
    """Build a deterministic, bounded Smartstore name from verified keywords."""
    brand_tokens = _tokens(brand_name)
    candidates: list[tuple[int, tuple[str, ...]]] = []
    for index, keyword in enumerate(keywords or []):
        candidate = _without_brand(_tokens(keyword), brand_tokens)
        if not candidate:
            continue
        if any(_contains(previous, candidate) for _, previous in candidates):
            continue
        candidates.append((index, candidate))

    chain: list[str] = []
    remaining: list[tuple[int, tuple[str, ...]]] = []
    for index, candidate in candidates:
        if not chain and _fits(candidate):
            chain = list(candidate)
        else:
            remaining.append((index, candidate))

    while chain and remaining:
        choices: list[tuple[int, bool, int, tuple[str, ...], list[str]]] = []
        for index, candidate in remaining:
            append_overlap = _overlap(chain, candidate)
            append = [*chain, *candidate[append_overlap:]]
            if append_overlap and _fits(append):
                choices.append((append_overlap, True, index, candidate, append))

            prepend_overlap = _overlap(list(candidate), tuple(chain))
            prepend = [*candidate[:-prepend_overlap], *chain]
            if prepend_overlap and _fits(prepend):
                choices.append((prepend_overlap, False, index, candidate, prepend))

        if choices:
            _, _, index, candidate, chain = max(
                choices, key=lambda choice: (choice[0], choice[1], -choice[2])
            )
            remaining.remove((index, candidate))
            continue

        index, candidate = remaining.pop(0)
        proposed = [*chain, *candidate]
        if _fits(proposed):
            chain = proposed

    return " ".join(chain) if chain else _fallback(brand_tokens, refined_name, original_name)


def _contains(container: tuple[str, ...], candidate: tuple[str, ...]) -> bool:
    width = len(candidate)
    candidate_folded = tuple(token.casefold() for token in candidate)
    return any(
        tuple(token.casefold() for token in container[index:index + width]) == candidate_folded
        for index in range(len(container) - width + 1)
    )
