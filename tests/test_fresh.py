from PIL import Image, ImageDraw

from screentutor.fresh import MARK_R, compare

DARK = (30, 30, 30)


def _screen():
    img = Image.new("RGB", (1920, 1080), DARK)
    d = ImageDraw.Draw(img)
    for i in range(12):   # a chat list: rows of text
        d.text((80, 120 + 60 * i), f"Tin nhắn số {i} gửi lúc 12:3{i % 10}", fill=(220, 220, 220), font_size=24)
    return img


def _toast(img):
    d = ImageDraw.Draw(img)
    d.rectangle((60, 940, 560, 1000), fill=(52, 52, 56))
    d.text((90, 955), "Đã tải xong      Mở thư mục      X", fill=(240, 240, 240), font_size=24)
    return img


def test_the_same_screen_is_fresh():
    change = compare(_screen(), _screen(), (400, 500))
    assert change.region == 0 and change.whole == 0 and not change.stale


def test_a_toast_that_has_gone_is_stale():
    change = compare(_toast(_screen()), _screen(), (405, 970))
    assert change.region >= 0.03 and change.stale


def test_a_box_that_came_up_away_from_the_target_is_stale():
    after = _screen()
    d = ImageDraw.Draw(after)
    d.rectangle((700, 300, 1250, 520), fill=(240, 240, 240))   # Confirm Save As, above the button
    d.text((740, 360), "Giáo án.pdf already exists. Replace it?", fill=(0, 0, 0), font_size=24)
    change = compare(_screen(), after, (980, 700))
    assert change.region == 0 and change.whole >= 0.02 and change.stale


def test_a_row_lit_by_the_mouse_is_fresh():
    after = _screen()
    ImageDraw.Draw(after).rectangle((60, 290, 900, 340), fill=(48, 48, 48))   # +18 grey: hover
    after.paste(_screen().crop((60, 290, 900, 340)).point(lambda v: min(v + 18, 255)), (60, 290))
    assert not compare(_screen(), after, (400, 315)).stale


def test_our_widgets_the_edge_and_the_mark_are_left_out():
    after = _screen()
    d = ImageDraw.Draw(after)
    d.rectangle((760, 0, 1160, 120), fill=(0, 0, 0))                    # the island grew
    d.rectangle((0, 0, 1920, 40), fill=(255, 60, 140))                  # the glow
    x, y = 400, 500
    d.ellipse((x - MARK_R + 5, y - MARK_R + 5, x + MARK_R - 5, y + MARK_R - 5), outline=(255, 69, 58), width=6)
    change = compare(_screen(), after, (x, y), ignore=[(760, 0, 1160, 120)])
    assert change.region == 0 and change.whole == 0


def test_a_taskbar_icon_is_compared_on_what_is_left_above_the_edge():
    target = (960, 1065)                                   # inside the edge band, under the glow
    assert not compare(_screen(), _screen(), target).stale
    after = _screen()
    ImageDraw.Draw(after).rectangle((800, 960, 1120, 1030), fill=(240, 240, 240))   # a preview came up over it
    assert compare(_screen(), after, target).region >= 0.03
