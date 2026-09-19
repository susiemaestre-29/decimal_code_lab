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


# =============================================================================
# 0. Sanity of the reference tables themselves (pure Python)
# =============================================================================
@cocotb.test()
async def test_reference_tables(dut):
    for m, w in WEIGHTS.items():
        for d, c in enumerate(CODES[m]):
            val = sum(wt * ((c >> (3 - i)) & 1) for i, wt in enumerate(w))
            assert val == d, f"{NAMES[m]}: code {c:04b} weighs {val}, expected {d}"
    for m in CODES:
        assert len(set(CODES[m])) == 10, f"{NAMES[m]} has duplicate codes"
        selfc = all(CODES[m][9 - d] == CODES[m][d] ^ 0xF for d in range(10))
        assert selfc == (m in SELF_COMP), f"{NAMES[m]} self-complement property mismatch"
    for d in range(10):
        assert CODES[5][d] == d + 3
        assert CODES[6][d] == d ^ (d >> 1)
        assert CODES[7][d] == (d + 3) ^ ((d + 3) >> 1)
    dist = [popcount(CODES[6][d] ^ CODES[6][(d + 1) % 10]) for d in range(10)]
    assert dist == [1] * 9 + [3], "reflected Gray must flip 3 bits at the 9->0 wrap"
    dist = [popcount(CODES[7][d] ^ CODES[7][(d + 1) % 10]) for d in range(10)]
    assert dist == [1] * 10, "cyclic Gray must be unit-distance including the wrap"


# =============================================================================
# 1. Pins and reset
# =============================================================================
@cocotb.test()
async def test_pin_directions(dut):
    await boot(dut)
    await step(dut, 2)
    assert int(dut.uio_oe.value) == 0xC0
    assert (int(dut.uio_out.value) & 0x3F) == 0


@cocotb.test()
async def test_reset_state(dut):
    await boot(dut)
    for f, code in ((CNT, 5), (MUS, 0)):          # museum always restarts in 8421
        drive(dut, m=5, f=f, spd=1)
        s = await reset(dut)
        assert s["nib"] == CODES[code][0], "reset must show digit 0"
        assert s["multi"] == 0
        assert s["aux"] == 0


# =============================================================================
# 2. Combinational encode / decode
# =============================================================================
@cocotb.test()
async def test_encode_exhaustive(dut):
    await boot(dut)
    for nines in (0, 1):
        for m in range(8):
            for d in range(16):
                drive(dut, d=d, m=m, f=ENC, nines=nines)
                await step(dut)
                s = snap(dut)
                e = expect_manual(ENC, m, d, nines)
                tag = f"ENC {NAMES[m]} d={d} nines={nines}"
                assert s["nib"] == e["nib"], f"{tag}: got {s['nib']:04b}, expected {e['nib']:04b}"
                assert s["invalid"] == int(not e["valid"]), tag
                assert s["selfcomp"] == int(m in SELF_COMP), tag
                assert s["aux"] == 0, tag


@cocotb.test()
async def test_decode_exhaustive(dut):
    await boot(dut)
    for nines in (0, 1):
        for m in range(8):
            for c in range(16):
                drive(dut, d=c, m=m, f=DEC, nines=nines)
                await step(dut)
                s = snap(dut)
                e = expect_manual(DEC, m, c, nines)
                tag = f"DEC {NAMES[m]} code={c:04b} nines={nines}"
                assert s["nib"] == e["nib"], f"{tag}: got {s['nib']}, expected {e['nib']}"
                assert s["invalid"] == int(not e["valid"]), tag
                assert s["selfcomp"] == int(m in SELF_COMP), tag


@cocotb.test()
async def test_round_trip(dut):
    await boot(dut)
    for m in range(8):
        for d in range(10):
            drive(dut, d=d, m=m, f=ENC)
            await step(dut)
            code = snap(dut)["nib"]
            drive(dut, d=code, m=m, f=DEC)
            await step(dut)
            s = snap(dut)
            assert s["nib"] == d and not s["invalid"], f"{NAMES[m]}: {d} -> {code:04b} -> {s['nib']}"


@cocotb.test()
async def test_nines_complement_property(dut):
    """For self-complementing codes, the 9's-complement output is the bitwise NOT."""
    await boot(dut)
    for m in range(8):
        for d in range(10):
            drive(dut, d=d, m=m, f=ENC, nines=0)
            await step(dut)
            plain = snap(dut)["nib"]
            drive(dut, d=d, m=m, f=ENC, nines=1)
            await step(dut)
            s = snap(dut)
            assert s["nib"] == CODES[m][9 - d]
            if m in SELF_COMP:
                assert s["nib"] == plain ^ 0xF, f"{NAMES[m]} d={d}"
                assert s["selfcomp"] == 1
    # and the flag is honest: non-self-complementing codes break the NOT rule somewhere
    for m in set(range(8)) - SELF_COMP:
        assert any(CODES[m][9 - d] != CODES[m][d] ^ 0xF for d in range(10))


