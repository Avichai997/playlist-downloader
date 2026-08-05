from playlist_downloader.core import naming


def test_pad_width_follows_playlist_size():
    assert naming.pad_width(9) == 3
    assert naming.pad_width(882) == 3
    assert naming.pad_width(1000) == 4
    assert naming.pad_width(12, configured=5) == 5


def test_padded_numbers_sort_lexically():
    width = naming.pad_width(882)
    names = [naming.number_prefix(n, width) for n in (1, 2, 10, 100, 882)]
    assert names == ["001. ", "002. ", "010. ", "100. ", "882. "]
    assert names == sorted(names)


def test_plain_numbering_does_not_sort_lexically():
    width = naming.pad_width(882)
    names = [naming.number_prefix(n, width, naming.PLAIN) for n in (1, 2, 10)]
    assert names == ["1. ", "2. ", "10. "]
    assert names != sorted(names)


def test_output_template_keeps_ytdlp_fields():
    assert naming.output_template(7, 3) == "007. %(title)s.%(ext)s"
    assert naming.output_template(7, 3, naming.NONE) == "%(title)s.%(ext)s"


def test_sanitize_strips_illegal_characters_but_keeps_hebrew():
    assert naming.sanitize('a/b:c*d?') == "a_b_c_d_"
    assert naming.sanitize("שלום עולם") == "שלום עולם"
    assert naming.sanitize("  trailing.  ") == "trailing"
    assert naming.sanitize("") == "untitled"
    assert naming.sanitize("CON") == "_CON"
