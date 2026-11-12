"""单独一行写 @[youtube](...) 或 @[bilibili](...)，生成嵌入的播放器。"""
import re
import unittest

from support import RenderTest

import md_render


def video(source):
    html = md_render.make_markdown().render(source)
    match = re.search(r'<div class="video" data-link="([^"]*)"><iframe src="([^"]+)" title="([^"]*)"', html)
    return (match.group(2).replace("&amp;", "&"), match.group(3), match.group(1).replace("&amp;", "&")) if match else None


class Video(unittest.TestCase):
    def test_links_and_ids(self):
        nocookie = "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"
        cases = {
            "@[youtube](dQw4w9WgXcQ)": nocookie,
            "@[youtube](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m30s)": nocookie + "?start=90",
            "@[youtube](https://www.youtube.com/watch?feature=share&v=dQw4w9WgXcQ)": nocookie,
            "@[youtube](https://youtu.be/dQw4w9WgXcQ?t=90)": nocookie + "?start=90",
            "@[youtube](https://youtube.com/shorts/dQw4w9WgXcQ)": nocookie,
            "@[YouTube](https://m.youtube.com/watch?v=dQw4w9WgXcQ)": nocookie,
            "@[bilibili](BV1GJ411x7h7)": "https://player.bilibili.com/player.html?bvid=BV1GJ411x7h7&autoplay=0",
            "@[bilibili](https://www.bilibili.com/video/BV1GJ411x7h7/?p=2&t=30)":
                "https://player.bilibili.com/player.html?bvid=BV1GJ411x7h7&autoplay=0&p=2&t=30",
        }
        for source, url in cases.items():
            with self.subTest(source=source):
                self.assertEqual(video(source)[0], url)

    def test_title_and_print_link(self):
        self.assertEqual(video('@[youtube](https://youtu.be/dQw4w9WgXcQ?t=90 "Trailer")'),
                         ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?start=90", "Trailer",
                          "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=90s"))
        self.assertEqual(video("@[bilibili](BV1GJ411x7h7)")[2], "https://www.bilibili.com/video/BV1GJ411x7h7")
        self.assertIn("&lt;script&gt;", md_render.make_markdown().render('@[youtube](dQw4w9WgXcQ "<script>")'))

    def test_not_a_video(self):
        for source in ["@[youtube](not-valid)", "@[vimeo](12345)", "text @[youtube](dQw4w9WgXcQ) inline",
                       "    @[youtube](dQw4w9WgXcQ)", "```\n@[youtube](dQw4w9WgXcQ)\n```"]:
            with self.subTest(source=source):
                self.assertIsNone(video(source))

    def test_between_lines_and_in_quotes(self):
        self.assertIsNotNone(video("text\n@[youtube](dQw4w9WgXcQ)\nmore"))
        self.assertIsNotNone(video("> @[youtube](dQw4w9WgXcQ)"))


class VideoInEditor(RenderTest):
    def test_preview_has_line_number(self):
        html = self.render("---\ntemplate: none\n---\ntext\n@[youtube](dQw4w9WgXcQ)")["html"]
        self.assertIn('<div class="video" data-link="https://www.youtube.com/watch?v=dQw4w9WgXcQ" data-line="4">', html)


if __name__ == "__main__":
    unittest.main()
