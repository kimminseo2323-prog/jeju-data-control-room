"""화면 꾸밈 조각(style.py)의 HTML."""
from app.ui import style


def test_key_html_draws_line_and_dot_swatches():
    html = style.key_html([("line:#111111", "실제"), ("dot:#DA1E28", "평소보다 많은 날"), ("#E0E0E0", "이상 없음")])
    assert '<i class="ln" style="background:#111111">' in html
    assert '<i class="dot" style="background:#DA1E28">' in html
    assert '<i style="background:#E0E0E0">' in html and html.count('class="jj-key"') == 3
