"""清理未使用的图片：只列出没有被任何 Markdown 或 HTML 引用的图片，删除时移到回收站。"""
import unittest
from unittest import mock

from support import RenderTest

import editor
from paths import ApiError


class CleanImages(RenderTest):
    def setUp(self):
        super().setUp()
        self.trashed = []
        patcher = mock.patch.object(editor, "send2trash", side_effect=self.fake_trash)  # 测试不往真的回收站里放东西
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_trash(self, path):
        self.trashed.append(path)
        __import__("os").remove(path)

    def image(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 10)

    def unused(self, folder=None):
        return [item["path"] for item in editor.api_unused_images(str(self.root), folder)["images"]]

    def test_finds_only_unreferenced(self):
        self.write("a/note.md", "![](_images/used.png)\n<img src=\"fig/html.png\">\n<audio src=\"_images/rec.mp3\"></audio>\n"
                                "[pdf](files/a.pdf) [pic](_images/linked.png)\n[ref]: _images/refstyle.png\n"
                                "![](_images/sea%20(1).png)")
        for name in ("a/_images/used.png", "a/fig/html.png", "a/_images/rec.mp3", "a/_images/linked.png",
                     "a/_images/refstyle.png", "a/_images/sea (1).png", "a/_images/orphan.png", "a/fig/old.jpg"):
            self.image(name)
        self.assertEqual(self.unused(), ["a/_images/orphan.png", "a/fig/old.jpg"])

    def test_references_from_other_folders_and_html(self):
        self.write("b/post.md", "![](../a/_images/shared.png)")
        self.write("lab/page.html", '<img src="../a/_images/from-html.png">')
        self.write("c/root.md", "![](/a/_images/rooted.png)")
        for name in ("a/_images/shared.png", "a/_images/from-html.png", "a/_images/rooted.png", "a/_images/orphan.png"):
            self.image(name)
        self.assertEqual(self.unused(), ["a/_images/orphan.png"])

    def test_scope_is_the_selected_folder(self):
        self.image("a/_images/one.png")
        self.image("b/_images/two.png")
        self.assertEqual(self.unused("a"), ["a/_images/one.png"])
        self.assertEqual(self.unused(), ["a/_images/one.png", "b/_images/two.png"])

    def test_skips_hidden_and_non_media(self):
        self.image(".git/x.png")
        self.image("node_modules/pkg/x.png")
        self.image("a/data.csv")
        self.assertEqual(self.unused(), [])

    def test_trash_rechecks_and_removes_empty_folder(self):
        self.image("a/_images/orphan.png")
        self.image("a/_images/now-used.png")
        self.write("a/note.md", "![](_images/now-used.png)")  # 列出来之后又被引用了
        result = editor.api_trash_images({"root": str(self.root), "paths": ["a/_images/orphan.png", "a/_images/now-used.png"]})
        self.assertEqual(result, {"trashed": ["a/_images/orphan.png"], "kept": ["a/_images/now-used.png"]})
        self.assertTrue((self.root / "a/_images/now-used.png").exists())
        self.image("b/_images/last.png")
        editor.api_trash_images({"root": str(self.root), "paths": ["b/_images/last.png"]})
        self.assertFalse((self.root / "b/_images").exists())  # 清空了的图片文件夹删掉

    def test_trash_refuses_non_images_and_outside(self):
        self.write("a/note.md", "text")
        for paths in (["a/note.md"], ["../outside.png"], "a/x.png"):
            with self.subTest(paths=paths), self.assertRaises(ApiError):
                editor.api_trash_images({"root": str(self.root), "paths": paths})
        self.assertEqual(self.trashed, [])


if __name__ == "__main__":
    unittest.main()
