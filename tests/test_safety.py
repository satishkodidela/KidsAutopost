import safety
from lyrics import Lyrics, Section


def make_lyrics(lines, title="The Happy Song", theme="friends wave at a balloon"):
    return Lyrics(
        title=title,
        description="A happy song.",
        sections=[Section(name="hook", lines=lines, visual_theme=theme),
                  Section(name="verse", lines=["La la la", "Sing with me"], visual_theme=theme)],
    )


def test_clean_lyrics_pass():
    result = safety.lint_lyrics(make_lyrics(["Red balloon, up so high", "Wave hello, you and I"]))
    assert result.ok, result.issues


def test_blocklisted_word_fails():
    result = safety.lint_lyrics(make_lyrics(["The monster waves hello", "So happy"]))
    assert not result.ok
    assert any("monster" in i for i in result.issues)


def test_blocklist_checks_visual_theme_and_title():
    assert not safety.lint_lyrics(make_lyrics(["Happy line", "Happy line"],
                                              theme="a scary dark forest")).ok
    assert not safety.lint_lyrics(make_lyrics(["Happy line", "Happy line"],
                                              title="The Ghost Song")).ok


def test_line_too_long_fails():
    long_line = "we sing and we dance and we play all day long together friends"
    result = safety.lint_lyrics(make_lyrics([long_line, "Short line"]))
    assert not result.ok


def test_wrong_line_count_fails():
    result = safety.lint_lyrics(make_lyrics(["Only one line"]))
    assert not result.ok


def test_blocklist_is_word_bounded():
    # "guns" blocked but "begun" must not trip the "gun" entry
    assert safety.lint_text("the song has begun") == []
    assert safety.lint_text("a toy gun") == ["gun"]
