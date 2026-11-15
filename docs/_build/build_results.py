"""결과 설명서 PDF 만들기: docs/결과_설명서.md → HTML(pandoc) → PDF(Edge 헤드리스 인쇄).

실행: python docs/_build/build_results.py [docs/설치_실행_매뉴얼.md ...]   (인자가 없으면 결과 설명서)
결과: docs/결과_설명서.pdf (A4). 원본은 Markdown이며, PDF는 읽기 편하도록 만든 사본이다.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
SRC, OUT = DOCS / "결과_설명서.md", DOCS / "결과_설명서.pdf"
BROWSERS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")]
FONTS = DOCS.parent / "app" / "ui" / "static" / "fonts"   # 화면과 같은 글꼴(IBM Plex Sans KR, OFL)
# 디자인 기준: docs/디자인_기준.md — 각진 면, 먹색·회색 단계, 감귤색은 강조 막대에만
CSS = """
@font-face { font-family: 'Plex KR'; font-weight: 300; src: url('FONTDIR/IBMPlexSansKR-Light.woff2') format('woff2'); }
@font-face { font-family: 'Plex KR'; font-weight: 400; src: url('FONTDIR/IBMPlexSansKR-Regular.woff2') format('woff2'); }
@font-face { font-family: 'Plex KR'; font-weight: 600 700; src: url('FONTDIR/IBMPlexSansKR-SemiBold.woff2') format('woff2'); }
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: 'Plex KR', 'Malgun Gothic', sans-serif; font-size: 9.6pt; line-height: 1.6; color: #161616; max-width: none; margin: 0; letter-spacing: 0.1px; }
strong, b { font-weight: 600; }
h1 { color: #FFFFFF; background: #161616; font-size: 18pt; font-weight: 300; padding: 10px 14px; margin: 0 0 10px; }
h2 { color: #161616; font-size: 13pt; font-weight: 600; border-top: 3px solid #E8630A; padding-top: 5px; margin: 18px 0 6px; page-break-after: avoid; }
h3 { color: #161616; font-size: 10.6pt; font-weight: 600; margin: 12px 0 4px; page-break-after: avoid; }
p, li { margin: 3px 0; }
a { color: #0043CE; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 8px; font-size: 8.8pt; page-break-inside: avoid; }
th { background: #E0E0E0; color: #161616; font-weight: 600; text-align: left; }
th, td { border: 1px solid #C6C6C6; padding: 3px 6px; vertical-align: top; word-break: keep-all; }
tr:nth-child(even) td { background: #F4F4F4; }
blockquote { margin: 6px 0; padding: 6px 10px; background: #F4F4F4; border-left: 4px solid #E8630A; color: #161616; }
pre { background: #F4F4F4; border: 1px solid #E0E0E0; padding: 6px 8px; font-size: 8.2pt; line-height: 1.45; white-space: pre-wrap; page-break-inside: avoid; }
code { font-family: Consolas, 'Plex KR', 'Malgun Gothic', monospace; font-size: 8.6pt; }
img { display: block; max-width: 100%; max-height: 105mm; margin: 6px auto; border: 1px solid #E0E0E0; }
p:has(> img) { page-break-inside: avoid; }
""".replace("FONTDIR/", "")   # 글꼴은 style.css 옆(임시 폴더)에 복사해 두고 pandoc이 HTML 안에 넣는다


def main(src: Path = SRC, out: Path = OUT):
    with tempfile.TemporaryDirectory() as tmp:
        css = Path(tmp) / "style.css"
        css.write_text(CSS, "utf-8")
        for f in FONTS.glob("*.woff2"):
            shutil.copy2(f, Path(tmp) / f.name)
        html = DOCS / f"_{src.stem}_tmp.html"   # 이미지 상대경로(images/) 때문에 docs 폴더에 잠깐 만든다
        try:
            subprocess.run(["pandoc", str(src), "-f", "gfm", "-t", "html5", "-s", "--metadata", f"title={src.stem.replace('_', ' ')}",
                            "--css", str(css), "--self-contained", "-o", str(html)], cwd=DOCS, check=True)
            # pandoc이 메타데이터 제목을 본문 위에 한 번 더 넣으므로 숨긴다(본문 첫 줄이 제목)
            t = html.read_text("utf-8").replace('<header id="title-block-header">', '<header id="title-block-header" style="display:none">')
            html.write_text(t, "utf-8")
            exe = next(b for b in BROWSERS if b.exists())
            subprocess.run([str(exe), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}",
                            html.as_uri()], check=True, timeout=120)
        finally:
            html.unlink(missing_ok=True)
    print(out)


if __name__ == "__main__":
    import sys
    srcs = [Path(a).resolve() for a in sys.argv[1:]] or [SRC]
    for s in srcs:
        main(s, s.with_suffix(".pdf"))
