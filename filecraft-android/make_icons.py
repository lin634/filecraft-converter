"""生成 FileCraft 启动图标：蓝色渐变圆角方块 + 白色文档 + 文本线条。
输出到 res/mipmap-{mdpi..xxxhdpi}/ic_launcher.png。"""
import os
from PIL import Image, ImageDraw

S = 1024
MARGIN = 56
RADIUS = 232


def gradient():
    top, bot = (37, 99, 235), (29, 78, 216)  # 站点品牌色 --primary / --primary-dark
    img = Image.new("RGBA", (S, S))
    d = ImageDraw.Draw(img)
    for y in range(S):
        t = y / (S - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (S, y)], fill=c)
    return img


def draw_document(img):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([300, 200, 724, 824], radius=40, fill=(255, 255, 255, 255))
    primary, dark = (37, 99, 235, 255), (29, 78, 216, 255)
    bars = [
        (360, 330, 664, 48, dark),    # 标题条
        (360, 450, 560, 36, primary),
        (360, 550, 640, 36, primary),
        (360, 650, 480, 36, primary),
    ]
    for x0, y0, x1, h, color in bars:
        d.rounded_rectangle([x0, y0, x1, y0 + h], radius=h // 2, fill=color)


icon = gradient()
draw_document(icon)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle(
    [MARGIN, MARGIN, S - MARGIN, S - MARGIN], radius=RADIUS, fill=255)
icon.putalpha(mask)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "res")
for dpi, px in {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}.items():
    d = os.path.join(out, "mipmap-" + dpi)
    os.makedirs(d, exist_ok=True)
    icon.resize((px, px), Image.LANCZOS).save(os.path.join(d, "ic_launcher.png"))
print("icons ok")
