from grounding_test.scoring import classify, direction, distance_to_box, score_point

BOX = (100, 100, 200, 140)


def test_inside_box_is_hit_including_edges():
    assert classify(150, 120, [BOX], 12) == ("hit", 0.0)
    assert classify(100, 140, [BOX], 12)[0] == "hit"


def test_near_and_miss_use_distance_to_edge():
    assert classify(210, 120, [BOX], 12) == ("near", 10.0)
    assert classify(220, 120, [BOX], 12) == ("miss", 20.0)
    assert distance_to_box(203, 144, BOX) == 5.0  # 3-4-5 from the corner


def test_union_of_boxes_takes_the_closest():
    other = (300, 100, 400, 140)
    assert classify(350, 120, [BOX, other], 12)[0] == "hit"


def test_norm1000_is_scaled_to_the_sent_image():
    # 1920x1080 image, target B centre (1686, 939) == (878, 869) on the 0-1000 grid.
    b = (1536, 907, 1836, 971)
    scores = score_point((878, 869), (1920, 1080), (1920, 1080), [b], 12)
    assert scores["norm1000"]["result"] == "hit"
    assert scores["pixel"]["result"] == "miss"


def test_resized_image_points_map_back_to_original_pixels():
    # Sent at half size: a pixel answer at (75, 60) is (150, 120) on the original.
    scores = score_point((75, 60), (960, 540), (1920, 1080), [BOX], 12)
    assert scores["pixel"]["result"] == "hit"
    assert scores["pixel"]["x"] == 150.0


def test_no_point_scores_none_everywhere():
    scores = score_point(None, (100, 100), (100, 100), [BOX], 12)
    assert {s["result"] for s in scores.values()} == {"none"}


def test_direction_labels():
    assert direction(10, 0) == "phải"
    assert direction(-10, -10) == "trái-trên"
    assert direction(1, 1) == "giữa"
