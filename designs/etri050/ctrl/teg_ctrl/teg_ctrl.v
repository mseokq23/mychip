// teg_ctrl: control logic of the on-chip characterization IC (ETRI 0.5 um, kit standard cells)
//
// Scan interface
//   sck  shifts sdi into a 20-bit shift register (MSB first; the first bit ends in sr[19])
//   sle  rising edge copies the shift register into the shadow register that drives the decoders
//   out  sr[19] (scan read-back) when osel = 0, RO / 256 when osel = 1
//
// Shadow register fields (bits 17..19 are spare)
//   [1:0]   mode   00 off, 01 Kelvin array, 10 CBCM, 11 ring oscillators
//   [5:2]   row    array row 0..11 (12..15 select nothing)
//   [8:6]   col    array column 0..7
//   [12:9]  cbsel  CBCM cell 0..9 (10..15 select nothing)
//   [15:13] rosel  ring oscillator 0..5 (6, 7 select nothing)
//   [16]    osel   output select; 0 also holds the divider in reset
//
// Only one block is enabled at a time (mode), so array, CBCM and RO never run together.
module teg_ctrl (
  input  wire        sck, sdi, sle, cck,
  input  wire [5:0]  ro_in,          // ring oscillator taps (one per RO)
  output wire        out,
  output wire [11:0] row_sel, row_selb,
  output wire [7:0]  col_sel, col_selb,
  output wire [9:0]  cbcm_en,
  output wire [5:0]  ro_en,
  output wire        cbcm_clk
);
  reg [19:0] sr, sh;
  always @(posedge sck) sr <= {sr[18:0], sdi};
  always @(posedge sle) sh <= sr;

  wire [1:0] mode  = sh[1:0];
  wire [3:0] row   = sh[5:2];
  wire [2:0] col   = sh[8:6];
  wire [3:0] cbsel  = sh[12:9];
  wire [2:0] rosel = sh[15:13];
  wire       osel  = sh[16];
  wire m_arr = (mode == 2'b01), m_cb = (mode == 2'b10), m_ro = (mode == 2'b11);

  genvar i;
  generate
    for (i = 0; i < 12; i = i + 1) begin : g_row
      assign row_sel[i]  = m_arr & (row == i);
      assign row_selb[i] = ~row_sel[i];
    end
    for (i = 0; i < 8; i = i + 1) begin : g_col
      assign col_sel[i]  = m_arr & (col == i);
      assign col_selb[i] = ~col_sel[i];
    end
    for (i = 0; i < 10; i = i + 1) begin : g_cb
      assign cbcm_en[i] = m_cb & (cbsel == i);
    end
    for (i = 0; i < 6; i = i + 1) begin : g_ro
      assign ro_en[i] = m_ro & (rosel == i);
    end
  endgenerate

  // CBCM clock is gated before the non-overlap generator
  assign cbcm_clk = cck & m_cb;

  // RO select (8:1, codes 6 and 7 give a constant 0)
  wire ro_mux = rosel[2] ? (rosel[1] ? 1'b0 : (rosel[0] ? ro_in[5] : ro_in[4]))
                         : (rosel[1] ? (rosel[0] ? ro_in[3] : ro_in[2]) : (rosel[0] ? ro_in[1] : ro_in[0]));

  // Ripple divide-by-256. The asynchronous reset (osel = 0) gives a known start phase and
  // lets the gate-level netlist be simulated without X-pessimism.
  wire div_rst_n = osel;
  wire [8:0] dclk;
  assign dclk[0] = ro_mux;
  generate
    for (i = 0; i < 8; i = i + 1) begin : g_div
      reg q;
      always @(posedge dclk[i] or negedge div_rst_n)
        if (!div_rst_n) q <= 1'b0;
        else            q <= ~q;
      assign dclk[i+1] = ~q;
    end
  endgenerate

  assign out = osel ? dclk[8] : sr[19];
endmodule
