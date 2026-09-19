/*
 * Decimal Code Lab - Tiny Tapeout
 * SPDX-License-Identifier: Apache-2.0
 *
 * Converts decimal digits to/from eight (8) 4-bit codes:
 *   0 8421 (BCD)   1 2421   2 5421   3 84-2-1   4 7421
 *   5 Excess-3     6 Gray (reflected)   7 Cyclic decimal Gray (Gray of n+3)
 *
 * ---------------------------------------------------------------------
 * INPUTS
 *   ui_in[3:0]   D      data nibble (digit / code / binary nibble / digit index)
 *   ui_in[6:4]   M      code select (0..7 as listed above)
 *   ui_in[7]     VIEW   0: uo_out = {multi, aux, nibble}   1: uo_out = 7-segment
 *   uio_in[2:0]  F      function (table below)
 *   uio_in[4:3]  SPD    step rate for counter / museum / scan
 *                       0: every clk   1: clk/256   2: clk/32768   3: clk/2^23
 *   uio_in[5]    NINES  use the 9's complement of the digit
 *                       (counter and museum then count DOWN)
 *
 * FUNCTIONS (F)
 *   0 ENC   nibble = code_M(D)          D > 9 -> invalid
 *   1 DEC   nibble = decimal digit of code D (in code M), illegal code -> invalid
 *   2 CNT   decade counter 0..9 shown in code M
 *   3 MUS   "code museum": walks digits 0..9 in every code, 0..7, forever
 *   4 LDL   binary low  nibble <= D (level-sensitive, every clk)  } dabble family:
 *   5 LDH   binary high nibble <= D (level-sensitive, every clk)  } the 3 BCD digits
 *   6 SCAN  hold binary value, scan units/tens/hundreds at rate SPD} of {hi,lo} are
 *   7 SEL   hold binary value, show digit number D[1:0] (3 = error)} shown in code M
 *
 * OUTPUTS
 *   VIEW=0  uo_out[3:0] nibble (encoded value, or decimal digit for DEC)
 *           uo_out[6:4] aux    (MUS: code number shown, dabble: digit index 0/1/2)
 *           uo_out[7]   multi  (last change of nibble flipped more than 1 bit;
 *                               updates one to two clocks after the change)
 *   VIEW=1  uo_out[6:0] 7-segment a..g of the decimal digit ("E" if invalid)
 *           uo_out[7]   decimal point = invalid
 *   uio_out[7]  invalid   uio_out[6]  selfcomp (selected code is self-complementing)
 *   uio_out[5:0] unused (inputs)
 *
 * Everything from ui_in/uio_in to the outputs is combinational, apart from the
 * counter, museum, scan and binary registers and the multi-bit-flip detector.
 */

