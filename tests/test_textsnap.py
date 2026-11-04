import numpy as np
from PIL import Image, ImageDraw

from screentutor.textsnap import snap_drag, words


def _line():
    """A dark chat bubble with one line of light text, words 8 px apart and their edges known."""
    img = Image.new("RGB", (900, 120), (40, 52, 70))
    d = ImageDraw.Draw(img)
    edges, x = [], 40
    for word in ("Vào", "trang", "boiduong-thunghiem.example", "và", "đăng"):
        left = x
        for ch in word:   # letters as bars 2 px apart, so the test does not hang on a font
            d.rectangle((x, 50, x + 6, 68), fill=(235, 235, 235))
            x += 8
        edges.append((left, x - 2))
        x += 12            # a space: 14 px of background after the last bar
    return img, edges


def test_words_are_told_apart_by_their_gaps():
    img, edges = _line()
    grey = np.asarray(img.convert("L"), dtype=np.int16)
    assert words(grey, 50, 68, 0, 900) == edges


def test_a_drag_that_starts_inside_the_address_takes_all_of_it():
    img, edges = _line()
    address = edges[2]
    a, b = snap_drag(img, (address[0] + 60, 52), (address[1] - 10, 52))   # starts inside, ends inside
    assert a[0] == address[0] - 2 and b[0] == address[1] + 2 and a[1] == b[1] == 59


def test_a_drag_from_the_end_of_the_word_before_is_meant_for_the_next_one():
    img, edges = _line()
    a, b = snap_drag(img, (edges[1][1], 59), (edges[2][1] - 4, 59))
    assert a[0] == edges[2][0] - 2


def test_with_no_writing_near_the_drag_is_left_as_it_was():
    img = Image.new("RGB", (400, 200), (255, 255, 255))
    assert snap_drag(img, (50, 100), (300, 100)) == ((50, 100), (300, 100))


def test_the_words_to_select_decide_the_end_when_the_model_overshoots():
    img, edges = _line()
    address = edges[2]
    a, b = snap_drag(img, (address[0] + 30, 59), (edges[4][1] - 3, 59), "boiduong-thunghiem.example")
    assert (a[0], b[0]) == (address[0] - 2, address[1] + 2)          # not on to "và đăng"
    a, b = snap_drag(img, (address[0] + 30, 59), (address[0] + 40, 59), "boiduong-thunghiem.example và")
    assert b[0] == edges[3][1] + 2                                   # two words: up to "và"
