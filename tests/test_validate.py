from pathlib import Path

from stead.fail import Stead
from stead.validate import validate_stead

VCD = Path(__file__).parent / "fixtures" / "mini.vcd"


def mk(**kw):
    d = dict(
        test="t",
        signal="TOP.dut.rvfi_mem_wdata",
        time=100,
        expected=0xFFFFF800,
        actual=0xFFFFF810,
        dump=str(VCD),
    )
    d.update(kw)
    return Stead(**d)


def test_valid_record_passes():
    ok, reason = validate_stead(mk(), VCD)
    assert ok, reason


def test_actual_must_match_dump_at_time():
    ok, reason = validate_stead(mk(actual=0x1234), VCD)
    assert not ok and "dump@t" in reason


def test_expected_must_differ_from_actual():
    ok, reason = validate_stead(mk(expected=0xFFFFF810), VCD)
    assert not ok and "expected == actual" in reason


def test_unknown_signal_fails():
    ok, reason = validate_stead(mk(signal="TOP.dut.nope"), VCD)
    assert not ok and "not in dump" in reason


def test_time_past_end_of_dump_fails():
    ok, reason = validate_stead(mk(time=10**9, actual=0x55), VCD)
    assert not ok and "beyond" in reason