`default_nettype none

module tt_um_decimal_code_lab (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

    // ------------------------------------------------------------------
    // Pin decode
    // ------------------------------------------------------------------
    wire [3:0] D     = ui_in[3:0];
    wire [2:0] M     = ui_in[6:4];
    wire       VIEW  = ui_in[7];
    wire [2:0] F     = uio_in[2:0];
    wire [1:0] SPD   = uio_in[4:3];
    wire       NINES = uio_in[5];

    localparam [2:0] F_ENC = 3'd0, F_DEC = 3'd1, F_CNT = 3'd2, F_MUS  = 3'd3,
                     F_LDL = 3'd4, F_LDH = 3'd5, F_SCAN = 3'd6, F_SEL = 3'd7;

    // ------------------------------------------------------------------
    // Code tables
    // ------------------------------------------------------------------
    function [3:0] enc(input [2:0] m, input [3:0] d);
        reg [3:0] e3;
        begin
            e3 = d + 4'd3;
            case (m)
                3'd0: enc = d;                                   // 8421 (BCD)
                3'd1: enc = (d < 4'd5) ? d : d + 4'd6;           // 2421: 5..9 -> 1011..1111
                3'd2: enc = (d < 4'd5) ? d : d + 4'd3;           // 5421: 5..9 -> 1000..1100
                3'd3: case (d)                                   // 84-2-1
                          4'd0:    enc = 4'b0000;
                          4'd1:    enc = 4'b0111;
                          4'd2:    enc = 4'b0110;
                          4'd3:    enc = 4'b0101;
                          4'd4:    enc = 4'b0100;
                          4'd5:    enc = 4'b1011;
                          4'd6:    enc = 4'b1010;
                          4'd7:    enc = 4'b1001;
                          4'd8:    enc = 4'b1000;
                          default: enc = 4'b1111;                // 9
                      endcase
                3'd4: enc = (d < 4'd7) ? d : d + 4'd1;           // 7421: 7..9 -> 1000..1010
                3'd5: enc = e3;                                  // Excess-3
                3'd6: enc = d ^ (d >> 1);                        // reflected Gray
                default: enc = e3 ^ (e3 >> 1);                   // cyclic decimal Gray
            endcase
        end
    endfunction

    // Reverse lookup: {valid, digit}. Codes that are not one of the ten
    // canonical patterns of code m come back as valid = 0.
    function [4:0] dec(input [2:0] m, input [3:0] c);
        integer i;
        reg [3:0] di;
        begin
            dec = 5'd0;
            for (i = 0; i < 10; i = i + 1) begin
                di = i[3:0];
                if (enc(m, di) == c) dec = {1'b1, di};
            end
        end
    endfunction

    // 8-bit binary -> 3 BCD digits, "shift and add 3" fully unrolled.
    // The hundreds digit never exceeds 2, so it needs no add-3 stage.
    function [11:0] bin2bcd(input [7:0] b);
        integer i;
        reg [19:0] s;                                            // {hund, tens, units, bin}
        begin
            s = {12'd0, b};
            for (i = 0; i < 8; i = i + 1) begin
                if (s[11:8]  >= 4'd5) s[11:8]  = s[11:8]  + 4'd3;
                if (s[15:12] >= 4'd5) s[15:12] = s[15:12] + 4'd3;
                s = s << 1;
            end
            bin2bcd = s[19:8];
        end
    endfunction

    // 7-segment, active high, bit order {g,f,e,d,c,b,a}; anything > 9 shows "E"
    function [6:0] seg7(input [3:0] n);
        case (n)
            4'd0:    seg7 = 7'b0111111;
            4'd1:    seg7 = 7'b0000110;
            4'd2:    seg7 = 7'b1011011;
            4'd3:    seg7 = 7'b1001111;
            4'd4:    seg7 = 7'b1100110;
            4'd5:    seg7 = 7'b1101101;
            4'd6:    seg7 = 7'b1111101;
            4'd7:    seg7 = 7'b0000111;
            4'd8:    seg7 = 7'b1111111;
            4'd9:    seg7 = 7'b1101111;
            default: seg7 = 7'b1111001;
        endcase
    endfunction

    // ------------------------------------------------------------------
    // Step-rate prescaler shared by counter, museum and digit scan
    // ------------------------------------------------------------------
    reg [22:0] pre;
    always @(posedge clk) begin
        if (!rst_n) pre <= 23'd0;
        else        pre <= pre + 23'd1;
    end

    reg tick;
    always @(*) begin
        case (SPD)
            2'd0:    tick = 1'b1;
            2'd1:    tick = &pre[7:0];
            2'd2:    tick = &pre[14:0];
            default: tick = &pre[22:0];
        endcase
    end

    // ------------------------------------------------------------------
    // State: decade counter, museum, binary value and digit scanner
    // ------------------------------------------------------------------
    reg [3:0] cnt;       // decade counter 0..9
    reg [3:0] mus_d;     // museum digit 0..9
    reg [2:0] mus_m;     // museum code 0..7
    reg [1:0] idx;       // scanned digit: 0 units, 1 tens, 2 hundreds
    reg [3:0] bin_lo;
    reg [3:0] bin_hi;

    always @(posedge clk) begin
        if (!rst_n) begin
            cnt    <= 4'd0;
            mus_d  <= 4'd0;
            mus_m  <= 3'd0;
            idx    <= 2'd0;
            bin_lo <= 4'd0;
            bin_hi <= 4'd0;
        end else begin
            if (F == F_CNT && tick)
                cnt <= (cnt == 4'd9) ? 4'd0 : cnt + 4'd1;

            if (F == F_MUS && tick) begin
                if (mus_d == 4'd9) begin
                    mus_d <= 4'd0;
                    mus_m <= mus_m + 3'd1;
                end else begin
                    mus_d <= mus_d + 4'd1;
                end
            end

            if (F == F_LDL) bin_lo <= D;
            if (F == F_LDH) bin_hi <= D;

            if ((F == F_LDL || F == F_LDH || F == F_SCAN) && tick)
                idx <= (idx == 2'd2) ? 2'd0 : idx + 2'd1;
        end
    end

    // ------------------------------------------------------------------
    // Binary -> BCD digit selection
    // ------------------------------------------------------------------
    wire [11:0] bcd     = bin2bcd({bin_hi, bin_lo});
    wire [1:0]  idx_eff = (F == F_SEL) ? D[1:0] : idx;

    reg [3:0] scan_d;
    always @(*) begin
        case (idx_eff)
            2'd0:    scan_d = bcd[3:0];
            2'd1:    scan_d = bcd[7:4];
            2'd2:    scan_d = bcd[11:8];
            default: scan_d = 4'hF;              // no such digit -> invalid
        endcase
    end

    // ------------------------------------------------------------------
    // Datapath: pick the source digit, apply 9's complement, encode
    // ------------------------------------------------------------------
    wire [4:0] dec_r = dec(M, D);

    reg [3:0] dig_raw;                           // decimal digit before 9's complement
    reg [2:0] mode;                              // code actually used
    always @(*) begin
        mode = M;
        case (F)
            F_ENC:   dig_raw = D;
            F_DEC:   dig_raw = dec_r[3:0];
            F_CNT:   dig_raw = cnt;
            F_MUS:   begin dig_raw = mus_d; mode = mus_m; end
            default: dig_raw = scan_d;
        endcase
    end

    wire       valid  = (F == F_DEC) ? dec_r[4] : (dig_raw <= 4'd9);
    wire [3:0] dig    = valid ? (NINES ? 4'd9 - dig_raw : dig_raw) : 4'd0;
    wire [3:0] cod    = enc(mode, dig);
    wire [3:0] nibble = valid ? ((F == F_DEC) ? dig : cod) : 4'd0;

    // Self-complementing codes: 2421, 84-2-1, Excess-3 (~code(d) == code(9-d))
    wire selfcomp = (mode == 3'd1) | (mode == 3'd3) | (mode == 3'd5);

    wire [2:0] aux = (F == F_MUS)  ? mus_m :
                     (F >= F_LDL)  ? {1'b0, idx_eff} : 3'd0;

    // ------------------------------------------------------------------
    // Multi-bit flip detector (plain Gray vs cyclic Gray at the 9 -> 0 wrap)
    // ------------------------------------------------------------------
    reg  [3:0] prev;
    reg        multi;
    wire [3:0] diff = nibble ^ prev;
    always @(posedge clk) begin
        if (!rst_n) begin
            prev  <= 4'd0;
            multi <= 1'b0;
        end else if (diff != 4'd0) begin
            prev  <= nibble;
            multi <= ((diff & (diff - 4'd1)) != 4'd0);   // more than one bit set
        end
    end

    // ------------------------------------------------------------------
    // Outputs
    // ------------------------------------------------------------------
    wire [6:0] seg = seg7(valid ? dig : 4'hF);

    assign uo_out  = VIEW ? {~valid, seg} : {multi, aux, nibble};
    assign uio_out = {~valid, selfcomp, 6'b000000};
    assign uio_oe  = 8'b1100_0000;

    wire _unused = &{ena, uio_in[7:6], 1'b0};

endmodule
