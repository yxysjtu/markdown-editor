"""内置 numbered 的编号和交叉引用。"""
import unittest

import numbered
from support import RenderTest, texts


def numbers(html):
    return texts(html, "heading-number")


def labels(html):
    return texts(html, "caption-label")


def references(html):
    return texts(html, "xref")


class Headings(RenderTest):
    def test_levels(self):
        self.assertEqual(numbers(self.html("# a\n\n## b\n\n## c\n\n### d\n\n# e\n\n## f")), ["1", "1.1", "1.2", "1.2.1", "2", "2.1"])

    def test_highest_level_counts_as_first(self):
        html = self.html("## a\n\n### b\n\n## c")
        self.assertEqual(numbers(html), ["1", "1.1", "2"])
        self.assertIn("<h1", html)

    def test_skipped_level(self):
        self.assertEqual(numbers(self.html("# a\n\n### b")), ["1", "1.1.1"])

    def test_unnumbered_mark(self):
        self.assertEqual(numbers(self.html("# a {-}\n\n## b\n\n# c")), ["1"])

    def test_conventional_titles_are_not_numbered(self):
        for title in ("摘要", "参考文献", "致谢", "References", "Abstract", "Acknowledgements"):
            with self.subTest(title):
                self.assertEqual(numbers(self.html(f"# a\n\n# {title}\n\n## sub")), ["1"])

    def test_label_does_not_show_in_the_title(self):
        html = self.html("# 引言 {#sec:intro}\n\n[@sec:intro]")
        self.assertNotIn("{#sec", html)
        self.assertIn('id="sec:intro"', html)
        self.assertEqual(references(html), ["第 1 章"])

    def test_section_reference(self):
        self.assertEqual(references(self.html("# a\n\n## b {#sec:b}\n\n[@sec:b]")), ["第 1.1 节"])

    def test_unnumbered_reference_uses_the_title(self):
        self.assertEqual(references(self.html("# 致谢 {#sec:t}\n\n[@sec:t]")), ["致谢"])


class Appendix(RenderTest):
    def test_letters(self):
        self.assertEqual(numbers(self.html("# a\n\n# 附录\n\n## x\n\n# 附录：问卷\n\n# b")), ["1", "附录 A", "A.1", "附录 B", "2"])

    def test_word_is_not_repeated(self):
        self.assertNotIn("附录：问卷", self.html("# 附录：问卷"))
        self.assertIn("问卷", self.html("# 附录：问卷"))

    def test_figures_use_the_letter(self):
        self.assertEqual(labels(self.html("# 附录\n\n![t](a.png)\n\n# 附录\n\n![t](a.png)")), ["图 A-1", "图 B-1"])

    def test_english(self):
        self.assertEqual(numbers(self.html("# Appendix\n\n# Appendix A: Survey", "template: numbered\nlang: en")), ["Appendix A", "Appendix B"])

    def test_words_starting_with_appendix_are_not_appendices(self):
        self.assertEqual(numbers(self.html("# Appendix Notes")), ["1"])


class Figures(RenderTest):
    def test_number_restarts_each_chapter(self):
        self.assertEqual(labels(self.html("![t](a.png)\n\n# a\n\n![t](a.png)\n\n![t](a.png)\n\n# b\n\n![t](a.png)")), ["图 1", "图 1-1", "图 1-2", "图 2-1"])

    def test_no_caption_no_number(self):
        html = self.html("# a\n\n![](a.png)\n\n![t](a.png)")
        self.assertEqual(labels(html), ["图 1-1"])

    def test_inline_image_is_not_a_figure(self):
        self.assertEqual(labels(self.html("# a\n\ntext ![t](a.png) more")), [])

    def test_reference_before_and_after(self):
        self.assertEqual(references(self.html("[@fig:later]\n\n# a\n\n![t](a.png){#fig:later}\n\n[@fig:later]")), ["图 1-1", "图 1-1"])

    def test_missing_reference_stands_out(self):
        self.assertIn('class="xref-missing"', self.html("[@fig:nope]"))

    def test_width(self):
        self.assertIn("width: 60%", self.html("![t](a.png){width=60%}"))
        self.assertIn("width: 5cm", self.html("![t](a.png){#fig:a width=5cm}"))
        self.assertNotIn("width:", self.html("![t](a.png){width=abc}"))
        self.assertNotIn("width:", self.html('![t](a.png){width="1;background:url(x)"}'))

    def test_unknown_attribute_stays_as_text(self):
        self.assertIn("{height=3cm}", self.html("![t](a.png){height=3cm}"))