# =============================================================================
# 3. 7-segment view
# =============================================================================
@cocotb.test()
async def test_segment_view(dut):
    await boot(dut)
    for f in (ENC, DEC):
        for nines in (0, 1):
            for m in (0, 3, 6, 7):
                for d in range(16):
                    drive(dut, d=d, m=m, view=1, f=f, nines=nines)
                    await step(dut)
                    s = snap(dut)
                    e = expect_manual(f, m, d, nines)
                    want = SEG[e["dig"]] if e["valid"] else SEG_ERR
                    tag = f"SEG f={f} {NAMES[m]} d={d} nines={nines}"
                    assert s["seg"] == want, f"{tag}: got {s['seg']:07b}, expected {want:07b}"
                    assert s["dp"] == int(not e["valid"]), tag
                    assert s["invalid"] == int(not e["valid"]), tag


# =============================================================================
# 4. Decade counter in every code
# =============================================================================
@cocotb.test()
async def test_decade_counter_all_codes(dut):
    await boot(dut)
    for nines in (0, 1):
        for m in range(8):
            drive(dut, m=m, f=CNT, spd=0, nines=nines)
            q0 = await reset(dut)
            assert q0["nib"] == CODES[m][9 if nines else 0]
            samples = await collect(dut, 35)
            for k, s in enumerate(samples, start=1):       # sample k = state after k steps
                dig = (9 - k % 10) if nines else (k % 10)
                assert s["nib"] == CODES[m][dig], (
                    f"{NAMES[m]} nines={nines} step {k}: got {s['nib']:04b}, expected {CODES[m][dig]:04b}"
                )
                assert s["invalid"] == 0
            check_multi_free_running([q0] + samples)


@cocotb.test()
async def test_gray_wrap_flag_slow(dut):
    """At a readable step rate, 'multi' fires exactly where the code flips >1 bit."""
    await boot(dut)
    events = {}
    for m in (0, 6, 7):
        drive(dut, m=m, f=CNT, spd=1)          # one step per 256 clocks
        await reset(dut)
        flagged = []
        for k in range(1, 13):
            old, new = await wait_change(dut, 300)
            await step(dut, 3)
            s = snap(dut)
            assert s["nib"] == new
            want = popcount(old ^ new) > 1
            assert s["multi"] == int(want), f"{NAMES[m]} step {k}: {old:04b}->{new:04b}"
            if want:
                flagged.append(k)
        events[m] = flagged
    assert events[6] == [10], f"reflected Gray should flag only the 9->0 wrap (step 10), got {events[6]}"
    assert events[7] == [], "cyclic Gray must never flag"
    assert len(events[0]) > 5, "plain BCD flips several bits on many steps"


@cocotb.test()
async def test_multi_flag_manual(dut):
    """Flag follows the last change and stays put while the code is stable."""
    await boot(dut)
    plan = [(0, 0), (1, 0), (2, 1), (3, 0), (4, 1), (8, 1), (9, 0)]   # (digit, expected multi), BCD
    for d, want in plan:
        drive(dut, d=d, m=0, f=ENC)
        await step(dut, 4)
        s = snap(dut)
        assert s["nib"] == d
        assert s["multi"] == want, f"BCD digit {d}: multi={s['multi']}, expected {want}"
        await step(dut, 4)
        assert snap(dut)["multi"] == want, "flag must hold while the nibble is stable"


