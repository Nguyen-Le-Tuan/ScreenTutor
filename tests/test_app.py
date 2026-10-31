from PIL import Image

from screentutor.app import masked
from screentutor.still import changed_fraction, signature


def test_our_own_widgets_never_count_as_the_screen_moving():
    a = Image.new("RGB", (1920, 1080), "white")
    b = a.copy()
    b.paste((37, 99, 235), (1650, 960, 1900, 1030))          # the Hỏi button changes colour and words
    rects = [(1640, 950, 1910, 1040)]
    assert changed_fraction(signature(a), signature(b)) > 0.002
    assert changed_fraction(signature(masked(a, rects)), signature(masked(b, rects))) == 0
    assert masked(a, []) is a
