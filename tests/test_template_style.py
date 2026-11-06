"""style 选项和模板 CSS 的检查。模板可能来自别人，这里的每一条都是一种跑出去或者联网的写法。"""
import unittest

import support  # noqa: F401
import template_style as style


class CssCheck(unittest.TestCase):
    def test_rejected(self):
        cases = {
            "extra brace": "h1{color:red}} body{display:none} .x{",
            "open brace": "h1{color:red",
            "closes style": "</style><script>alert(1)</script>",
            "closes style in comment": "/* </STYLE> */ h1{}",
            "closes style in string": 'h1::before{content:"</style>"}',
            "unclosed comment": "h1{} /* x",
            "unclosed string": 'h1::before{content:"x}',
            "import url": "@import url(http://x/a.css);",
            "import string": '@import "http://x/a.css";',
            "import upper": "@IMPORT 'x.css';",
            "import escaped": "@\\69mport 'x.css';",
            "url": "h1{background:url(http://x/a.png)}",
            "url quoted": "h1{background:url('https://x/a.png')}",
            "url relative": "h1{background:url(a.png)}",
            "url upper": "h1{background:URL(http://x)}",
            "url escaped": "h1{background:u\\72l(http://x/a.png)}",
            "url escaped hex": "h1{background:\\75 rl(http://x/a.png)}",
            "url escaped in string": 'a{background:url("ht\\74p://x")}',
            "image-set": "h1{background:image-set('http://x/a.png' 1x)}",
            "webkit image-set": "h1{background:-webkit-image-set('http://x/a.png' 1x)}",
            "src function": "h1{background:src('http://x')}",
            # 这些曾经能骗过检查，跑出隔离范围
            "comment mark in string": 'a{content:"/*"} } b{display:none} .x{content:"*/"}',
            "brace in unquoted url": "a{b:url(data:{)}} c{display:none} .d{e:url(data:})",
            "escaped quote": 'a{x:\\"} } b{display:none} .y{z:\\"}',
            "escaped url with brace": "a{b:u\\72l(data:{)}} c{display:none} .d{e:u\\72l(data:})",
            "quote in comment": "/* ' */ a{color:red} } b{} .x{ /* ' */",
        }
        for name, css in cases.items():
            with self.subTest(name):
                self.assertTrue(style.css_problem(css))
                self.assertEqual(style.read_css(css, "t.css")[0], "")

    def test_allowed(self):
        cases = {
            "plain": "h1 { color: red; }",
            "empty": "",
            "brace in comment": "/* } */ h1{color:red}",
            "brace in string": 'h1::before{content:"}"}',
            "quote in comment": "/* it's fine */ a{color:red}",
            "comment mark in string": 'a::before{content:"/* not a comment"}',
            "link in comment": "/* url(http://x) @import */ a{color:red}",
            "data url": "h1{background:url(data:image/png;base64,AAAA)}",
            "escape in string": 'a::before{content:"\\201C"}',
            "font face": '@font-face { font-family: x; src: local("y"); }',
            "media": "@media print { h1 { color: red; } }",
        }
        for name, css in cases.items():
            with self.subTest(name):
                self.assertEqual(style.css_problem(css), "")

    def test_scope_and_variables(self):
        css, variables, problems = style.read_css("h1 { color: var(--accent); margin: var( --gap, var(--other)); }", "t.css")
        self.assertTrue(css.startswith(style.CSS_SCOPE + " {"))
        self.assertEqual(variables, {"accent", "gap", "other"})
        self.assertEqual(problems, [])

    def test_comments_do_not_declare_variables(self):
        self.assertEqual(style.read_css("/* var(--ghost) */ h1 {}", "t.css")[1], set())

    def test_font_face_moves_outside_the_scope(self):
        css = style.read_css('@font-face { font-family: x; src: local("y"); } h1 {}', "t.css")[0]
        self.assertLess(css.index("@font-face"), css.index(style.CSS_SCOPE))
        self.assertNotIn("@font-face", css[css.index(style.CSS_SCOPE):])

    def test_page_rule_gets_a_hint(self):
        self.assertIn("page-margin", style.read_css("@page { margin: 0 } h1 {}", "t.css")[2][0])


