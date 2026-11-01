// Self-checking testbench for teg_ctrl. The same bench runs on the RTL and on the
// synthesized gate-level netlist (kit cell models), so both are checked against one spec.
//
//   every array setting   mode 01, row 0..15 x col 0..7   (row 12..15 must select nothing)
//   every CBCM setting    mode 10, cbsel 0..15             (cbsel 10..15 must select nothing)
//   every RO setting      mode 11, rosel 0..7              (6, 7 must select nothing)
//   mode 00               nothing enabled, CBCM clock blocked
//   scan read-back        the word shifted out equals the word loaded before
//   divider               OUT period = 256 cycles of the selected RO, other ROs ignored
`timescale 1ns/10ps
module tb_teg_ctrl;
  reg sck = 1'b0, sdi = 1'b0, sle = 1'b0, cck = 1'b0;
  reg [5:0] ro_in = 6'b0;
  wire out, cbcm_clk;
  wire [11:0] row_sel, row_selb;
  wire [7:0]  col_sel, col_selb;
  wire [9:0]  cbcm_en;
  wire [5:0]  ro_en;

  teg_ctrl dut (.sck(sck), .sdi(sdi), .sle(sle), .cck(cck), .ro_in(ro_in), .out(out),
                .row_sel(row_sel), .row_selb(row_selb), .col_sel(col_sel), .col_selb(col_selb),
                .cbcm_en(cbcm_en), .ro_en(ro_en), .cbcm_clk(cbcm_clk));

  integer errors = 0, checks = 0;
  reg [19:0] readback;

  function [19:0] word(input [1:0] mode, input [3:0] row, input [2:0] col,
                       input [3:0] cbsel, input [2:0] rosel, input osel);
    word = {3'b000, osel, rosel, cbsel, col, row, mode};
  endfunction

  // 10 MHz scan clock; OUT is sampled before each rising edge (read-back of the old word)
  task load(input [19:0] w);
    integer b;
    begin
      for (b = 19; b >= 0; b = b - 1) begin
        sdi = w[b];
        #40 readback[b] = out;
        sck = 1'b1;
        #50 sck = 1'b0;
        #10;
      end
      #20 sle = 1'b1;
      #50 sle = 1'b0;
      #30;
    end
  endtask

  task expect_outputs(input [1:0] mode, input [3:0] row, input [2:0] col,
                      input [3:0] cbsel, input [2:0] rosel);
    reg [11:0] er; reg [7:0] ec; reg [9:0] eb; reg [5:0] eo;
    begin
      er = (mode == 2'b01 && row < 12)   ? (12'b1 << row)  : 12'b0;
      ec = (mode == 2'b01)               ? (8'b1 << col)   : 8'b0;
      eb = (mode == 2'b10 && cbsel < 10)  ? (10'b1 << cbsel) : 10'b0;
      eo = (mode == 2'b11 && rosel < 6)  ? (6'b1 << rosel) : 6'b0;
      cck = 1'b1; #5;
      checks = checks + 1;
      if (row_sel !== er || row_selb !== ~er || col_sel !== ec || col_selb !== ~ec ||
          cbcm_en !== eb || ro_en !== eo || cbcm_clk !== (mode == 2'b10)) begin
        errors = errors + 1;
        $display("FAIL mode=%b row=%0d col=%0d cbsel=%0d rosel=%0d: row=%b/%b col=%b/%b cbcm=%b ro=%b clk=%b",
                 mode, row, col, cbsel, rosel, row_sel, row_selb, col_sel, col_selb, cbcm_en, ro_en, cbcm_clk);
      end
      cck = 1'b0; #5;
      if (cbcm_clk !== 1'b0) begin
        errors = errors + 1;
        $display("FAIL cbcm_clk not low with cck low (mode=%b)", mode);
      end
    end
  endtask

  integer r, c, k, rises, last_rise, nper, bad_per, toggles;
  reg prev_out;
  reg [19:0] wa;

  initial begin
    // power-up state is unknown; the first load defines everything
    load(word(2'b00, 0, 0, 0, 0, 1'b0));
    expect_outputs(2'b00, 0, 0, 0, 0);

    for (r = 0; r < 16; r = r + 1)
      for (c = 0; c < 8; c = c + 1) begin
        load(word(2'b01, r, c, 0, 0, 1'b0));
        expect_outputs(2'b01, r, c, 0, 0);
      end
    for (k = 0; k < 16; k = k + 1) begin
      load(word(2'b10, 0, 0, k, 0, 1'b0));
      expect_outputs(2'b10, 0, 0, k, 0);
    end
    for (k = 0; k < 8; k = k + 1) begin
      load(word(2'b11, 0, 0, 0, k, 1'b0));
      expect_outputs(2'b11, 0, 0, 0, k);
    end
    load(word(2'b00, 0, 0, 0, 0, 1'b0));
    expect_outputs(2'b00, 0, 0, 0, 0);

    // scan read-back: loading B shifts out A
    wa = word(2'b01, 5, 3, 7, 2, 1'b0);
    load(wa);
    load(word(2'b11, 0, 0, 0, 2, 1'b0));
    checks = checks + 1;
    if (readback !== wa) begin
      errors = errors + 1;
      $display("FAIL read-back %b expected %b", readback, wa);
    end

    // divider: RO 4 selected, OUT = RO/256; 20 ns input period
    load(word(2'b11, 0, 0, 0, 4, 1'b1));
    rises = 0; last_rise = -1; nper = 0; bad_per = 0; prev_out = out;
    for (k = 0; k < 4096; k = k + 1) begin
      ro_in[4] = 1'b1; #10;
      ro_in[4] = 1'b0; #10;
      if (prev_out === 1'b0 && out === 1'b1) begin
        if (last_rise >= 0) begin
          nper = nper + 1;
          if (k - last_rise != 256) bad_per = bad_per + 1;
        end
        last_rise = k;
        rises = rises + 1;
      end
      prev_out = out;
    end
    checks = checks + 1;
    if (rises < 15 || bad_per != 0) begin
      errors = errors + 1;
      $display("FAIL divider: %0d OUT rises, %0d periods not equal to 256", rises, bad_per);
    end else
      $display("divider: %0d OUT periods, all 256 input cycles", nper);

    // an unselected RO must not reach OUT
    toggles = 0; prev_out = out;
    for (k = 0; k < 600; k = k + 1) begin
      ro_in[3] = 1'b1; #10;
      ro_in[3] = 1'b0; #10;
      if (out !== prev_out) toggles = toggles + 1;
      prev_out = out;
    end
    checks = checks + 1;
    if (toggles != 0) begin
      errors = errors + 1;
      $display("FAIL OUT toggled %0d times from unselected RO 3", toggles);
    end

    if (errors == 0) $display("TB RESULT: PASS (%0d checks)", checks);
    else             $display("TB RESULT: FAIL (%0d errors in %0d checks)", errors, checks);
    $finish;
  end
endmodule
