"""模板的查找、继承和合并。"""
import re
import unittest

from support import APP_DIR, RenderTest

SCOPE = ".doc.doc.doc.doc.doc {"


def variable(data, name):
    found = re.search(rf"--{name}: ([^;]+);", data["template_css"])
    return found.group(1) if found else None


class Library(RenderTest):
    def test_plain_document_has_no_template(self):
        data = self.render("---\ntitle: t\nstyle:\n  a: 1\ncss: ./x.css\n---\nx")
        self.assertEqual((data["doc_class"], data["template_css"], data["warning"]), ("", "", ""))
        self.assertTrue(data["show_head"])

    def test_report_works_in_any_folder(self):
        data = self.render("---\ntemplate: report\n---\n# a")
        self.assertEqual(data["doc_class"], "numbered paged")
        self.assertEqual(data["warning"], "")
        self.assertFalse(data["show_head"])
        self.assertEqual(variable(data, "font-size"), "12pt")

    def test_builtin_bases(self):
        numbered = self.render("---\ntemplate: numbered\n---\n# a")
        self.assertEqual(numbered["doc_class"], "numbered")
        self.assertIn("heading-number", numbered["html"])
        plain = self.render("---\ntemplate: none\n---\n# a")
        self.assertEqual(plain["doc_class"], "")
        self.assertNotIn("heading-number", plain["html"])

    def test_open_folder_comes_first(self):
        self.write("templates/resume.md", "---\nextends: none\ncss: ./r.css\nstyle:\n  c: blue\n---\n")
        self.write("templates/r.css", "h1 { color: var(--c); }")
        self.assertEqual(variable(self.render("---\ntemplate: resume\n---\nx"), "c"), "blue")

    def test_found_from_a_subfolder(self):
        self.write("templates/mine.md", "---\nextends: report\nstyle:\n  font-size: 小五\n---\n")
        self.assertEqual(variable(self.render("---\ntemplate: mine\n---\nx", path="a/b/doc.md"), "font-size"), "9pt")

    def test_overriding_report_can_inherit_it(self):
        self.write("templates/report.md", "---\nextends: report\nstyle:\n  font-size: 小五\n---\n")
        data = self.render("---\ntemplate: report\n---\nx")
        self.assertEqual(variable(data, "font-size"), "9pt")
        self.assertEqual(variable(data, "title-size"), "22pt")
        self.assertEqual(data["warning"], "")

    def test_builtin_bases_cannot_be_overridden(self):
        self.write("templates/numbered.md", "---\nextends: none\n---\n")
        self.assertEqual(self.render("---\ntemplate: numbered\n---\n# a")["doc_class"], "numbered")

    def test_unknown_lists_the_names(self):
        self.write("templates/mine.md", "---\nextends: none\n---\n")
        self.write("templates/.hidden.md", "---\nextends: none\n---\n")
        warning = self.render("---\ntemplate: nope\n---\nx")["warning"]
        for name in ("mine", "numbered", "report", "resume"):
            self.assertIn(name, warning)
        self.assertNotIn("hidden", warning)

    def test_names_cannot_be_paths(self):
        self.write("secret.md", "---\nextends: none\n---\n")
        for name in ["../secret", "..\\secret", "sub/local", "/etc/passwd", "C:/x", ".hidden", "local.", "local ", 5, ["a"], {"a": "b"}]:
            with self.subTest(name=name):
                data = self.render(f"---\ntemplate: {name!r}\n---\nx")
                self.assertEqual(data["doc_class"], "")
                self.assertTrue(data["warning"])


