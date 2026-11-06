"""用模板的文档可以写 ::: 块和 [文字]{.类名}。除了 class，什么属性都不能加。"""
import re
import unittest

from support import RenderTest, texts

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


class WithNumbered(RenderTest):
    BODY = "[a]{.date}\n\n::: job\nx\n:::"

    def test_plain_documents_leave_them_alone(self):
        html = self.html(self.BODY, "title: t")
        self.assertIn("[a]{.date}", html)
        self.assertIn("::: job", html)

    def test_numbered_and_report_support_them(self):
        for head in ("template: numbered", "template: report"):
            with self.subTest(head):
                html = self.html(self.BODY, head)
                self.assertIn('<span class="date">a</span>', html)
                self.assertIn('<div class="job">', html)

    def test_figures_stays_a_group(self):
        self.assertIn('<div class="figures">', self.html("::: figures\ntext\n:::", NONE))
        for source in ("::: figures\n![a](b.png)\n:::", "::: figures {#fig:x cols=3}\n![a](b.png)\n:::"):
            with self.subTest(source):
                html = self.html(source, "template: numbered")
                self.assertIn('class="figure-group"', html)
                self.assertNotIn("<div class=\"figures", html)

    def test_only_class_is_allowed(self):
        for source in ('[a]{style="x"}', "[a]{#x}", "[a]{onclick=y}"):
            with self.subTest(source):
                self.assertNotIn("<span", self.html(source, "template: numbered"))
        self.assertNotIn("<div", self.html('::: x" onclick="y\nz\n:::', "template: numbered"))

    def test_reference_is_not_swallowed(self):
        html = self.html("# a\n\n![t](a.png){#fig:a}\n\n[@fig:a]{.k}", "template: numbered")
        self.assertEqual(texts(html, "xref"), ["图 1-1"])
        self.assertIn("{.k}", html)

    def test_reference_inside_a_span(self):
        html = self.html("# a\n\n![t](a.png){#fig:a}\n\n[见 [@fig:a] 所示]{.note}", "template: numbered")
        self.assertRegex(html, r'<span class="note">见 <a class="xref"[^>]*>图 1-1</a> 所示</span>')

    def test_missing_reference_inside_a_span_stands_out(self):
        self.assertIn('xref-missing', self.html("[见 [@fig:no]]{.note}", "template: numbered"))

    def test_numbering_inside_a_block(self):
        body = "# a\n\n::: box\n## b {#sec:b}\n\n![t](a.png){#fig:a}\n\n: T {#tbl:t}\n\n| A |\n| --- |\n| 1 |\n\n$$ x $$ {#eq:e}\n\n```python title=\"c\"\nx\n```\n:::\n\n[@sec:b] [@fig:a] [@tbl:t] [@eq:e]"
        html = self.html(body, "template: numbered")
        self.assertIn('<div class="box">', html)
        self.assertEqual(texts(html, "heading-number"), ["1", "1.1"])
        self.assertEqual(texts(html, "caption-label"), ["图 1-1", "表 1-1", "代码 1-1"])
        self.assertEqual(texts(html, "xref"), ["第 1.1 节", "图 1-1", "表 1-1", "式 (1-1)"])
        self.assertLess(html.index('<div class="box">'), html.index("图 1-1"))
        self.assertLess(html.index("代码 1-1"), html.index("</div>\n<p>"))

    def test_figure_group_inside_a_block(self):
        html = self.html(":::: box\n::: figures {#fig:g}\n![a](a.png)\n:::\n::::\n\n[@fig:g]", "template: numbered")
        self.assertLess(html.index('class="box"'), html.index("figure-group"))
        self.assertEqual(texts(html, "xref"), ["图 1"])

    def test_page_break_inside_a_block(self):
        self.assertIn('class="page-break"', self.html("::: box\n\\newpage\n:::", "template: numbered"))

    def test_span_in_titles_and_captions(self):
        html = self.html("# 题 [x]{.k} {#sec:a}\n\n![图 [y]{.k}](a.png)\n\n: 表 [z]{.k} {#tbl:t}\n\n| A |\n| --- |\n| 1 |\n\n[@sec:a] [@tbl:t]", "template: numbered")
        for text in ("x", "y", "z"):
            with self.subTest(text):
                self.assertIn(f'<span class="k">{text}</span>', html)
        self.assertEqual(texts(html, "xref"), ["第 1 章", "表 1-1"])
        self.assertNotIn("{#", html)
        self.assertNotIn("{.k}", html)

    def test_span_in_front_matter(self):
        html = self.render("---\ntemplate: numbered\ntitle: T [x]{.k}\nabstract: A [y]{.k}\n---\nbody")["html"]
        self.assertIn('<span class="k">x</span>', html)
        self.assertIn('<span class="k">y</span>', html)


if __name__ == "__main__":
    unittest.main()
