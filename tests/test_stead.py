"""A STEAD record is all four fields or nothing, and it must agree with the dump."""

from pathlib import Path

from stead.fail import Stead, parse_fail_line, parse_log
from stead.validate import validate_stead

VCD = Path(__file__).parent / "fixtures" / "mini.vcd"
LINE = (
    "FAIL  test=I-XOR-01  signal=TOP.dut.rvfi_mem_wdata  time=100  "
    "expected=0xfffff800  actual=0xfffff810  dump=/x.fst"
)


def rec(**kw):
    d = dict(
        test="t",
        signal="TOP.dut.rvfi_mem_wdata",
        time=100,
        expected=0xFFFFF800,
        actual=0xFFFFF810,
        dump=str(VCD),
    )
    return Stead(**{**d, **kw})


def test_fail_line_parses_all_four_or_not_at_all():
    assert parse_fail_line(LINE) == rec(test="I-XOR-01", dump="/x.fst")
    assert parse_fail_line("FAIL  test=x  signal=a.b  time=3  expected=0x1") is None
    assert parse_fail_line("NOTE  test=x  never stored") is None


def test_first_fail_line_in_log_wins(tmp_path):
    log = tmp_path / "sim.log"
    log.write_text("hello\n" + LINE + "\n" + LINE.replace("time=100", "time=999") + "\n")
    assert parse_log(log).time == 100


def test_record_is_kept_only_when_dump_shows_actual_at_time():
    assert validate_stead(rec(), VCD) == (True, "ok")
    assert "dump@t" in validate_stead(rec(actual=0x1234), VCD)[1]
    assert "expected == actual" in validate_stead(rec(expected=0xFFFFF810), VCD)[1]
    assert "not in dump" in validate_stead(rec(signal="TOP.dut.nope"), VCD)[1]
    assert "beyond" in validate_stead(rec(time=10**9, actual=0x55), VCD)[1]


def test_value_at_holds_last_change_and_scalars_work():
    from stead.wave import open_dump, value_at

    w = open_dump(VCD)
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 99) == 0
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 104) == 0xFFFFF810
    assert value_at(w, "TOP.dut.rvfi_mem_wdata", 108) == 0xFFFFF800
    assert value_at(w, "TOP.dut.valid", 150) == 1
