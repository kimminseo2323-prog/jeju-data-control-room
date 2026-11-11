"""결과 설명서 PDF 만들기: docs/결과_설명서.md → HTML(pandoc) → PDF(Edge 헤드리스 인쇄).

실행: python docs/_build/build_results.py
결과: docs/결과_설명서.pdf (A4). 원본은 Markdown이며, PDF는 읽기 편하도록 만든 사본이다.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
SRC, OUT = DOCS / "결과_설명서.md", DOCS / "결과_설명서.pdf"
BROWSERS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")]
CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: 'Malgun Gothic', sans-serif; font-size: 10pt; line-height: 1.55; color: #1f2a37; max-width: none; margin: 0; }
h1 { color: #1F3A5F; font-size: 19pt; border-bottom: 3px solid #1F3A5F; padding-bottom: 4px; margin: 0 0 8px; }
h2 { color: #1F3A5F; font-size: 13.5pt; border-left: 5px solid #2A7F7F; padding-left: 8px; margin: 18px 0 6px; page-break-after: avoid; }
h3 { color: #2A7F7F; font-size: 11pt; margin: 12px 0 4px; page-break-after: avoid; }
p, li { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 8px; font-size: 9pt; page-break-inside: avoid; }
th { background: #1F3A5F; color: #fff; font-weight: 600; }
th, td { border: 1px solid #cfd8e3; padding: 3px 6px; vertical-align: top; word-break: keep-all; }
tr:nth-child(even) td { background: #f5f8fa; }
blockquote { margin: 6px 0; padding: 6px 10px; background: #E8F1F1; border-left: 4px solid #2A7F7F; color: #1f2a37; }
pre { background: #f5f3ee; border: 1px solid #e3ddd0; padding: 6px 8px; font-size: 8.3pt; line-height: 1.45; white-space: pre-wrap; page-break-inside: avoid; }
code { font-family: Consolas, 'Malgun Gothic', monospace; font-size: 8.8pt; }
img { display: block; max-width: 100%; max-height: 105mm; margin: 6px auto; border: 1px solid #dde3ea; }
p:has(> img) { page-break-inside: avoid; }
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        css = Path(tmp) / "style.css"
        css.write_text(CSS, "utf-8")
        html = DOCS / "_결과_설명서_tmp.html"   # 이미지 상대경로(images/) 때문에 docs 폴더에 잠깐 만든다
        try:
            subprocess.run(["pandoc", str(SRC), "-f", "gfm", "-t", "html5", "-s", "--metadata", "title=결과 설명서 — 제주 데이터 관제실",
                            "--css", str(css), "--self-contained", "-o", str(html)], cwd=DOCS, check=True)
            # pandoc이 메타데이터 제목을 본문 위에 한 번 더 넣으므로 숨긴다(본문 첫 줄이 제목)
            t = html.read_text("utf-8").replace('<header id="title-block-header">', '<header id="title-block-header" style="display:none">')
            html.write_text(t, "utf-8")
            exe = next(b for b in BROWSERS if b.exists())
            subprocess.run([str(exe), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={OUT}",
                            html.as_uri()], check=True, timeout=120)
        finally:
            html.unlink(missing_ok=True)
    print(OUT)


if __name__ == "__main__":
    main()