class Files(RenderTest):
    def test_path_is_relative_to_the_document(self):
        self.write("a/school.md", "---\nextends: report\nstyle:\n  font-size: 五号\n---\n")
        self.assertEqual(variable(self.render("---\ntemplate: ./school.md\n---\nx", path="a/doc.md"), "font-size"), "10.5pt")
        self.assertEqual(variable(self.render("---\ntemplate: ../a/school.md\n---\nx", path="b/doc.md"), "font-size"), "10.5pt")

    def test_template_cannot_leave_the_folder(self):
        (self.work / "outside.md").write_text("---\nextends: none\n---\n", encoding="utf-8")
        for template in ("../outside.md", (self.work / "outside.md").as_posix()):
            with self.subTest(template):
                data = self.render(f"---\ntemplate: {template}\n---\nx")
                self.assertIn("Cannot read", data["warning"] or "Cannot read")
                self.assertEqual(data["doc_class"], "")

    def test_broken_template_falls_back_to_a_plain_document(self):
        self.write("no-extends.md", "---\ntitle: x\n---\n")
        self.write("broken.md", "---\nextends: [\n---\n")
        (self.root / "gbk.md").write_bytes("---\nextends: none\ntitle: 中文\n---\n".encode("gbk"))
        for name in ("no-extends", "broken", "gbk", "missing"):
            with self.subTest(name):
                data = self.render(f"---\ntemplate: ./{name}.md\n---\n# a")
                self.assertEqual(data["doc_class"], "")
                self.assertTrue(data["warning"])
                self.assertNotIn("heading-number", data["html"])

    def test_crlf_and_bom(self):
        (self.root / "crlf.md").write_bytes("\ufeff---\r\nextends: report\r\nstyle:\r\n  font-size: 四号\r\n---\r\n".encode("utf-8"))
        self.assertEqual(variable(self.render("---\ntemplate: ./crlf.md\n---\nx"), "font-size"), "14pt")


class Inheritance(RenderTest):
    def setUp(self):
        super().setUp()
        self.write("school.md", "---\nextends: report\nlang: en\nstyle:\n  font-size: 五号\n  numbering: '2.1'\n---\nsample\n")
        self.write("dept.md", "---\nextends: ./school.md\ncss: ./dept.css\npdf-bookmarks: false\nstyle:\n  dept-color: red\n  font-size: 四号\n---\n")
        self.write("dept.css", "h1 { color: var(--dept-color); }")
        self.write("sub/deep.md", "---\nextends: ../dept.md\nstyle:\n  dept-color: blue\n---\n")

    def test_layers_override_in_order(self):
        data = self.render("---\ntemplate: ./sub/deep.md\n---\nx")
        self.assertEqual(variable(data, "dept-color"), "blue")
        self.assertEqual(variable(data, "font-size"), "14pt")
        self.assertEqual(variable(data, "title-size"), "22pt")
        self.assertEqual(data["warning"], "")

    def test_document_wins(self):
        data = self.render("---\ntemplate: ./sub/deep.md\nstyle:\n  dept-color: green\n  font-size: 小四\n---\nx")
        self.assertEqual(variable(data, "dept-color"), "green")
        self.assertEqual(variable(data, "font-size"), "12pt")

    def test_css_order_is_base_then_parent_then_child(self):
        css = self.render("---\ntemplate: ./dept.md\n---\nx")["template_css"]
        self.assertEqual(css.count(SCOPE), 3)
        self.assertLess(css.index(".figure-group"), css.index(".doc-title"))
        self.assertLess(css.index(".doc-title"), css.index("var(--dept-color)"))

    def test_lang_and_bookmarks_inherit(self):
        data = self.render("---\ntemplate: ./dept.md\n---\nx")
        self.assertEqual(data["toc_title"], "Contents")
        self.assertFalse(data["pdf_bookmarks"])
        data = self.render("---\ntemplate: ./dept.md\nlang: zh\npdf-bookmarks: true\n---\nx")
        self.assertEqual(data["toc_title"], "目录")
        self.assertTrue(data["pdf_bookmarks"])

    def test_nearest_lang_wins(self):
        self.write("zh.md", "---\nextends: ./school.md\nlang: zh\n---\n")
        self.assertEqual(self.render("---\ntemplate: ./zh.md\n---\nx")["toc_title"], "目录")

    def test_numbering_comes_through(self):
        self.assertIn("Figure 1.1", self.render("---\ntemplate: ./sub/deep.md\n---\n# a\n\n![t](a.png)")["html"])

    def test_opening_a_template_shows_its_effect(self):
        data = self.render((self.root / "dept.md").read_text(encoding="utf-8"), path="dept.md")
        self.assertEqual(data["doc_class"], "numbered paged")
        self.assertEqual(variable(data, "dept-color"), "red")

    def test_cycles_stop(self):
        self.write("a.md", "---\nextends: ./b.md\n---\n")
        self.write("b.md", "---\nextends: ./a.md\n---\n")
        self.write("self.md", "---\nextends: ./self.md\n---\n")
        for template, path in (("./a.md", "doc.md"), ("./self.md", "doc.md")):
            with self.subTest(template):
                data = self.render(f"---\ntemplate: {template}\n---\nx", path=path)
                self.assertIn("extends itself", data["warning"])
                self.assertEqual(data["doc_class"], "")
        data = self.render((self.root / "self.md").read_text(encoding="utf-8"), path="self.md")
        self.assertIn("extends itself", data["warning"])

    def test_several_parents_are_not_supported(self):
        data = self.render("---\nextends: [report, none]\n---\nx", path="t.md")
        self.assertIn("Unknown template", data["warning"])