class FigureGroups(RenderTest):
    GROUP = "::: figures {#fig:all cols=3}\n![one](a.png){#fig:a}\n![two](b.png){#fig:b}\n\nCaption\n:::\n\n[@fig:all] [@fig:a] [@fig:b]"

    def test_group(self):
        html = self.html("# x\n\n" + self.GROUP)
        self.assertIn('class="figure-group"', html)
        self.assertIn("--figure-columns: 3", html)
        self.assertEqual(labels(html), ["图 1-1"])
        self.assertEqual(references(html), ["图 1-1", "图 1-1(a)", "图 1-1(b)"])
        self.assertIn("(a) one", html)

    def test_columns_are_limited(self):
        self.assertIn("--figure-columns: 6", self.html("::: figures {cols=99}\n![a](a.png)\n:::"))
        self.assertIn("--figure-columns: 2", self.html("::: figures\n![a](a.png)\n:::"))

    def test_other_content_is_not_lost(self):
        html = self.html("::: figures\n![a](a.png)\n\n- list item\n\nCaption\n:::")
        self.assertIn("list item", html)
        self.assertIn("Caption", html)


class Tables(RenderTest):
    TABLE = "| A |\n| --- |\n| 1 |"

    def test_caption_before_or_after(self):
        before = self.html(f"# a\n\n: T {{#tbl:t}}\n\n{self.TABLE}\n\n[@tbl:t]")
        self.assertLess(before.index("表 1-1"), before.index("<table"))
        self.assertEqual(references(before), ["表 1-1"])
        after = self.html(f"# a\n\n{self.TABLE}\n\n: T\n")
        self.assertLess(after.index("表 1-1"), after.index("<table"))

    def test_colon_without_table_is_text(self):
        self.assertIn(": plain", self.html(": plain"))

    def test_table_without_caption_is_not_numbered(self):
        self.assertEqual(labels(self.html(self.TABLE)), [])


class Equations(RenderTest):
    def test_numbers_and_references(self):
        html = self.html("# a\n\n$$\nx\n$$ {#eq:one}\n\n$$ y $$ {#eq:two}\n\n$$ z $$\n\n$$ w $$ {-}\n\n[@eq:one] [@eq:two]")
        self.assertEqual(texts(html, "equation-number"), ["(1-1)", "(1-2)", "(1-3)"])
        self.assertEqual(references(html), ["式 (1-1)", "式 (1-2)"])
        self.assertNotIn("{#eq", html)


class CodeBlocks(RenderTest):
    def test_language_only_is_not_numbered(self):
        self.assertEqual(labels(self.html("```python\nx\n```")), [])

    def test_title_and_label(self):
        html = self.html('# a\n\n```python title="a.py" {#lst:a}\nx\n```\n\n[@lst:a]')
        self.assertEqual(labels(html), ["代码 1-1"])
        self.assertEqual(references(html), ["代码 1-1"])
        self.assertIn("a.py", html)
        self.assertNotIn("title=", html)

    def test_title_is_not_formatted(self):
        html = self.html('```python title="a_b*c*<b>e</b>.py"\nx\n```')
        self.assertIn("a_b*c*&lt;b&gt;e&lt;/b&gt;.py", html)

    def test_markers_inside_code_are_left_alone(self):
        html = self.html("```\n$$ x $$ {#eq:a}\n![t](a.png){#fig:a}\n[@fig:a]\n\\newpage\n```\n\n`[@fig:a]`")
        self.assertEqual(labels(html), [])
        self.assertEqual(texts(html, "equation-number"), [])
        self.assertNotIn("page-break", html)
        self.assertNotIn("xref", html)

    def test_long_code_can_break_across_pages(self):
        self.assertIn("code-long", self.html("```\n" + "x\n" * 31 + "```"))
        self.assertNotIn("code-long", self.html("```\n" + "x\n" * 30 + "```"))


