"""换行直接换段，单独占一行的图片也自成一段；行尾两个空格或反斜杠只换行。"""
import re
import unittest

from support import RenderTest, texts

NONE = "template: none"


def paragraphs(html):
    """每段里的内容，图片换成 IMG，方便比较。"""
    html = re.sub(r"<img [^>]*>", "IMG", html)
    return [re.sub(r"\s+", " ", p).strip() for p in re.findall(r"<p>(.*?)</p>", html, re.S)]


class LineBreaks(RenderTest):
    def check(self, cases):
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(paragraphs(self.html(source, NONE)), expected)

    def test_each_line_is_a_paragraph(self):
        self.check({
            "one\ntwo\nthree": ["one", "two", "three"],
            "one\n\ntwo": ["one", "two"],
            "> q1\n> q2": ["q1", "q2"],
            "# Title\nbody\nmore": ["body", "more"],
        })

    def test_hard_break_keeps_the_paragraph(self):
        self.check({
            "roses  \nviolets\\\nsugar\nnext": ["roses<br /> violets<br /> sugar", "next"],
        })

    def test_formatting_across_lines_is_not_cut(self):
        self.check({
            "**bold\nacross** after\nnew": ["<strong>bold across</strong> after", "new"],
            "[link\ntext](u)\nnext": ['<a href="u">link text</a>', "next"],
        })

    def test_tight_list_lines_become_line_breaks(self):
        html = self.html("- one\n  two\n- three", NONE)
        self.assertIn("one<br />", html)
        self.assertEqual(paragraphs(html), [])

    def test_images_on_their_own_line(self):
        self.check({
            "text\n![](a.png)": ["text", "IMG"],
            "![](a.png)\ntext": ["IMG", "text"],
            "a\n![](x.png)\n![](y.png)\nb": ["a", "IMG", "IMG", "b"],
            "text\n[![](a.png)](https://x.org)": ["text", '<a href="https://x.org">IMG</a>'],
            "text  \n![](a.png)": ["text", "IMG"],
            "Text with ![](icon.png) inside": ["Text with IMG inside"],
            "![](a.png) ![](b.png)": ["IMG IMG"],
        })

    def test_line_numbers_follow_the_source(self):
        html = self.render(f"---\n{NONE}\n---\none\ntwo\n![](a.png)\na $x\ny$ b\nafter")["html"]
        self.assertEqual(re.findall(r'data-line="(\d+)"', html), ["3", "4", "5", "6", "8"])

    def test_numbered_figure(self):
        html = self.html("# a\n\nSee [@fig:w].\n![Wave](a.png){#fig:w width=60%}\nAfter.")
        self.assertEqual(texts(html, "caption-label"), ["图 1-1"])
        self.assertIn("width: 60%", html)
        self.assertEqual(paragraphs(html)[-1], "After.")


if __name__ == "__main__":
    unittest.main()