class TemplateCss(RenderTest):
    def template(self, css_line):
        self.write("t.md", f"---\nextends: none\n{css_line}\n---\n")
        return self.render("---\ntemplate: ./t.md\n---\nx")

    def test_css_is_relative_to_the_template(self):
        self.write("sub/rel.css", "h1 { color: var(--c); }")
        self.write("sub/rel.md", "---\nextends: none\ncss: ./rel.css\nstyle:\n  c: red\n---\n")
        data = self.render("---\ntemplate: sub/rel.md\n---\nx")
        self.assertEqual((variable(data, "c"), data["warning"]), ("red", ""))

    def test_css_problems(self):
        (self.work / "outside.css").write_text("h1 {}", encoding="utf-8")
        self.write("a.txt", "h1 {}")
        (self.root / "gbk.css").write_bytes("/* 中文 */".encode("gbk"))
        for css in ("no-such.css", "../outside.css", "a.txt", "gbk.css", "5"):
            with self.subTest(css):
                data = self.template(f"css: {css}")
                self.assertIn("Cannot read template CSS", data["warning"])
                self.assertNotIn(SCOPE, data["template_css"])

    def test_bad_css_is_not_used_at_all(self):
        self.write("bad.css", "h1{color:red}} body{display:none}")
        data = self.template("css: ./bad.css")
        self.assertIn("was not used", data["warning"])
        self.assertNotIn("display:none", data["template_css"])

    def test_options_must_be_used_by_the_css(self):
        self.write("ok.css", "h1 { color: var(--accent); }")
        self.write("t.md", "---\nextends: none\ncss: ./ok.css\nstyle:\n  accent: red\n  typo: 1\n---\n")
        data = self.render("---\ntemplate: ./t.md\n---\nx")
        self.assertEqual(data["warning"], 'Unknown style option "typo"')

    def test_css_field_in_a_document_is_ignored(self):
        self.write("x.css", "h1 { color: red; }")
        self.assertNotIn("color: red", self.render("---\ntemplate: report\ncss: ./x.css\n---\nx")["template_css"])


class PdfBookmarks(RenderTest):
    def test_default_and_override(self):
        self.assertTrue(self.render("x")["pdf_bookmarks"])
        self.assertFalse(self.render("---\npdf-bookmarks: false\n---\nx")["pdf_bookmarks"])
        self.assertFalse(self.render("---\ntemplate: resume\n---\nx")["pdf_bookmarks"])
        self.assertTrue(self.render("---\ntemplate: resume\npdf-bookmarks: true\n---\nx")["pdf_bookmarks"])

    def test_wrong_value_keeps_the_template_value(self):
        data = self.render("---\ntemplate: resume\npdf-bookmarks: nope\n---\nx")
        self.assertFalse(data["pdf_bookmarks"])
        self.assertIn("pdf-bookmarks", data["warning"])


class WhatShips(RenderTest):
    """编辑器自带的模板和示例不能有警告。"""

    def test_library_templates(self):
        for path in (APP_DIR / "templates").glob("*.md"):
            with self.subTest(path.name):
                data = self.render(path.read_text(encoding="utf-8"), path=f"templates/{path.name}", root=APP_DIR)
                self.assertEqual(data["warning"], "")

    def test_examples(self):
        for path in (APP_DIR / "examples").rglob("*.md"):
            with self.subTest(path.name):
                data = self.render(path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n"), path=path.name, root=path.parent)
                self.assertEqual(data["warning"], "")


if __name__ == "__main__":
    unittest.main()
