#!/usr/bin/env python3
"""检查版式有没有变：把几份文档导出成 PDF，逐页和之前存下的基准比较。

    python tests/compare_pdf.py save      改代码之前运行，存下基准
    python tests/compare_pdf.py compare   改完之后运行，列出有变化的页

需要本机的 Chrome 或 Edge，还要额外安装：pip install pypdfium2 pillow。这些只有这个脚本用，所以不放进 requirements.txt。
这里没有经过前端，公式显示成原文，也不带目录，所以只用来发现版式的变化，不能代替实际导出。
基准存在 tests/.pdf-baseline，不提交。examples 里的文件改了也会显示有变化，那就重新 save。
"""
import base64
import mimetypes
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
import editor  # noqa: E402

try:
    import pypdfium2
    from PIL import ImageChops
except ImportError:
    sys.exit("This script needs: pip install pypdfium2 pillow")

BASELINE = Path(__file__).resolve().parent / ".pdf-baseline"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPORT_FOLDER = APP_DIR / "examples" / "academic-report"
# (打开的文件夹, 文档的路径, 内容来自哪个文件)
DOCUMENTS = [
    (REPORT_FOLDER, "report_zh.md", REPORT_FOLDER / "report_zh.md"),
    (REPORT_FOLDER, "report_using_template.md", REPORT_FOLDER / "report_using_template.md"),
    (REPORT_FOLDER, "template.md", REPORT_FOLDER / "template.md"),
    (APP_DIR / "examples" / "resume", "resume.md", APP_DIR / "examples" / "resume" / "resume.md"),
    (REPORT_FOLDER, "english.md", FIXTURES / "english.md"),
    (REPORT_FOLDER, "edge-cases.md", FIXTURES / "edge-cases.md"),
    (REPORT_FOLDER, "start-at-level-two.md", FIXTURES / "start-at-level-two.md"),
    (REPORT_FOLDER, "styled.md", FIXTURES / "styled.md"),
    (REPORT_FOLDER, "plain.md", FIXTURES / "plain.md"),
]


def embed_image(match):
    """前端导出时把图片嵌进 HTML，这里也一样，否则 PDF 里没有图片。"""
    query = parse_qs(match.group(1).replace("&amp;", "&"))
    path = Path(unquote(query["root"][0])) / unquote(query["path"][0])
    if not path.is_file():
        return match.group(0)
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f'src="data:{kind};base64,{base64.b64encode(path.read_bytes()).decode()}"'


def build_html(data):
    body = re.sub(r'src="/files\?([^"]+)"', embed_image, data["html"])
    document_css = (editor.STATIC_DIR / "document.css").read_text(encoding="utf-8")
    style = f'{document_css}\n{editor.CODE_CSS}\n{data["template_css"]}'
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>test</title>\n<style>\n{style}\n</style>\n</head>\n'
            f'<body class="exported"><article class="doc {data["doc_class"]}"><div class="prose">{body}</div></article></body>\n</html>\n')


def export(root, path, source):
    content = source.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    data = editor.api_render({"root": str(root), "path": path, "content": content})
    return editor.api_pdf({"html": build_html(data), "bookmarks": data["pdf_bookmarks"]})


def pages(pdf_bytes):
    pdf = pypdfium2.PdfDocument(pdf_bytes)
    outline = [(item.level, item.get_title()) for item in pdf.get_toc()]
    return [pdf[index].render(scale=1.5).to_pil().convert("RGB") for index in range(len(pdf))], outline


def save():
    BASELINE.mkdir(exist_ok=True)
    for root, path, source in DOCUMENTS:
        (BASELINE / f"{Path(path).stem}.pdf").write_bytes(export(root, path, source))
        print("saved", path)


def compare():
    changed = 0
    for root, path, source in DOCUMENTS:
        stored = BASELINE / f"{Path(path).stem}.pdf"
        if not stored.is_file():
            sys.exit("There is no baseline yet. Run: python tests/compare_pdf.py save")
        before, before_outline = pages(stored.read_bytes())
        after, after_outline = pages(export(root, path, source))
        different = [number + 1 for number, (a, b) in enumerate(zip(before, after))
                     if a.size != b.size or ImageChops.difference(a, b).getbbox()]
        problems = []
        if len(before) != len(after):
            problems.append(f"{len(before)} pages -> {len(after)} pages")
        if different:
            problems.append(f"pages {different} look different")
        if before_outline != after_outline:
            problems.append("bookmarks are different")
        changed += bool(problems)
        print(f"{path:28} {len(after):3} pages  {'; '.join(problems) or 'same'}")
    print("All the same." if not changed else f"{changed} document(s) changed.")
    return changed


if __name__ == "__main__":
    if sys.argv[1:] == ["save"]:
        save()
    elif sys.argv[1:] == ["compare"]:
        sys.exit(1 if compare() else 0)
    else:
        sys.exit(__doc__)
