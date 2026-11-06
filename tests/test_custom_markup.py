"""基于 none 的模板可以写 ::: 块和 [文字]{.类名}。除了 class，什么属性都不能加。"""
import re
import unittest

from support import RenderTest

NONE = "template: none"


class Spans(RenderTest):
    def test_written_forms(self):
        cases = {
            "text [a b]{.date} end": '<span class="date">a b</span>',
            "[a]{.x .y}": '<span class="x y">a</span>',
            "[a]{ .k  .m }": '<span class="k m">a</span>',
            "### Co [2020]{.date}": 'Co <span class="date">2020</span>',
            "[**bold**]{.k}": '<span class="k"><strong>bold</strong></span>',
            "[`c`]{.k}": '<span class="k"><code>c</code></span>',
            "[a [b] c]{.k}": '<span class="k">a [b] c</span>',
            "[a [b]{.i} c]{.o}": '<span class="o">a <span class="i">b</span> c</span>',
            "[see [x](http://x.com) now]{.k}": '<span class="k">see <a href="http://x.com">x</a> now</span>',
            "[a \\] b]{.k}": '<span class="k">a ] b</span>',
            "[a]{.x} and [b]{.y}": '<span class="x">a</span> and <span class="y">b</span>',
            "| h |\n| --- |\n| [a]{.k} |": '<span class="k">a</span>',
        }
        for source, expected in cases.items():
            with self.subTest(source):
                self.assertIn(expected, self.html(source, NONE))

    def test_left_as_text_without_losing_anything(self):
        # 换掉的插件会把没写完的 {.b 吃掉
        for source in ("[a]{.b", "[a]{ unfinished text here", "[a]{}", "[a] {.k}", "[a] b", "\\[a]{.k}"):
            with self.subTest(source):
                html = self.html(source, NONE)
                self.assertNotIn("<span", html)
                self.assertIn(source.lstrip("\\"), html)

    def test_only_class_is_allowed(self):
        # 换掉的插件会原样输出 style 和 id，绕开模板 CSS 的联网检查
        for source in ("[a]{onclick=alert(1)}", "[a]{.ok onclick=alert(1)}", '[a]{style="background:url(http://x)"}',
                       "[a]{#x}", '[a]{.x" onclick="y}', '[a]{class="x" onclick="y"}', "[a](http://x){onclick=y}",
                       '![a](b.png){onerror=y}', '![a](b.png){style="position:fixed"}', "`c`{onclick=y}"):
            with self.subTest(source):
                self.assertIsNone(re.search(r'<(?:span|a|img|code)\b[^>]*\b(?:onclick|onerror|style|id)\s*=', self.html(source, NONE)))

    def test_links_are_still_links(self):
        self.assertIn('<a href="http://x.com">a</a>', self.html("[a](http://x.com)", NONE))
        self.assertIn('<a href="http://x.com">a</a>', self.html("[a]\n\n[a]: http://x.com", NONE))

    def test_code_is_left_alone(self):
        self.assertNotIn("<span", self.html("```\n[a]{.b}\n```\n\n`[a]{.b}`", NONE))


class Blocks(RenderTest):
    def test_written_forms(self):
        cases = {
            "::: job\ntext\n:::": '<div class="job">',
            "::: job current\ntext\n:::": '<div class="job current">',
            "::: 工作\nx\n:::": '<div class="工作">',
            "::: job\ntext": '<div class="job">',
            "- item\n\n  ::: job\n  x\n  :::": '<div class="job">',
        }
        for source, expected in cases.items():
            with self.subTest(source):
                self.assertIn(expected, self.html(source, NONE))

    def test_markdown_inside(self):
        html = self.html("::: job\n## h\n\n- a\n\n[b]{.k}\n:::", NONE)
        for expected in ("<h2", "<li>a</li>", '<span class="k">b</span>'):
            self.assertIn(expected, html)

    def test_nesting(self):
        self.assertRegex(self.html(":::: outer\n::: inner\nx\n:::\n::::", NONE), r'(?s)class="outer".*class="inner"')

    def test_left_as_text(self):
        for source in (":::\ntext\n:::", ":: job\nx", '::: x" onclick="y\nz\n:::', "::: x><script>alert(1)</script>\nz\n:::",
                       "::: x onclick=y\nz\n:::", "::: x;y\nz\n:::", "::: 1x\nz\n:::"):
            with self.subTest(source):
                self.assertNotIn("<div", self.html(source, NONE))

    def test_keeps_line_numbers_for_scroll_sync(self):
        self.assertIn("data-line", self.render(f"---\n{NONE}\n---\n::: job\ntext\n:::")["html"])


class OtherTemplates(RenderTest):
    BODY = "[a]{.date}\n\n::: job\nx\n:::"

    def test_plain_documents_and_numbered_leave_them_alone(self):
        for head in ("title: t", "template: numbered", "template: report"):
            with self.subTest(head):
                html = self.html(self.BODY, head)
                self.assertIn("[a]{.date}", html)
                self.assertIn("::: job", html)

    def test_figures_is_a_normal_block_in_none(self):
        self.assertIn('<div class="figures">', self.html("::: figures\ntext\n:::", NONE))
        self.assertIn('class="figure-group"', self.html("::: figures\n![a](b.png)\n:::", "template: numbered"))


if __name__ == "__main__":
    unittest.main()
