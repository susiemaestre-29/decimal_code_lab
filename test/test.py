# SPDX-License-Identifier: Apache-2.0
"""cocotb tests for tt_um_decimal_code_lab.

The reference tables below are written out literally (and cross-checked by
weights / Gray rules in test_reference_tables) so they are independent of the
arithmetic shortcuts used inside the RTL.
"""

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

# ---- function codes (uio_in[2:0]) -------------------------------------
ENC, DEC, CNT, MUS, LDL, LDH, SCAN, SEL = range(8)

# ---- reference data -----------------------------------------------------
NAMES = ["8421", "2421", "5421", "84-2-1", "7421", "Excess-3", "Gray", "Cyclic Gray"]

CODES = {
    0: [0b0000, 0b0001, 0b0010, 0b0011, 0b0100, 0b0101, 0b0110, 0b0111, 0b1000, 0b1001],
    1: [0b0000, 0b0001, 0b0010, 0b0011, 0b0100, 0b1011, 0b1100, 0b1101, 0b1110, 0b1111],
    2: [0b0000, 0b0001, 0b0010, 0b0011, 0b0100, 0b1000, 0b1001, 0b1010, 0b1011, 0b1100],
    3: [0b0000, 0b0111, 0b0110, 0b0101, 0b0100, 0b1011, 0b1010, 0b1001, 0b1000, 0b1111],
    4: [0b0000, 0b0001, 0b0010, 0b0011, 0b0100, 0b0101, 0b0110, 0b1000, 0b1001, 0b1010],
    5: [0b0011, 0b0100, 0b0101, 0b0110, 0b0111, 0b1000, 0b1001, 0b1010, 0b1011, 0b1100],
    6: [0b0000, 0b0001, 0b0011, 0b0010, 0b0110, 0b0111, 0b0101, 0b0100, 0b1100, 0b1101],
    7: [0b0010, 0b0110, 0b0111, 0b0101, 0b0100, 0b1100, 0b1101, 0b1111, 0b1110, 0b1010],
}
WEIGHTS = {0: (8, 4, 2, 1), 1: (2, 4, 2, 1), 2: (5, 4, 2, 1), 3: (8, 4, -2, -1), 4: (7, 4, 2, 1)}
SELF_COMP = {1, 3, 5}

SEG = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F]   # a=bit0 ... g=bit6
SEG_ERR = 0x79                                                       # "E"


def popcount(x):
    return bin(x).count("1")


def expect_manual(f, m, d, nines):
    """Expected result for the combinational functions ENC and DEC."""
    if f == ENC:
        valid, dig = d <= 9, d
    else:
        valid = d in CODES[m]
        dig = CODES[m].index(d) if valid else 0
    if not valid:
        return {"valid": False, "dig": 0, "nib": 0}
    if nines:
        dig = 9 - dig
    nib = dig if f == DEC else CODES[m][dig]
    return {"valid": True, "dig": dig, "nib": nib}


# ---- pin helpers ----------------------------------------------------------
def drive(dut, d=0, m=0, view=0, f=0, spd=0, nines=0):
    dut.ui_in.value = (view << 7) | (m << 4) | (d & 0xF)
    dut.uio_in.value = (nines << 5) | (spd << 3) | f


def snap(dut):
    uo = int(dut.uo_out.value)
    uio = int(dut.uio_out.value)
    return {
        "uo": uo,
        "nib": uo & 0xF,
        "aux": (uo >> 4) & 7,
        "multi": uo >> 7,
        "seg": uo & 0x7F,
        "dp": uo >> 7,
        "invalid": uio >> 7,
        "selfcomp": (uio >> 6) & 1,
    }


async def boot(dut):
    """Start the clock and apply reset. Sampling always happens on falling edges."""
    try:
        clk = Clock(dut.clk, 10, unit="us")
    except TypeError:                       # cocotb 1.x spells it "units"
        clk = Clock(dut.clk, 10, units="us")
    cocotb.start_soon(clk.start())
    dut.ena.value = 1
    drive(dut)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


async def reset(dut):
    """Re-apply reset; returns the sample taken while reset is asserted."""
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    await FallingEdge(dut.clk)
    s = snap(dut)
    dut.rst_n.value = 1
    return s


async def step(dut, n=1):
    for _ in range(n):
        await FallingEdge(dut.clk)


async def collect(dut, n):
    out = []
    for _ in range(n):
        await FallingEdge(dut.clk)
        out.append(snap(dut))
    return out


async def wait_change(dut, timeout):
    """Advance until the nibble changes; return (old_nib, new_nib)."""
    old = snap(dut)["nib"]
    for _ in range(timeout):
        await FallingEdge(dut.clk)
        new = snap(dut)["nib"]
        if new != old:
            return old, new
    raise AssertionError(f"nibble did not change within {timeout} clocks")


def check_multi_free_running(seq):
    """Cycle-exact model of the flag when the state itself changes on every clock.

    The detector compares the nibble with the value it saw one clock earlier, so
    the flag trails the nibble by one extra clock.
    """
    for i in range(2, len(seq)):
        a, b = seq[i - 1]["nib"], seq[i - 2]["nib"]
        exp = (popcount(a ^ b) > 1) if a != b else seq[i - 1]["multi"]
        assert seq[i]["multi"] == int(exp), (
            f"multi mismatch at sample {i}: nib history {b:04b}->{a:04b}, "
            f"got {seq[i]['multi']}, expected {int(exp)}"
        )