class Values(unittest.TestCase):
    def read(self, name, value, base="numbered", variables=("accent", "body-font", "font-size", "line-height", "first-line-indent", "title-align")):
        return style.read_style([{name: value}], base, variables)

    def test_size_names(self):
        self.assertEqual(style.size("小四"), "12pt")
        self.assertEqual(style.size("五号"), "10.5pt")
        self.assertEqual(style.size("11pt"), "11pt")
        with self.assertRaises(ValueError):
            style.size("x;}")

    def test_margin_shorthand(self):
        self.assertEqual(style.page_margin("2cm"), (2, 2, 2, 2))
        self.assertEqual(style.page_margin("2cm 3cm"), (2, 3, 2, 3))
        self.assertEqual(style.page_margin("1cm 2cm 3cm"), (1, 2, 3, 2))
        self.assertEqual(style.page_margin("1cm 2cm 3cm 4cm"), (1, 2, 3, 4))
        self.assertAlmostEqual(style.page_margin("10mm")[0], 1)
        for bad in ("2cm 2cm 2cm 2cm 2cm", "2em", "abc"):
            with self.assertRaises(ValueError):
                style.page_margin(bad)

    def test_paper_ignores_case(self):
        self.assertEqual(style.paper("a5"), (14.8, 21))
        with self.assertRaises(ValueError):
            style.paper("A9")

    def test_variable_values_cannot_escape(self):
        bad = ["red; } body { display: none", "url(http://x/a.png)", "URL(http://x)", "url(a.png)", "image-set('http://x')", "image-set('a.png')", "a)b", "(a",
               "'x", '"x', "/* x", "a:b", "<x>", "\\75rl(http://x)", True, None, [], {}]
        for value in bad:
            with self.subTest(value=value):
                values, variables, problems = self.read("accent", value)
                self.assertEqual(variables, {})
                self.assertEqual(len(problems), 1)

    def test_variable_values_allowed(self):
        for value, expected in {"#1a5fb4": "#1a5fb4", "rgb(1, 2, 3)": "rgb(1, 2, 3)", ".75pt solid #000": ".75pt solid #000",
                                0: "0", 1.5: "1.5", "小四": "12pt"}.items():
            with self.subTest(value=value):
                self.assertEqual(self.read("accent", value)[1], {"accent": expected})

    def test_checked_by_name_ending(self):
        self.assertEqual(self.read("font-size", "小四")[1], {"font-size": "12pt"})
        self.assertTrue(self.read("font-size", "abc")[2])
        self.assertTrue(self.read("title-align", "middle")[2])
        self.assertEqual(self.read("body-font", "Times New Roman, KaiTi")[1], {"body-font": '"Times New Roman", "KaiTi"'})
        self.assertTrue(self.read("body-font", 'a"}')[2])
        self.assertEqual(self.read("line-height", "20pt")[1], {"line-height": "20pt"})
        self.assertTrue(self.read("line-height", True)[2])
        self.assertEqual(self.read("first-line-indent", 0)[1], {"first-line-indent": "0"})

    def test_labels_cannot_be_format_attacks(self):
        self.assertEqual(style.label("Fig."), "Fig. {}")
        self.assertEqual(style.label("图{}"), "图{}")
        for bad in ("{0.__class__}", "a{}{}", "", "   ", 5, "x" * 40):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                style.label(bad)

    def test_chapter_format(self):
        self.assertEqual(style.chapter_format("第{cn}章"), "第{cn}章")
        for bad in ("第章", "{a}", "{}{}", 5):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                style.chapter_format(bad)

    def test_numbering(self):
        self.assertEqual(style.numbering("2-1"), "-")
        self.assertEqual(style.numbering(2.1), ".")
        self.assertEqual(style.numbering(1), "")
        with self.assertRaises(ValueError):
            style.numbering("3")

    def test_unknown_options(self):
        self.assertIn("Unknown", self.read("nope", 1)[2][0])
        self.assertEqual(style.read_style(["oops"], "none")[2], ['"style" should be a list of "name: value" lines'])

    def test_numbering_options_need_numbered(self):
        self.assertEqual(self.read("numbering", "2.1")[2], [])
        self.assertIn("Unknown", self.read("numbering", "2.1", base="none")[2][0])

    def test_page_options_work_everywhere(self):
        self.assertEqual(self.read("paper", "A5", base="none")[2], [])

    def test_a_wrong_value_keeps_the_earlier_layer(self):
        values, variables, problems = style.read_style([{"title-align": "left", "paper": "A4"}, {"title-align": "middle", "paper": "A5"}], "none", ["title-align"])
        self.assertEqual(variables, {"title-align": "left"})
        self.assertEqual(values["paper"], (14.8, 21))
        self.assertEqual(len(problems), 1)


class GeneratedCss(unittest.TestCase):
    def test_nothing_without_options(self):
        self.assertEqual(style.build_css({}, {}), "")

    def test_page_rule(self):
        css = style.build_css({"paper": (14.8, 21), "page-margin": (1, 2, 3, 4), "page-numbers": False}, {})
        self.assertIn("size: 14.8cm 21cm;", css)
        self.assertIn("margin: 1cm 2cm 3cm 4cm;", css)
        self.assertIn('@bottom-center { content: ""; }', css)
        self.assertIn(".doc.paged", css)

    def test_page_numbers_alone_do_not_make_a_sheet(self):
        css = style.build_css({"page-numbers": True}, {})
        self.assertIn("counter(page)", css)
        self.assertNotIn(".paged", css)

    def test_variables(self):
        self.assertEqual(style.build_css({}, {"accent": "red", "gap": "1em"}), ".doc { --accent: red; --gap: 1em; }")


if __name__ == "__main__":
    unittest.main()
