from pathlib import Path

import pytest

from stead.wave import end_time, open_dump, value_at

VCD = Path(__file__).parent / "fixtures" / "mini.vcd"


def test_value_at_holds_last_change():
    w = open_dump(VCD)
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 99) == 0
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 100) == 0xFFFFF810
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 104) == 0xFFFFF810
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 108) == 0xFFFFF800


def test_value_at_scalar():
    w = open_dump(VCD)
    assert value_at(w, "TOP.dut.valid", 150) == 1


def test_missing_signal_raises():
    with pytest.raises(KeyError):
        value_at(open_dump(VCD), "TOP.dut.nope", 0)


def test_end_time_is_last_time_step():
    assert end_time(open_dump(VCD)) == 200
