from stead.fail import Stead, parse_fail_line, parse_log

LINE = (
    "FAIL  test=I-XOR-01  signal=TOP.dut.rvfi_mem_wdata  time=108  "
    "expected=0xfffff800  actual=0xfffff810  dump=/x/fail.fst"
)


def test_parse_fail_line_all_fields():
    s = parse_fail_line(LINE)
    assert s == Stead(
        test="I-XOR-01",
        signal="TOP.dut.rvfi_mem_wdata",
        time=108,
        expected=0xFFFFF800,
        actual=0xFFFFF810,
        dump="/x/fail.fst",
    )


def test_parse_fail_line_rejects_non_fail_lines():
    assert parse_fail_line("NOTE  test=x  never stored") is None
    assert parse_fail_line("PASS  test=x") is None


def test_parse_fail_line_rejects_partial_stead():
    # all four or none: a FAIL line missing a field is not a STEAD record
    assert parse_fail_line("FAIL  test=x  signal=a.b  time=3  expected=0x1") is None


def test_parse_log_returns_first_fail_line(tmp_path):
    log = tmp_path / "sim.log"
    log.write_text("hello\n" + LINE + "\n" + LINE.replace("time=108", "time=999") + "\n")
    s = parse_log(log)
    assert s is not None and s.time == 108


def test_parse_log_without_fail_line_is_none(tmp_path):
    log = tmp_path / "sim.log"
    log.write_text("all good\n")
    assert parse_log(log) is None
