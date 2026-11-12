"""表情名字（:sob:）换成表情字符。"""
import unittest

import md_render
import support  # noqa: F401  把编辑器文件夹加进 sys.path


class Emoji(unittest.TestCase):
    def test_names(self):
        md = md_render.make_markdown()
        cases = {
            "哈哈 :clown_face: 好": "哈哈 🤡 好",
            "落泪了:sob:": "落泪了😭",
            ":sob::rofl:": "😭🤣",
            "**:fire:**": "<strong>🔥</strong>",
            "`:sob:`": "<code>:sob:</code>",
            "12:30:45": "12:30:45",
            "a:smile:b": "a:smile:b",
            ":huanhu:": ":huanhu:",
            "http://x.org/a:b:c": "http://x.org/a:b:c",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(md.renderInline(source), expected)


if __name__ == "__main__":
    unittest.main()
