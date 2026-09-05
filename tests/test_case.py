from stead.case import Case
from stead.fail import Stead


def test_case_yaml_roundtrip_with_stead(tmp_path):
    c = Case(
        id="ibex-0001",
        repo="ibex",
        url="https://github.com/lowRISC/ibex",
        commit="abc",
        kind="injected",
        test="I-XOR-01",
        recipe="ibex",
        dump="waves/fail.fst",
        validated_on="verilator-5.050",
        dut_paths=["rtl/**"],
        checker_paths=["dv/**", "vendor/**"],
        stead=Stead("I-XOR-01", "TOP.a.b", 108, 0xFFFFF800, 0xFFFFF810, "waves/fail.fst"),
    )
    p = tmp_path / "case.yaml"
    c.save(p)
    assert Case.load(p) == c
    assert "expected: '0xfffff800'" in p.read_text()


def test_case_yaml_roundtrip_without_stead(tmp_path):
    c = Case(
        id="x",
        repo="r",
        url="u",
        commit="c",
        kind="hwe",
        test="t",
        recipe="r",
        dump=None,
        validated_on="v",
        dut_paths=["rtl/**"],
        checker_paths=[],
        stead=None,
    )
    p = tmp_path / "case.yaml"
    c.save(p)
    assert Case.load(p) == c


def test_is_dut_path_uses_globs():
    c = Case(
        id="x",
        repo="r",
        url="u",
        commit="c",
        kind="hwe",
        test="t",
        recipe="r",
        dump=None,
        validated_on="v",
        dut_paths=["rtl/**"],
        checker_paths=["dv/**"],
        stead=None,
    )
    assert c.is_dut_path("rtl/ibex_alu.sv")
    assert c.is_dut_path("rtl/sub/x.sv")
    assert not c.is_dut_path("dv/tb.sv")
    assert not c.is_dut_path("Makefile")
