from screentutor.listen import KEYWORDS, TurnCollector, handshake


def test_handshake_carries_the_key_and_the_t3_settings():
    h = handshake("sk-test", "ENDPOINTING")
    assert h["authorization"] == {"accessToken": "Bearer sk-test"}
    assert (h["audioEncoding"], h["model"], h["mode"]) == ("PCM_24KHZ", "muse-voice-transcribe-1.0", "ENDPOINTING")
    assert h["languageBias"] == ["Vietnamese"] and "mẹ" in KEYWORDS and "giáo án" in KEYWORDS


def test_endpointing_joins_turns_until_close():
    partials, now = [], [0.0]
    c = TurnCollector("ENDPOINTING", partials.append, clock=lambda: now[0])
    events = [{"type": "speechStart", "turnId": 1},
              {"type": "transcript", "transcript": "nó nằm ở", "final": False},
              {"type": "speechComplete", "turnId": 1, "transcript": "File báo cáo nằm ở đâu vậy."}]
    assert [c.feed(e) for e in events] == [False] * 3
    assert c.pending_since == 0.0 and c.heard.text is None       # waiting to see whether she goes on
    now[0] = 0.8
    c.feed({"type": "speechStart", "turnId": 2})
    assert c.pending_since is None                               # she went on: keep listening
    c.feed({"type": "transcript", "transcript": "sao mở ra", "final": False})
    assert partials[-1] == "File báo cáo nằm ở đâu vậy. sao mở ra"
    now[0] = 3.0
    c.feed({"type": "speechComplete", "turnId": 2, "transcript": "Sao mở ra trống trơn."})
    c.close()
    assert c.heard.text == "File báo cáo nằm ở đâu vậy. Sao mở ra trống trơn." and c.heard.turns == 2


def test_overlapping_turns_do_not_close_early():
    c = TurnCollector("ENDPOINTING", clock=lambda: 1.0)
    c.feed({"type": "speechStart", "turnId": 1})
    c.feed({"type": "speechStart", "turnId": 2})       # the next turn opened before the first was complete
    c.feed({"type": "speechComplete", "turnId": 1, "transcript": "Mẹ muốn"})
    assert c.pending_since is None
    c.feed({"type": "speechComplete", "turnId": 2, "transcript": "gửi file."})
    assert c.pending_since == 1.0


def test_push_to_talk_ends_on_the_final_transcript():
    c = TurnCollector("PUSH_TO_TALK", clock=lambda: 5.0)
    assert c.feed({"type": "transcript", "transcript": "bấm vào đâu", "final": False}) is False
    assert c.feed({"type": "speechComplete", "turnId": 1, "transcript": "x"}) is False  # not used in this mode
    assert c.feed({"type": "transcript", "transcript": "Bấm vào đâu?", "final": True}) is True
    assert c.heard.text == "Bấm vào đâu?"


def test_error_and_silence():
    c = TurnCollector("ENDPOINTING")
    assert c.feed({"type": "error", "message": "invalid request"}) is True and c.heard.error == "invalid request"
    c = TurnCollector("PUSH_TO_TALK")
    assert c.feed({"type": "transcript", "transcript": "", "final": True}) is True and c.heard.text is None


def test_t7a_replay_joins_turns_that_start_within_the_wait():
    from tutor_eval.voice import replay

    tl = [(0.5, "speechStart", 1, "", 300), (2.0, "speechEnd", 1, "", 1800),
          (2.1, "speechComplete", 1, "File báo cáo nằm ở đâu vậy.", 1800),
          (3.3, "speechStart", 2, "", 3000), (5.0, "speechEnd", 2, "", 4800),
          (5.1, "speechComplete", 2, "Sao mà mở lên không thấy.", 4800), (7.0, "transcript", None, "", None)]
    assert replay(tl, 0.0, 1.0)[0] == "File báo cáo nằm ở đâu vậy."                     # the pause was 1.2 s: cut
    text, wait = replay(tl, 0.0, 1.5)
    assert text == "File báo cáo nằm ở đâu vậy. Sao mà mở lên không thấy." and abs(wait - (5.1 + 1.5 - 4.8)) < 1e-9
