#!/usr/bin/env python3
"""python tools/wave.py <dump> <signal> [<time>]: the signal's value at that time, or every change of it.
Signals are full hierarchical names as in the STEAD line; an unknown name lists the closest candidates."""

import sys

import pywellen

if len(sys.argv) not in (3, 4):
    sys.exit("usage: wave.py <dump> <signal> [<time>]")
dump, name = sys.argv[1], sys.argv[2]
w = pywellen.Waveform(dump)
names = [v.full_name for v in w.all_vars()]
if name not in names:
    leaf = name.split(".")[-1]
    hits = [n for n in names if leaf in n][:40]
    sys.exit(f"no signal {name}" + ("; candidates:\n  " + "\n  ".join(hits) if hits else ""))
var = w[name]
if len(sys.argv) == 4:
    t = int(sys.argv[3])
    v = var.signal.value_at(t)
    print(f"{name} @ {t} = {v}" + (f" (0x{v:x})" if isinstance(v, int) else ""))
else:
    for t, v in var.tv:
        print(f"{t}\t{v}" + (f"\t0x{v:x}" if isinstance(v, int) else ""))
