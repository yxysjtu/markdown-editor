"""测试共用的东西：一个临时文件夹，和调用渲染接口的方法。"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
import editor  # noqa: E402


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.root = self.work / "open"
        self.root.mkdir()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def render(self, content, path="doc.md", root=None):
        return editor.api_render({"root": str(root or self.root), "path": path, "content": content})

    def html(self, body, head="template: numbered"):
        """渲染一段正文，去掉 data-line，方便比较。"""
        return re.sub(r' data-line="\d+"', "", self.render(f"---\n{head}\n---\n{body}")["html"])


def texts(html, css_class):
    """取出某个 class 的文字，比如所有的“图 2-1”。"""
    return re.findall(rf'class="{css_class}"[^>]*>([^<]*)<', html)