class PageBreak(RenderTest):
    def test_alone_on_a_line(self):
        self.assertIn('class="page-break"', self.html("\\newpage"))

    def test_inside_text_is_not_a_break(self):
        self.assertNotIn("page-break", self.html("text \\newpage more"))


class FrontMatter(RenderTest):
    def test_fields(self):
        html = self.render("---\ntemplate: numbered\ntitle: T\nauthor: [A, B]\naffiliation: U\ndate: 2026-11-06\nabstract: X\nkeywords: a, b\n---\nbody")["html"]
        for css_class in ("front-matter", "doc-title", "doc-author", "doc-affiliation", "doc-date", "doc-abstract", "doc-keywords", "front-label"):
            with self.subTest(css_class):
                self.assertIn(css_class, html)
        self.assertIn("A　B", html)
        self.assertIn("a；b", html)

    def test_nothing_without_fields(self):
        self.assertNotIn("front-matter", self.html("x"))

    def test_english_labels(self):
        html = self.html("# a\n\n![t](a.png)", "template: numbered\nlang: en\nabstract: X")
        self.assertIn("Abstract: ", html)
        self.assertEqual(labels(html), ["Figure 1-1"])


class Options(RenderTest):
    BODY = "# a {#sec:a}\n\n![t](a.png){#fig:a}\n\n# b\n\n![t](a.png){#fig:b}\n\n$$ x $$\n\n[@sec:a] [@fig:a] [@fig:b]\n\n# 附录\n\n![t](a.png)"

    def run_with(self, option):
        return self.html(self.BODY, f"template: numbered\nstyle:\n  {option}")

    def test_dot_separator(self):
        html = self.run_with('numbering: "2.1"')
        self.assertEqual(labels(html), ["图 1.1", "图 2.1", "图 A.1"])
        self.assertEqual(texts(html, "equation-number"), ["(2.1)"])

    def test_continuous(self):
        self.assertEqual(labels(self.run_with("numbering: 1")), ["图 1", "图 2", "图 3"])

    def test_chapter_format(self):
        html = self.run_with('chapter-format: "第{cn}章"')
        self.assertEqual(numbers(html), ["第一章", "第二章", "附录 A"])
        self.assertEqual(references(html)[0], "第一章")
        self.assertEqual(numbers(self.run_with('chapter-format: "Chapter {}"'))[:2], ["Chapter 1", "Chapter 2"])

    def test_labels(self):
        self.assertEqual(labels(self.run_with("figure-label: Fig."))[0], "Fig. 1-1")
        self.assertEqual(labels(self.run_with('figure-label: "图{}"'))[0], "图1-1")
        self.assertEqual(numbers(self.run_with("appendix-label: Annex"))[-1], "Annex A")

    def test_label_text_is_escaped(self):
        self.assertIn("&lt;b&gt; 1-1", self.run_with('figure-label: "<b>"'))


class ChineseNumber(unittest.TestCase):
    def test_values(self):
        cases = {1: "一", 9: "九", 10: "十", 11: "十一", 20: "二十", 23: "二十三", 99: "九十九", 100: "100"}
        for number, expected in cases.items():
            with self.subTest(number):
                self.assertEqual(numbered.chinese_number(number), expected)


if __name__ == "__main__":
    unittest.main()
