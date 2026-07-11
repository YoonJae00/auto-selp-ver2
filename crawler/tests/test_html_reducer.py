from __future__ import annotations

from bs4 import BeautifulSoup

from app.analyzer.html_reducer import reduce_html


def test_reduce_html_removes_scripts_and_styles() -> None:
    html = '<html><body><script>alert(1)</script><style>.x{}</style><p>hello</p></body></html>'
    result = reduce_html(html)
    assert "script" not in result.lower()
    assert "style" not in result.lower() or "style" not in result
    assert "hello" in result


def test_reduce_html_removes_inline_styles() -> None:
    html = '<div style="color:red">text</div>'
    result = reduce_html(html)
    assert "color:red" not in result
    assert "text" in result


def test_reduce_html_truncates_long_text() -> None:
    long_text = "A" * 200
    html = f"<p>{long_text}</p>"
    result = reduce_html(html)
    assert "…" in result
    assert "A" * 200 not in result


def test_reduce_html_preserves_structure() -> None:
    html = '<div class="product"><h2 class="name">상품명</h2><span class="price">1000</span></div>'
    result = reduce_html(html)
    soup = BeautifulSoup(result, "html.parser")
    assert soup.find("h2", class_="name") is not None
    assert soup.find("span", class_="price") is not None


def test_reduce_html_compresses_repeated() -> None:
    html = '<ul>' + ''.join(f'<li class="item">item{i}</li>' for i in range(10)) + '</ul>'
    result = reduce_html(html)
    assert "omitted" in result.lower()
    assert result.count('<li class="item">') <= 2


def test_reduce_html_empty_input() -> None:
    assert reduce_html("") == ""


def test_reduce_html_removes_comments() -> None:
    html = '<div><!-- comment --><p>text</p></div>'
    result = reduce_html(html)
    assert "comment" not in result
    assert "text" in result


def test_reduce_html_preserves_classes_and_ids() -> None:
    html = '<div class="container" id="main" data-custom="yes">text</div>'
    result = reduce_html(html)
    assert 'class="container"' in result
    assert 'id="main"' in result
    assert "data-custom" not in result


def test_reduce_html_keeps_mapping_inputs_and_buttons() -> None:
    html = '<input type="hidden" name="maxq" value="0"><button class="buy">구매</button>'
    result = reduce_html(html)
    assert 'name="maxq"' in result
    assert 'value="0"' in result
    assert '<button class="buy"' in result
    assert "구매" in result


def test_reduce_html_strips_sensitive_input_values() -> None:
    html = '<input type="hidden" name="csrf_token" value="secret"><input type="password" name="pw" value="1234">'
    result = reduce_html(html)
    assert "csrf_token" in result
    assert "secret" not in result
    assert "1234" not in result


def test_reduce_html_keeps_empty_select_and_textarea() -> None:
    html = '<select name="opt"></select><textarea name="memo"></textarea>'
    result = reduce_html(html)
    assert 'name="opt"' in result
    assert 'name="memo"' in result


def test_reduce_html_drop_chrome_removes_frame_tags() -> None:
    html = (
        '<header><nav class="gnb">메뉴</nav></header>'
        '<main><div class="product">상품</div></main>'
        '<aside>사이드</aside><footer>푸터</footer>'
    )
    result = reduce_html(html, drop_chrome=True)
    assert "메뉴" not in result
    assert "사이드" not in result
    assert "푸터" not in result
    assert "상품" in result


def test_reduce_html_keeps_chrome_by_default() -> None:
    html = '<header>헤더</header><div class="product">상품</div>'
    result = reduce_html(html)
    assert "헤더" in result
    assert "상품" in result
