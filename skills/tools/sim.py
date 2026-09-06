#!/usr/bin/env python3
"""python tools/sim.py <test> [--dump]: rebuild your edited tree and run one test in the core's simulator.
Prints PASS, FAIL, BUILD_ERROR or CRASH and the log; --dump also writes waves/sim.fst for pywellen."""

import sys

from stead.agents.sim import main

sys.exit(main())
