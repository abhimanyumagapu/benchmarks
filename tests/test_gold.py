from stead.gold import Gold


def test_hit_inside_window_same_file():
    g = Gold(file="rtl/ibex_alu.sv", start=384, end=388, klass="logic")
    assert g.hit("rtl/ibex_alu.sv", 386)
    assert g.hit("rtl/ibex_alu.sv", 384) and g.hit("rtl/ibex_alu.sv", 388)


def test_miss_outside_window_or_other_file():
    g = Gold(file="rtl/ibex_alu.sv", start=384, end=388, klass="logic")
    assert not g.hit("rtl/ibex_alu.sv", 389)
    assert not g.hit("rtl/ibex_decoder.sv", 386)


def test_hit_normalises_leading_dot_slash():
    g = Gold(file="rtl/ibex_alu.sv", start=386, end=386, klass="logic")
    assert g.hit("./rtl/ibex_alu.sv", 386)


def test_yaml_roundtrip(tmp_path):
    g = Gold(file="rtl/a.sv", start=1, end=2, klass="mux", patch="bug.patch")
    p = tmp_path / "gold.yaml"
    g.save(p)
    assert Gold.load(p) == g
