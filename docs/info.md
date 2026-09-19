<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

Decimal Code Lab converts a decimal digit (0-9) to and from eight different 4-bit codes, and wraps that converter in a few extra modes that make the codes easy to explore.

## How to test

Reset the design (pulse rst_n low) before starting. The examples below assume the code view (VIEW=0) unless stated. uio[5:0] is written as NINES SPD F in binary.

Encode. Set F=000. Choose a code with M and a digit with D.

M=001 (2421), D=0111 (7): output 1101.
M=111 (cyclic Gray), D=0110 (6): output 1101.
D=1010 (10) in any code: output 0000 and invalid (uio[7]) goes high.

Decode. Set F=001 and put a code on D.

M=010 (5421), D=1100: output 1001 (digit 9).
M=010 (5421), D=0101: invalid, because 0101 is not a 5421 code.

9's complement. Set NINES=1 in encode mode. In Excess-3 (M=101), digit 3 gives 0110, and with NINES=1 it gives 1001, the bitwise inverse. The selfcomp output stays high. Try the same in BCD (M=000): the outputs are not inverses and selfcomp is low.

Decade counter. Set F=010. With a 10 MHz clock use SPD=11 for about one step per second; with a slow or manually pulsed clock use SPD=00 to step on every clock edge. Set M=110 and watch uo[3:0] (or a logic analyser): three bits change together at the 9 to 0 wrap and multi (uo[7]) pulses. Change to M=111 and every step, including the wrap, flips exactly one bit. Set NINES=1 to count down.

Code museum. Set F=011 and a slow SPD. The nibble walks digits 0 to 9 in BCD, then in 2421, and so on through all eight codes. uo[6:4] shows which code is on display.

Binary to BCD. To convert 173 (1010 1101):

Put D=1101 with F=100 for at least one clock (low nibble).
Put D=1010 with F=101 for at least one clock (high nibble).
Set F=111 and use D=0000, 0001, 0010 to see the units (3), tens (7) and hundreds (1) digits in the selected code. Alternatively set F=110 to scan through them automatically at the SPD rate; uo[5:4] shows which digit is on display.

When changing F with hand-operated switches, change one bit at a time where you can (4 to 5 to 7 above is a good route). Switches that flip two bits at once can pass through an intermediate function for a moment, and a load function that is momentarily selected will write whatever is on D at that clock.

7-segment view. Set VIEW (ui[7]) high. uo[6:0] then drives segments a to g with the decimal digit, and uo[7] is the decimal point, lit when the result is invalid ("E" is shown). selfcomp and invalid stay on uio[6] and uio[7].

Simulation. The test folder contains a cocotb testbench that checks every code, decode, 9's complement, the counter, museum, step-rate dividers and all 256 binary values. Run it with make in the test directory.

## External hardware

TBA