# =============================================================================
# 5. Step-rate prescaler
# =============================================================================
@cocotb.test()
async def test_speed_dividers(dut):
    await boot(dut)
    for spd, period in ((0, 1), (1, 256), (2, 32768)):
        drive(dut, m=0, f=CNT, spd=spd)
        await reset(dut)
        await step(dut)
        start = snap(dut)["nib"]
        n = 3 * period
        await ClockCycles(dut.clk, n)
        await FallingEdge(dut.clk)
        end = snap(dut)["nib"]
        # any n = 3*period consecutive clocks contain exactly 3 ticks
        want = (start + n // period) % 10
        assert end == want, f"SPD={spd}: {start} -> {end}, expected {want}"


@cocotb.test()
async def test_speed_slowest_tap(dut):
    """SPD=3 divides by 2^23: check the tap by depositing into the prescaler (RTL only)."""
    await boot(dut)
    if os.environ.get("GATES") == "yes":
        dut._log.warning("gate-level run: skipping prescaler deposit test")
        return
    try:
        pre = dut.user_project.pre
    except AttributeError:
        dut._log.warning("no dut.user_project.pre - skipping slowest-tap test")
        return
    drive(dut, m=0, f=CNT, spd=3)
    await reset(dut)
    await step(dut)
    d0 = snap(dut)["nib"]
    pre.value = 0x3FFFF0                       # bit 22 clear: passes through 22 ones, must NOT tick
    await step(dut, 40)
    assert snap(dut)["nib"] == d0, "SPD=3 ticked on only 22 low ones - tap too short"
    pre.value = 0x7FFFF0                       # all 23 bits reach 1: exactly one tick
    await step(dut, 40)
    assert snap(dut)["nib"] == (d0 + 1) % 10, "SPD=3 should step once when all 23 bits are 1"


# =============================================================================
# 6. Code museum
# =============================================================================
@cocotb.test()
async def test_museum(dut):
    await boot(dut)
    for nines in (0, 1):
        drive(dut, f=MUS, spd=0, nines=nines)
        q0 = await reset(dut)
        samples = await collect(dut, 170)              # two full sweeps of all 8 codes + 10
        for k, s in enumerate(samples, start=1):
            digit, mode = k % 10, (k // 10) % 8
            dig = 9 - digit if nines else digit
            assert s["aux"] == mode, f"step {k}: aux={s['aux']} expected code {mode}"
            assert s["nib"] == CODES[mode][dig], f"step {k}: {NAMES[mode]} digit {dig}"
            assert s["selfcomp"] == int(mode in SELF_COMP), f"step {k}"
        check_multi_free_running([q0] + samples)


@cocotb.test()
async def test_state_retention(dut):
    """Counter keeps its value while another function is selected; reset clears it."""
    await boot(dut)
    drive(dut, m=0, f=CNT, spd=0)
    await reset(dut)
    await step(dut, 3)                                 # cnt = 3
    drive(dut, d=7, m=0, f=ENC, spd=0)
    await step(dut, 6)
    assert snap(dut)["nib"] == 7
    drive(dut, m=0, f=CNT, spd=0)
    await step(dut)
    assert snap(dut)["nib"] == 4, "counter should resume from 3 and step to 4"
    q = await reset(dut)
    assert q["nib"] == 0


# =============================================================================
# 7. Binary -> BCD (double dabble), shown in every code
# =============================================================================
def bcd_digits(v):
    return [v % 10, (v // 10) % 10, v // 100]


async def load_binary(dut, value, m, nines=0):
    drive(dut, d=value & 0xF, m=m, f=LDL, nines=nines)
    await step(dut)
    drive(dut, d=value >> 4, m=m, f=LDH, nines=nines)
    await step(dut)


@cocotb.test()
async def test_binary_to_bcd_exhaustive(dut):
    await boot(dut)
    # every binary value in every code; 9's complement is orthogonal, so sample a few codes
    for nines, modes in ((0, range(8)), (1, (0, 1, 7))):
        for m in modes:
            for v in range(256):
                await load_binary(dut, v, m, nines)
                digs = bcd_digits(v)
                for idx in range(4):
                    drive(dut, d=idx, m=m, f=SEL, nines=nines)
                    await step(dut)
                    s = snap(dut)
                    tag = f"bin={v} idx={idx} {NAMES[m]} nines={nines}"
                    assert s["aux"] == idx, tag
                    if idx < 3:
                        dig = 9 - digs[idx] if nines else digs[idx]
                        assert s["nib"] == CODES[m][dig], f"{tag}: got {s['nib']:04b}"
                        assert s["invalid"] == 0, tag
                    else:
                        assert s["invalid"] == 1 and s["nib"] == 0, f"{tag}: idx 3 must be invalid"


@cocotb.test()
async def test_dabble_segment_view(dut):
    await boot(dut)
    for v in (0, 9, 10, 99, 100, 173, 199, 200, 255):
        await load_binary(dut, v, m=0)
        for idx in range(3):
            drive(dut, d=idx, m=0, view=1, f=SEL)
            await step(dut)
            s = snap(dut)
            assert s["seg"] == SEG[bcd_digits(v)[idx]], f"bin={v} idx={idx}"
            assert s["dp"] == 0


@cocotb.test()
async def test_dabble_scan(dut):
    await boot(dut)
    m = 3
    await load_binary(dut, 173, m)                      # 1-7-3
    drive(dut, m=m, f=SCAN, spd=0)
    samples = await collect(dut, 15)
    digs = bcd_digits(173)
    for i, s in enumerate(samples):
        assert s["aux"] in (0, 1, 2)
        assert s["nib"] == CODES[m][digs[s["aux"]]], f"sample {i}"
        if i:
            assert s["aux"] == (samples[i - 1]["aux"] + 1) % 3, "scan must cycle 0,1,2,0,..."
    # switching to a manual function stops the scanner
    drive(dut, d=5, m=m, f=ENC)
    await step(dut, 4)
    assert snap(dut)["aux"] == 0

