import cadquery as cq

from letter_stamps.cli import default_output, main


def test_writes_step(font_path, tmp_path, capsys):
    out = tmp_path / "A.step"
    code = main(["--font", font_path, "--char", "A", "--out", str(out)])
    assert code == 0
    assert out.stat().st_size > 0
    assert "wrote" in capsys.readouterr().out
    assert cq.importers.importStep(str(out)).val().isValid()


def test_writes_stl_with_base(font_path, tmp_path):
    out = tmp_path / "B.stl"
    code = main(
        [
            "--font", font_path,
            "--char", "B",
            "--size", "12",
            "--depth", "5",
            "--draft", "5",
            "--base", "disc",
            "--base-chamfer", "0.4",
            "--out", str(out),
        ]
    )
    assert code == 0
    assert out.stat().st_size > 0


def test_missing_glyph_exits_nonzero(font_path, tmp_path, capsys):
    code = main(
        ["--font", font_path, "--char", "", "--out", str(tmp_path / "x.step")]
    )
    assert code == 1
    assert "letter-stamp:" in capsys.readouterr().err


def test_missing_font_exits_nonzero(tmp_path, capsys):
    code = main(["--font", str(tmp_path / "nope.ttf"), "--char", "A"])
    assert code == 1


def test_default_output_name():
    assert default_output("A") == "stamp_A.step"
    assert default_output("é") == "stamp_u00E9.step"
