"""移动 Markdown 文件时，它引用的图片跟着搬到新文件夹里同名的图片文件夹。"""
import unittest

from support import RenderTest

import editor


class MoveImages(RenderTest):
    def setUp(self):
        super().setUp()
        (self.root / "b").mkdir()

    def image(self, name, data=b"png-a"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def move(self, source, target):
        return editor.api_move({"root": str(self.root), "from": source, "to": target})

    def test_images_follow_into_same_named_folder(self):
        self.write("a/note.md", "![](_images/x.png)\n<img src=\"fig/y.png\">\n<audio src=\"_images/z.mp3\"></audio>")
        self.image("a/_images/x.png")
        self.image("a/fig/y.png", b"y")
        self.image("a/_images/z.mp3", b"z")
        result = self.move("a/note.md", "b/note.md")
        self.assertEqual(result["images"], {"moved": 3, "copied": 0, "renamed": 0})
        for name in ("b/_images/x.png", "b/fig/y.png", "b/_images/z.mp3"):
            self.assertTrue((self.root / name).is_file(), name)
        self.assertFalse((self.root / "a/_images").exists())  # 搬空的图片文件夹删掉
        self.assertFalse((self.root / "a/fig").exists())

    def test_shared_image_is_copied(self):
        self.write("a/one.md", "![](_images/x.png)")
        self.write("a/two.md", "![](_images/x.png)")
        self.image("a/_images/x.png")
        result = self.move("a/one.md", "b/one.md")
        self.assertEqual(result["images"]["copied"], 1)
        self.assertTrue((self.root / "a/_images/x.png").is_file())
        self.assertTrue((self.root / "b/_images/x.png").is_file())

    def test_name_clash_renames_and_rewrites(self):
        (self.root / "a").mkdir()
        (self.root / "a/note.md").write_bytes(b"first ![a](_images/x.png)\r\nagain ![b](_images/x.png)\r\n")
        self.image("a/_images/x.png", b"mine")
        self.image("b/_images/x.png", b"someone else")
        result = self.move("a/note.md", "b/note.md")
        self.assertEqual(result["images"]["renamed"], 1)
        self.assertTrue(result["images"]["rewritten"])
        self.assertEqual((self.root / "b/_images/x.png").read_bytes(), b"someone else")  # 不覆盖
        self.assertEqual((self.root / "b/_images/x-1.png").read_bytes(), b"mine")
        text = (self.root / "b/note.md").read_bytes().decode()
        self.assertEqual(text, "first ![a](_images/x-1.png)\r\nagain ![b](_images/x-1.png)\r\n")  # 换行没被改

    def test_identical_image_already_there(self):
        self.write("a/note.md", "![](_images/x.png)")
        self.image("a/_images/x.png", b"same")
        self.image("b/_images/x.png", b"same")
        result = self.move("a/note.md", "b/note.md")
        self.assertEqual(result["images"], {"moved": 1, "copied": 0, "renamed": 0})
        self.assertFalse((self.root / "a/_images").exists())

    def test_what_does_not_move(self):
        self.write("a/note.md", "![](https://x.org/a.png) ![](../up.png) ![](/abs.png) ![](missing.png) [doc](other.md)\n"
                                "```\n![](_images/in-code.png)\n```")
        self.image("up.png")
        result = self.move("a/note.md", "b/note.md")
        self.assertNotIn("images", result)
        self.assertTrue((self.root / "up.png").is_file())

    def test_rename_in_same_folder_leaves_images(self):
        self.write("a/note.md", "![](_images/x.png)")
        self.image("a/_images/x.png")
        result = self.move("a/note.md", "a/renamed.md")
        self.assertNotIn("images", result)
        self.assertTrue((self.root / "a/_images/x.png").is_file())

    def test_parentheses_in_name(self):
        self.write("a/note.md", "![](_images/sea%20(1).png) ![](_images/plan(2).png)")
        self.image("a/_images/sea (1).png")
        self.image("a/_images/plan(2).png", b"p")
        result = self.move("a/note.md", "b/note.md")
        self.assertEqual(result["images"]["moved"], 2)
        self.assertTrue((self.root / "b/_images/sea (1).png").is_file())
        self.assertTrue((self.root / "b/_images/plan(2).png").is_file())

    def test_encoded_and_titled_paths(self):
        self.write("a/note.md", '![](_images/my%20pic.png "title") ![](<_images/other pic.png>)')
        self.image("a/_images/my pic.png")
        self.image("a/_images/other pic.png", b"o")
        result = self.move("a/note.md", "b/note.md")
        self.assertEqual(result["images"]["moved"], 2)
        self.assertTrue((self.root / "b/_images/my pic.png").is_file())
        self.assertTrue((self.root / "b/_images/other pic.png").is_file())


if __name__ == "__main__":
    unittest.main()
