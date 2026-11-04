import threading

from screentutor.speak import Speaker, for_speech


def test_file_names_are_read_like_a_person_would():
    assert for_speech("Bạn mở file Giáo án mẫu Âm nhạc 8 (1).docx trong Downloads nhé.") == \
        "Bạn mở file Giáo án mẫu Âm nhạc 8 số 1, bản Word trong Downloads nhé."
    assert for_speech("Bản Giáo án 8.pdf đã lưu.") == "Bản Giáo án 8, bản PDF đã lưu."
    assert for_speech("Mở Bảng kê.xlsx") == "Mở Bảng kê, bản Excel"


def test_buttons_symbols_and_times():
    assert for_speech("Bạn bấm vào nút O K nhé.") == "Bạn bấm vào nút ô kê nhé."
    assert for_speech("Bạn bấm nút OK.") == "Bạn bấm nút ô kê."
    assert for_speech("Bạn bấm vào nút Create PDF/XPS.") == "Bạn bấm vào nút Create PDF."
    assert for_speech("Chọn Word/Excel.") == "Chọn Word Excel."
    assert for_speech("File sửa lúc 21:05 hôm qua.") == "File sửa lúc 21 giờ 5 hôm qua."
    assert for_speech("Bạn bấm vào chữ \"Save\" (màu xanh)…") == "Bạn bấm vào chữ Save màu xanh."


def test_plain_sentences_are_untouched():
    s = "Bạn bấm vào chữ File ở góc trên bên trái để mở mục lưu và xuất tài liệu."
    assert for_speech(s) == s
    assert for_speech("Bạn bấm vào nút Book nhé.") == "Bạn bấm vào nút Book nhé."  # "OK" inside a word stays


class FakeEngine:
    def __init__(self):
        self.calls = []

    def infer_stream(self, text, voice):
        self.calls.append((text, voice))
        for i in range(5):
            yield [0.0] * 10


def test_speaker_plays_the_normalised_text_and_can_be_stopped():
    played = []

    def play(chunks, stop):
        for i, c in enumerate(chunks):
            if stop.is_set():
                return
            played.append(c)
            if i == 1:
                stop.set()  # as if the user clicked while the tutor was talking

    engine = FakeEngine()
    spk = Speaker(engine=engine, play=play)
    assert spk.speak("Bạn bấm nút OK.") == "Bạn bấm nút ô kê."
    assert engine.calls == [("Bạn bấm nút ô kê.", "Hải Đăng")] and len(played) == 2
    played.clear()
    spk.speak("Bạn bấm File.")  # a new sentence starts with the stop flag cleared
    assert len(played) == 2


def test_stop_from_another_thread():
    started, stopped = threading.Event(), []

    def play(chunks, stop):
        started.set()
        stopped.append(stop.wait(timeout=2))

    spk = Speaker(engine=FakeEngine(), play=play)
    t = threading.Thread(target=spk.speak, args=("Bạn bấm File.",))
    t.start()
    started.wait(1)
    spk.stop()
    t.join(2)
    assert stopped == [True]


def test_the_meter_follows_the_voice_and_drops_to_zero_after():
    import numpy as np

    class LoudEngine:
        def infer_stream(self, text, voice):
            yield np.full(48000 // 10, 0.3, dtype=np.float32)  # 0.1 s at a steady loud level

    seen = []
    spk = Speaker(engine=LoudEngine(), play=lambda chunks, stop: [seen.append(spk.meter.value) for _ in chunks])
    spk.speak("Bạn bấm File.")
    assert len(seen) == 3 and seen[0] > 0.5 and seen[-1] >= seen[0]  # 40 ms blocks, metered as they go out
    assert spk.meter.value == 0.0


def test_on_sound_comes_once_as_the_player_takes_the_first_block():
    order = []
    spk = Speaker(engine=FakeEngine(), play=lambda chunks, stop: [order.append("block") for _ in chunks])
    spk.speak("Bạn bấm File.", on_sound=lambda: order.append("sound"))
    assert order == ["block", "sound", "block", "block", "block", "block"]


def test_on_sound_still_comes_when_no_sound_went_out():
    calls = []
    spk = Speaker(engine=FakeEngine(), play=lambda chunks, stop: None)   # stopped before the first block
    spk.speak("Bạn bấm File.", on_sound=lambda: calls.append("stopped"))
    spk.speak("()", on_sound=lambda: calls.append("nothing to read"))

    class Broken:
        def infer_stream(self, text, voice):
            raise RuntimeError("no model")

    try:
        Speaker(engine=Broken(), play=lambda chunks, stop: list(chunks)).speak("Bạn bấm File.",
                                                                              on_sound=lambda: calls.append("failed"))
    except RuntimeError:
        pass
    assert calls == ["stopped", "nothing to read", "failed"]


def test_keys_are_said_the_way_people_here_say_them():
    assert for_speech("Bạn bấm giữ phím Ctrl rồi bấm phím C.") == "Bạn bấm giữ phím con trôn rồi bấm phím xê."
    assert for_speech("Bấm Ctrl+V rồi bấm Enter.") == "Bấm con trôn vê rồi bấm en tơ."
    assert for_speech("Bấm Ctrl + A để chọn hết.") == "Bấm con trôn a để chọn hết."
