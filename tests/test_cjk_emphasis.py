"""中文里的粗体：** 一边是中文、一边是标点时也算粗体；其他写法和标准 Markdown 一样。"""
import unittest

from markdown_it import MarkdownIt

import md_render
import support  # noqa: F401  把编辑器文件夹加进 sys.path


class CjkEmphasis(unittest.TestCase):
    def test_bold_next_to_cjk_punctuation(self):
        md = md_render.make_markdown()
        cases = {
            "觉醒的**“第一阶段”**。让我": "觉醒的<strong>“第一阶段”</strong>。让我",
            "**码组同步（CGS）与帧同步（ILAS）**流程": "<strong>码组同步（CGS）与帧同步（ILAS）</strong>流程",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(md.renderInline(source), expected)

    def test_everything_else_is_standard(self):
        md, standard = md_render.make_markdown(), MarkdownIt()
        for source in ["这是**重点**内容", "a **b** c", "snake*case*word", "2*3*4", "用 * 号和 ** 号", "_下划线_", "x **(note)** y"]:
            with self.subTest(source=source):
                self.assertEqual(md.renderInline(source), standard.renderInline(source))

    def test_other_parsers_unchanged(self):
        self.assertEqual(MarkdownIt().renderInline("的**“阶段”**。"), "的**“阶段”**。")


if __name__ == "__main__":
    unittest.main()
