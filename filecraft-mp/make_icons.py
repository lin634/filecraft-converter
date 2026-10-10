# 生成小程序 tabBar 图标（4 个 tab × 常规/选中 2 态）
# 与 Web 版配色一致：灰 #9ca3af、主题蓝 #2563eb
from PIL import Image, ImageDraw
import os

OUT = os.path.join(os.path.dirname(__file__), "assets", "tab")
os.makedirs(OUT, exist_ok=True)
SIZE = 96
GRAY = (156, 163, 175, 255)
BLUE = (37, 99, 235, 255)


def canvas():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def rounded_rect(d, box, radius, fill, width=0, outline=None):
    d.rounded_rectangle(box, radius=radius, fill=fill, width=width, outline=outline)


def draw_files(c):
    """文档：两张叠放的纸"""
    d = ImageDraw.Draw(c)
    # 后面的纸
    rounded_rect(d, (30, 16, 78, 80), 8, None, width=6, outline=(156, 163, 175, 120))
    # 前面的纸
    rounded_rect(d, (18, 26, 66, 84), 8, c.getpixel((1, 1)))  # clear spacer
    rounded_rect(d, (18, 26, 66, 84), 8, None, width=6, outline=(0, 0, 0, 0))
    return d


def icon_files(color):
    img, d = canvas()
    # 后纸（浅）
    d.rounded_rectangle((32, 14, 80, 76), radius=8, width=6,
                        outline=(color[0], color[1], color[2], 110))
    # 前纸
    d.rounded_rectangle((16, 24, 64, 84), radius=8, width=6, outline=color)
    # 文字行
    for y in (42, 56, 70):
        d.line((28, y, 52, y), fill=color, width=5)
    return img


def icon_summary(color):
    """AI 总结：四角星 + 小星"""
    img, d = canvas()

    def star4(cx, cy, r, fill):
        pts = []
        import math
        for i in range(8):
            ang = math.pi / 4 * i - math.pi / 2
            rad = r if i % 2 == 0 else r * 0.36
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        d.polygon(pts, fill=fill)

    star4(44, 48, 30, color)
    star4(74, 26, 12, color)
    return img


def icon_qa(color):
    """问答：圆角气泡 + 三个点"""
    img, d = canvas()
    d.rounded_rectangle((12, 18, 84, 70), radius=18, width=6, outline=color)
    d.polygon([(34, 70), (34, 88), (52, 70)], fill=None, outline=None)
    # 气泡尾巴（三角形描边简化为实心）
    d.polygon([(30, 66), (30, 88), (50, 66)], fill=color)
    for cx in (34, 48, 62):
        d.ellipse((cx - 4, 40, cx + 4, 48), fill=color)
    return img


def icon_me(color):
    """我的：头 + 肩"""
    img, d = canvas()
    d.ellipse((34, 12, 62, 40), width=6, outline=color)
    # 肩膀弧线
    d.arc((18, 46, 78, 104), start=180, end=360, fill=color, width=6)
    d.line((18, 74, 18, 80), fill=color, width=6)
    d.line((78, 74, 78, 80), fill=color, width=6)
    return img


icons = {
    "files": icon_files,
    "summary": icon_summary,
    "qa": icon_qa,
    "me": icon_me,
}

for name, fn in icons.items():
    fn(GRAY).save(os.path.join(OUT, f"{name}.png"))
    fn(BLUE).save(os.path.join(OUT, f"{name}-active.png"))

print("generated:", sorted(os.listdir(OUT)))
