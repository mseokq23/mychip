/* Verilog module written by vlog2Verilog (qflow) */

module teg_ctrl(
    input sck,
    input sdi,
    input sle,
    input cck,
    input [5:0] ro_in,
    output out,
    output [11:0] row_sel,
    output [11:0] row_selb,
    output [7:0] col_sel,
    output [7:0] col_selb,
    output [9:0] cbcm_en,
    output [5:0] ro_en,
    output cbcm_clk
);

wire vdd = 1'b1;
wire gnd = 1'b0;

wire _60_ ;
wire _19_ ;
wire _57_ ;
wire out ;
wire _16_ ;
wire _54_ ;
wire _13_ ;
wire _51_ ;
wire _7_ ;
wire _48_ ;
wire [3:0] cbsel ;
wire _10_ ;
wire [7:0] col_selb ;
wire _4_ ;
wire _45_ ;
wire \g_div[4].q  ;
wire [2:0] col ;
wire _1_ ;
wire _42_ ;
wire _39_ ;
wire sdi ;
wire _36_ ;
wire [11:0] _74_ ;
wire [8:8] dclk ;
wire _33_ ;
wire [7:0] _71_ ;
wire _68_ ;
wire _30_ ;
wire [11:0] row_sel ;
wire cck ;
wire _27_ ;
wire _65_ ;
wire [7:0] col_sel ;
wire _24_ ;
wire _62_ ;
wire _59_ ;
wire \g_div[3].q  ;
wire _21_ ;
wire _18_ ;
wire _56_ ;
wire _15_ ;
wire _53_ ;
wire _9_ ;
wire _12_ ;
wire _50_ ;
wire _6_ ;
wire _47_ ;
wire sle ;
wire [19:0] sr ;
wire _3_ ;
wire _44_ ;
wire _0_ ;
wire _41_ ;
wire _38_ ;
wire _76_ ;
wire sck ;
wire \g_div[7].q  ;
wire \g_div[2].q  ;
wire _35_ ;
wire [11:0] _73_ ;
wire [1:0] mode ;
wire _32_ ;
wire [2:0] rosel ;
wire [9:0] _70_ ;
wire _29_ ;
wire _67_ ;
wire sck_bF$buf0 ;
wire sck_bF$buf1 ;
wire sck_bF$buf2 ;
wire sck_bF$buf3 ;
wire [11:0] row_selb ;
wire [5:0] ro_in ;
wire _26_ ;
wire _64_ ;
wire _23_ ;
wire [7:0] \g_div  ;
wire _61_ ;
wire _58_ ;
wire _20_ ;
wire _17_ ;
wire ro_mux ;
wire _55_ ;
wire _14_ ;
wire _52_ ;
wire \g_div[6].q  ;
wire \g_div[1].q  ;
wire _8_ ;
wire _49_ ;
wire _11_ ;
wire _5_ ;
wire _46_ ;
wire _2_ ;
wire _43_ ;
wire [3:0] row ;
wire _40_ ;
wire [9:0] cbcm_en ;
wire _37_ ;
wire _75_ ;
wire sle_bF$buf0 ;
wire sle_bF$buf1 ;
wire sle_bF$buf2 ;
wire sle_bF$buf3 ;
wire _34_ ;
wire div_rst_n ;
wire [7:0] _72_ ;
wire [5:0] _69_ ;
wire _31_ ;
wire _28_ ;
wire \g_div[5].q  ;
wire _66_ ;
wire \g_div[0].q  ;
wire _25_ ;
wire _63_ ;
wire cbcm_clk ;
wire [5:0] ro_en ;
wire _22_ ;

NAND2X1 _168_ (
    .A(col[2]),
    .B(_40_),
    .Y(_41_)
);

BUFX2 _130_ (
    .A(_69_[3]),
    .Y(ro_en[3])
);

BUFX2 _95_ (
    .A(_73_[6]),
    .Y(row_selb[6])
);

NAND2X1 _224_ (
    .A(cbsel[0]),
    .B(_66_),
    .Y(_67_)
);

NAND2X1 _262_ (
    .A(_49_),
    .B(_14_),
    .Y(_71_[0])
);

BUFX2 _127_ (
    .A(_70_[0]),
    .Y(cbcm_en[0])
);

INVX1 _165_ (
    .A(col[0]),
    .Y(_38_)
);

INVX1 _259_ (
    .A(_71_[2]),
    .Y(_72_[2])
);

DFFPOSX1 _297_ (
    .D(sdi),
    .CLK(sck_bF$buf0),
    .Q(sr[0])
);

BUFX2 _92_ (
    .A(_73_[9]),
    .Y(row_selb[9])
);

NAND3X1 _221_ (
    .A(_55_),
    .B(_64_),
    .C(_60_),
    .Y(_73_[0])
);

BUFX2 _124_ (
    .A(_70_[3]),
    .Y(cbcm_en[3])
);

BUFX2 _89_ (
    .A(_74_[0]),
    .Y(row_sel[0])
);

NAND3X1 _162_ (
    .A(rosel[2]),
    .B(_17_),
    .C(_32_),
    .Y(_35_)
);

NOR3X1 _218_ (
    .A(row[0]),
    .B(_65_),
    .C(_51_),
    .Y(_74_[2])
);

NAND2X1 _256_ (
    .A(_39_),
    .B(_14_),
    .Y(_71_[3])
);

DFFSR _294_ (
    .R(div_rst_n),
    .S(vdd),
    .D(dclk[8]),
    .CLK(_27_),
    .Q(\g_div[7].q )
);

NOR2X1 _159_ (
    .A(_30_),
    .B(_31_),
    .Y(_32_)
);

INVX2 _197_ (
    .A(_59_),
    .Y(_60_)
);

FILL FILL58050x14550 (
);

BUFX2 _121_ (
    .A(_70_[6]),
    .Y(cbcm_en[6])
);

BUFX2 _86_ (
    .A(_74_[3]),
    .Y(row_sel[3])
);

INVX2 _215_ (
    .A(_64_),
    .Y(_65_)
);

INVX1 _253_ (
    .A(_12_),
    .Y(_69_[0])
);

BUFX2 _118_ (
    .A(_70_[9]),
    .Y(cbcm_en[9])
);

DFFPOSX1 _291_ (
    .D(sr[12]),
    .CLK(sle_bF$buf1),
    .Q(cbsel[3])
);

AOI21X1 _156_ (
    .A(\g_div[7].q ),
    .B(div_rst_n),
    .C(_29_),
    .Y(_75_)
);

NOR3X1 _194_ (
    .A(row[0]),
    .B(_56_),
    .C(_51_),
    .Y(_74_[10])
);

DFFSR _288_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_33_),
    .CLK(_58_),
    .Q(\g_div[4].q )
);

BUFX2 _83_ (
    .A(_74_[6]),
    .Y(row_sel[6])
);

NOR3X1 _212_ (
    .A(row[0]),
    .B(_63_),
    .C(_59_),
    .Y(_74_[4])
);

NOR2X1 _250_ (
    .A(_11_),
    .B(_9_),
    .Y(_69_[2])
);

DFFPOSX1 _306_ (
    .D(sr[4]),
    .CLK(sle_bF$buf3),
    .Q(row[2])
);

BUFX2 _115_ (
    .A(_71_[2]),
    .Y(col_selb[2])
);

INVX1 _153_ (
    .A(\g_div[0].q ),
    .Y(_24_)
);

NAND3X1 _209_ (
    .A(row[0]),
    .B(_62_),
    .C(_60_),
    .Y(_73_[5])
);

INVX2 _191_ (
    .A(_54_),
    .Y(_56_)
);

NAND3X1 _247_ (
    .A(rosel[0]),
    .B(rosel[1]),
    .C(_19_),
    .Y(_10_)
);

DFFPOSX1 _285_ (
    .D(sr[15]),
    .CLK(sle_bF$buf2),
    .Q(rosel[2])
);

NOR2X1 _188_ (
    .A(row[2]),
    .B(_53_),
    .Y(_54_)
);

BUFX2 _80_ (
    .A(_74_[9]),
    .Y(row_sel[9])
);

DFFPOSX1 _303_ (
    .D(sr[5]),
    .CLK(sle_bF$buf0),
    .Q(row[3])
);

BUFX2 _112_ (
    .A(_71_[5]),
    .Y(col_selb[5])
);

BUFX2 _77_ (
    .A(_75_),
    .Y(out)
);

INVX1 _150_ (
    .A(\g_div[2].q ),
    .Y(_45_)
);

NOR3X1 _206_ (
    .A(_55_),
    .B(_63_),
    .C(_51_),
    .Y(_74_[7])
);

NAND2X1 _244_ (
    .A(cck),
    .B(_66_),
    .Y(_8_)
);

BUFX2 _109_ (
    .A(_72_[0]),
    .Y(col_sel[0])
);

DFFPOSX1 _282_ (
    .D(sr[10]),
    .CLK(sle_bF$buf1),
    .Q(cbsel[1])
);

INVX1 _147_ (
    .A(\g_div[7].q ),
    .Y(dclk[8])
);

NAND2X1 _185_ (
    .A(row[1]),
    .B(_40_),
    .Y(_51_)
);

DFFPOSX1 _279_ (
    .D(sr[13]),
    .CLK(sle_bF$buf2),
    .Q(rosel[0])
);

DFFSR _300_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_45_),
    .CLK(_36_),
    .Q(\g_div[2].q )
);

NOR2X1 _203_ (
    .A(row[3]),
    .B(_61_),
    .Y(_62_)
);

NOR2X1 _241_ (
    .A(_7_),
    .B(_6_),
    .Y(_70_[2])
);

BUFX2 _106_ (
    .A(_72_[3]),
    .Y(col_sel[3])
);

AND2X2 _144_ (
    .A(_15_),
    .B(rosel[0]),
    .Y(_26_)
);

NAND2X1 _182_ (
    .A(_49_),
    .B(_42_),
    .Y(_71_[4])
);

NOR2X1 _238_ (
    .A(_5_),
    .B(_3_),
    .Y(_70_[4])
);

DFFPOSX1 _276_ (
    .D(sr[9]),
    .CLK(sck_bF$buf0),
    .Q(sr[10])
);

INVX1 _179_ (
    .A(_47_),
    .Y(_48_)
);

NAND3X1 _200_ (
    .A(_55_),
    .B(_54_),
    .C(_60_),
    .Y(_73_[8])
);

FILL FILL57750x10950 (
);

BUFX2 _103_ (
    .A(_72_[6]),
    .Y(col_sel[6])
);

NAND3X1 _141_ (
    .A(rosel[0]),
    .B(rosel[1]),
    .C(ro_in[3]),
    .Y(_22_)
);

NAND3X1 _235_ (
    .A(cbsel[1]),
    .B(_2_),
    .C(_66_),
    .Y(_6_)
);

DFFPOSX1 _273_ (
    .D(sr[5]),
    .CLK(sck_bF$buf2),
    .Q(sr[6])
);

AOI22X1 _138_ (
    .A(ro_in[0]),
    .B(_17_),
    .C(_16_),
    .D(ro_in[2]),
    .Y(_18_)
);

NOR2X1 _176_ (
    .A(_46_),
    .B(_41_),
    .Y(_72_[6])
);

BUFX2 _100_ (
    .A(_73_[1]),
    .Y(row_selb[1])
);

INVX1 _232_ (
    .A(cbsel[3]),
    .Y(_4_)
);

DFFPOSX1 _270_ (
    .D(sr[6]),
    .CLK(sle_bF$buf0),
    .Q(col[0])
);

INVX1 _135_ (
    .A(rosel[1]),
    .Y(_15_)
);

FILL FILL57750x18150 (
);

NOR2X1 _173_ (
    .A(col[0]),
    .B(_37_),
    .Y(_44_)
);

INVX1 _229_ (
    .A(cbsel[0]),
    .Y(_2_)
);

DFFPOSX1 _267_ (
    .D(sr[7]),
    .CLK(sle_bF$buf0),
    .Q(col[1])
);

BUFX2 _132_ (
    .A(_69_[1]),
    .Y(ro_en[1])
);

BUFX2 _97_ (
    .A(_73_[4]),
    .Y(row_selb[4])
);

NAND2X1 _170_ (
    .A(_39_),
    .B(_42_),
    .Y(_71_[7])
);

NAND2X1 _226_ (
    .A(cbsel[3]),
    .B(_68_),
    .Y(_76_)
);

DFFPOSX1 _264_ (
    .D(sr[18]),
    .CLK(sck_bF$buf2),
    .Q(sr[19])
);

BUFX2 _129_ (
    .A(_69_[4]),
    .Y(ro_en[4])
);

NOR2X1 _167_ (
    .A(mode[1]),
    .B(_31_),
    .Y(_40_)
);

DFFPOSX1 _299_ (
    .D(sr[10]),
    .CLK(sck_bF$buf1),
    .Q(sr[11])
);

BUFX2 _94_ (
    .A(_73_[7]),
    .Y(row_selb[7])
);

NOR2X1 _223_ (
    .A(mode[0]),
    .B(_30_),
    .Y(_66_)
);

INVX1 _261_ (
    .A(_71_[1]),
    .Y(_72_[1])
);

BUFX2 _126_ (
    .A(_70_[1]),
    .Y(cbcm_en[1])
);

FILL FILL57750x25350 (
);

FILL FILL57450x3750 (
);

INVX1 _164_ (
    .A(col[1]),
    .Y(_37_)
);

NAND2X1 _258_ (
    .A(_44_),
    .B(_14_),
    .Y(_71_[2])
);

DFFPOSX1 _296_ (
    .D(sr[2]),
    .CLK(sle_bF$buf3),
    .Q(row[0])
);

NOR3X1 _199_ (
    .A(_55_),
    .B(_56_),
    .C(_59_),
    .Y(_74_[9])
);

BUFX2 _91_ (
    .A(_73_[10]),
    .Y(row_selb[10])
);

NOR3X1 _220_ (
    .A(_55_),
    .B(_65_),
    .C(_59_),
    .Y(_74_[1])
);

BUFX2 _123_ (
    .A(_70_[4]),
    .Y(cbcm_en[4])
);

BUFX2 _88_ (
    .A(_74_[1]),
    .Y(row_sel[1])
);

NOR2X1 _161_ (
    .A(_19_),
    .B(_34_),
    .Y(_69_[5])
);

NAND3X1 _217_ (
    .A(_55_),
    .B(_64_),
    .C(_52_),
    .Y(_73_[2])
);

NOR2X1 _255_ (
    .A(col[2]),
    .B(_13_),
    .Y(_14_)
);

DFFPOSX1 _293_ (
    .D(sr[1]),
    .CLK(sck_bF$buf0),
    .Q(sr[2])
);

INVX1 _158_ (
    .A(mode[0]),
    .Y(_31_)
);

NAND2X1 _196_ (
    .A(_57_),
    .B(_40_),
    .Y(_59_)
);

BUFX2 _120_ (
    .A(_70_[7]),
    .Y(cbcm_en[7])
);

BUFX2 _85_ (
    .A(_74_[4]),
    .Y(row_sel[4])
);

NAND3X1 _214_ (
    .A(row[0]),
    .B(_64_),
    .C(_52_),
    .Y(_73_[3])
);

NAND3X1 _252_ (
    .A(_19_),
    .B(_17_),
    .C(_32_),
    .Y(_12_)
);

DFFPOSX1 _308_ (
    .D(sr[14]),
    .CLK(sle_bF$buf2),
    .Q(rosel[1])
);

BUFX2 _117_ (
    .A(_71_[0]),
    .Y(col_selb[0])
);

DFFPOSX1 _290_ (
    .D(sr[17]),
    .CLK(sck_bF$buf2),
    .Q(sr[18])
);

FILL FILL58050x7350 (
);

NOR2X1 _155_ (
    .A(sr[19]),
    .B(div_rst_n),
    .Y(_29_)
);

NAND3X1 _193_ (
    .A(_55_),
    .B(_54_),
    .C(_52_),
    .Y(_73_[10])
);

NAND2X1 _249_ (
    .A(_19_),
    .B(_16_),
    .Y(_11_)
);

DFFPOSX1 _287_ (
    .D(sr[7]),
    .CLK(sck_bF$buf3),
    .Q(sr[8])
);

BUFX2 _82_ (
    .A(_74_[7]),
    .Y(row_sel[7])
);

NAND3X1 _211_ (
    .A(_55_),
    .B(_62_),
    .C(_60_),
    .Y(_73_[4])
);

FILL FILL57450x10950 (
);

DFFPOSX1 _305_ (
    .D(sr[2]),
    .CLK(sck_bF$buf3),
    .Q(sr[3])
);

BUFX2 _114_ (
    .A(_71_[3]),
    .Y(col_selb[3])
);

BUFX2 _79_ (
    .A(_74_[10]),
    .Y(row_sel[10])
);

INVX1 _152_ (
    .A(\g_div[6].q ),
    .Y(_27_)
);

NOR3X1 _208_ (
    .A(row[0]),
    .B(_63_),
    .C(_51_),
    .Y(_74_[6])
);

INVX4 _190_ (
    .A(row[0]),
    .Y(_55_)
);

INVX1 _246_ (
    .A(_32_),
    .Y(_9_)
);

DFFSR _284_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_58_),
    .CLK(_45_),
    .Q(\g_div[3].q )
);

INVX1 _149_ (
    .A(\g_div[3].q ),
    .Y(_58_)
);

INVX1 _187_ (
    .A(row[3]),
    .Y(_53_)
);

DFFPOSX1 _302_ (
    .D(sr[16]),
    .CLK(sck_bF$buf2),
    .Q(sr[17])
);

BUFX2 _111_ (
    .A(_71_[6]),
    .Y(col_selb[6])
);

INVX2 _205_ (
    .A(_62_),
    .Y(_63_)
);

NOR2X1 _243_ (
    .A(_7_),
    .B(_3_),
    .Y(_70_[0])
);

BUFX2 _108_ (
    .A(_72_[1]),
    .Y(col_sel[1])
);

DFFSR _281_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_27_),
    .CLK(_21_),
    .Q(\g_div[6].q )
);

AOI22X1 _146_ (
    .A(rosel[2]),
    .B(_28_),
    .C(_25_),
    .D(_18_),
    .Y(ro_mux)
);

NOR2X1 _184_ (
    .A(_50_),
    .B(_41_),
    .Y(_72_[4])
);

DFFPOSX1 _278_ (
    .D(sr[6]),
    .CLK(sck_bF$buf2),
    .Q(sr[7])
);

INVX1 _202_ (
    .A(row[2]),
    .Y(_61_)
);

NOR3X1 _240_ (
    .A(_1_),
    .B(_7_),
    .C(_67_),
    .Y(_70_[3])
);

BUFX2 _105_ (
    .A(_72_[4]),
    .Y(col_sel[4])
);

INVX1 _143_ (
    .A(_23_),
    .Y(_25_)
);

FILL FILL58050x10950 (
);

NOR2X1 _181_ (
    .A(col[1]),
    .B(col[0]),
    .Y(_49_)
);

NOR3X1 _237_ (
    .A(cbsel[1]),
    .B(_5_),
    .C(_67_),
    .Y(_70_[5])
);

DFFPOSX1 _275_ (
    .D(sr[3]),
    .CLK(sck_bF$buf3),
    .Q(sr[4])
);

NAND2X1 _178_ (
    .A(_47_),
    .B(_42_),
    .Y(_71_[5])
);

BUFX2 _102_ (
    .A(_72_[7]),
    .Y(col_sel[7])
);

NAND3X1 _140_ (
    .A(rosel[0]),
    .B(ro_in[1]),
    .C(_15_),
    .Y(_20_)
);

NOR3X1 _234_ (
    .A(_1_),
    .B(_5_),
    .C(_67_),
    .Y(_70_[7])
);

FILL FILL57450x25350 (
);

DFFPOSX1 _272_ (
    .D(sr[8]),
    .CLK(sle_bF$buf3),
    .Q(col[2])
);

NOR2X1 _137_ (
    .A(rosel[0]),
    .B(rosel[1]),
    .Y(_17_)
);

INVX1 _175_ (
    .A(_44_),
    .Y(_46_)
);

DFFPOSX1 _269_ (
    .D(sr[13]),
    .CLK(sck_bF$buf1),
    .Q(sr[14])
);

FILL FILL58050x18150 (
);

NOR2X1 _231_ (
    .A(_76_),
    .B(_3_),
    .Y(_70_[8])
);

BUFX2 _134_ (
    .A(_0_),
    .Y(cbcm_clk)
);

BUFX2 _99_ (
    .A(_73_[2]),
    .Y(row_selb[2])
);

NOR2X1 _172_ (
    .A(_41_),
    .B(_43_),
    .Y(_72_[7])
);

INVX1 _228_ (
    .A(cbsel[1]),
    .Y(_1_)
);

DFFPOSX1 _266_ (
    .D(sr[4]),
    .CLK(sck_bF$buf3),
    .Q(sr[5])
);

INVX1 _169_ (
    .A(_41_),
    .Y(_42_)
);

BUFX2 _131_ (
    .A(_69_[2]),
    .Y(ro_en[2])
);

FILL FILL57750x3750 (
);

BUFX2 _96_ (
    .A(_73_[5]),
    .Y(row_selb[5])
);

INVX1 _225_ (
    .A(cbsel[2]),
    .Y(_68_)
);

INVX1 _263_ (
    .A(_71_[0]),
    .Y(_72_[0])
);

BUFX2 _128_ (
    .A(_69_[5]),
    .Y(ro_en[5])
);

NOR2X1 _166_ (
    .A(_37_),
    .B(_38_),
    .Y(_39_)
);

FILL FILL58050x25350 (
);

DFFPOSX1 _298_ (
    .D(sr[9]),
    .CLK(sle_bF$buf1),
    .Q(cbsel[0])
);

BUFX2 _93_ (
    .A(_73_[8]),
    .Y(row_selb[8])
);

NOR3X1 _222_ (
    .A(row[0]),
    .B(_65_),
    .C(_59_),
    .Y(_74_[0])
);

NAND2X1 _260_ (
    .A(_47_),
    .B(_14_),
    .Y(_71_[1])
);

BUFX2 _125_ (
    .A(_70_[2]),
    .Y(cbcm_en[2])
);

INVX1 _163_ (
    .A(_35_),
    .Y(_69_[4])
);

NAND3X1 _219_ (
    .A(row[0]),
    .B(_64_),
    .C(_60_),
    .Y(_73_[1])
);

INVX1 _257_ (
    .A(_71_[3]),
    .Y(_72_[3])
);

DFFPOSX1 _295_ (
    .D(sr[8]),
    .CLK(sck_bF$buf0),
    .Q(sr[9])
);

NAND3X1 _198_ (
    .A(row[0]),
    .B(_54_),
    .C(_60_),
    .Y(_73_[9])
);

BUFX2 _90_ (
    .A(_73_[11]),
    .Y(row_selb[11])
);

BUFX2 _122_ (
    .A(_70_[5]),
    .Y(cbcm_en[5])
);

BUFX2 _87_ (
    .A(_74_[2]),
    .Y(row_sel[2])
);

NAND2X1 _160_ (
    .A(_26_),
    .B(_32_),
    .Y(_34_)
);

NOR3X1 _216_ (
    .A(_55_),
    .B(_65_),
    .C(_51_),
    .Y(_74_[3])
);

NAND2X1 _254_ (
    .A(mode[0]),
    .B(_30_),
    .Y(_13_)
);

BUFX2 _119_ (
    .A(_70_[8]),
    .Y(cbcm_en[8])
);

DFFPOSX1 _292_ (
    .D(sr[16]),
    .CLK(sle_bF$buf0),
    .Q(div_rst_n)
);

INVX1 _157_ (
    .A(mode[1]),
    .Y(_30_)
);

INVX1 _195_ (
    .A(row[1]),
    .Y(_57_)
);

FILL FILL57750x150 (
);

DFFPOSX1 _289_ (
    .D(sr[0]),
    .CLK(sle_bF$buf2),
    .Q(mode[0])
);

BUFX2 _84_ (
    .A(_74_[5]),
    .Y(row_sel[5])
);

NOR2X1 _213_ (
    .A(row[3]),
    .B(row[2]),
    .Y(_64_)
);

NOR2X1 _251_ (
    .A(rosel[2]),
    .B(_34_),
    .Y(_69_[1])
);

DFFSR _307_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_36_),
    .CLK(_24_),
    .Q(\g_div[1].q )
);

BUFX2 _116_ (
    .A(_71_[1]),
    .Y(col_selb[1])
);

INVX1 _154_ (
    .A(\g_div[4].q ),
    .Y(_33_)
);

NOR3X1 _192_ (
    .A(_55_),
    .B(_56_),
    .C(_51_),
    .Y(_74_[11])
);

NOR2X1 _248_ (
    .A(_10_),
    .B(_9_),
    .Y(_69_[3])
);

DFFPOSX1 _286_ (
    .D(sr[0]),
    .CLK(sck_bF$buf0),
    .Q(sr[1])
);

NAND3X1 _189_ (
    .A(row[0]),
    .B(_54_),
    .C(_52_),
    .Y(_73_[11])
);

BUFX2 _81_ (
    .A(_74_[8]),
    .Y(row_sel[8])
);

NOR3X1 _210_ (
    .A(_55_),
    .B(_63_),
    .C(_59_),
    .Y(_74_[5])
);

DFFPOSX1 _304_ (
    .D(sr[12]),
    .CLK(sck_bF$buf1),
    .Q(sr[13])
);

BUFX2 _113_ (
    .A(_71_[4]),
    .Y(col_selb[4])
);

BUFX2 _78_ (
    .A(_74_[11]),
    .Y(row_sel[11])
);

INVX1 _151_ (
    .A(\g_div[5].q ),
    .Y(_21_)
);

NAND3X1 _207_ (
    .A(_55_),
    .B(_62_),
    .C(_52_),
    .Y(_73_[6])
);

INVX1 _245_ (
    .A(_8_),
    .Y(_0_)
);

DFFPOSX1 _283_ (
    .D(sr[15]),
    .CLK(sck_bF$buf3),
    .Q(sr[16])
);

INVX1 _148_ (
    .A(\g_div[1].q ),
    .Y(_36_)
);

FILL FILL58050x150 (
);

INVX2 _186_ (
    .A(_51_),
    .Y(_52_)
);

DFFPOSX1 _301_ (
    .D(sr[1]),
    .CLK(sle_bF$buf3),
    .Q(mode[1])
);

BUFX2 _110_ (
    .A(_71_[7]),
    .Y(col_selb[7])
);

NAND3X1 _204_ (
    .A(row[0]),
    .B(_62_),
    .C(_52_),
    .Y(_73_[7])
);

NOR3X1 _242_ (
    .A(cbsel[1]),
    .B(_7_),
    .C(_67_),
    .Y(_70_[1])
);

BUFX2 _107_ (
    .A(_72_[2]),
    .Y(col_sel[2])
);

DFFPOSX1 _280_ (
    .D(sr[11]),
    .CLK(sck_bF$buf1),
    .Q(sr[12])
);

AOI22X1 _145_ (
    .A(ro_in[4]),
    .B(_17_),
    .C(_26_),
    .D(ro_in[5]),
    .Y(_28_)
);

INVX1 _183_ (
    .A(_49_),
    .Y(_50_)
);

NAND2X1 _239_ (
    .A(_4_),
    .B(_68_),
    .Y(_7_)
);

DFFSR _277_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_21_),
    .CLK(_33_),
    .Q(\g_div[5].q )
);

NOR3X1 _201_ (
    .A(row[0]),
    .B(_56_),
    .C(_59_),
    .Y(_74_[8])
);

BUFX2 _104_ (
    .A(_72_[5]),
    .Y(col_sel[5])
);

NAND3X1 _142_ (
    .A(_19_),
    .B(_22_),
    .C(_20_),
    .Y(_23_)
);

NOR2X1 _180_ (
    .A(_48_),
    .B(_41_),
    .Y(_72_[5])
);

NOR2X1 _236_ (
    .A(_5_),
    .B(_6_),
    .Y(_70_[6])
);

DFFPOSX1 _274_ (
    .D(sr[14]),
    .CLK(sck_bF$buf1),
    .Q(sr[15])
);

INVX1 _139_ (
    .A(rosel[2]),
    .Y(_19_)
);

NOR2X1 _177_ (
    .A(col[1]),
    .B(_38_),
    .Y(_47_)
);

FILL FILL58050x3750 (
);

BUFX2 _101_ (
    .A(_73_[0]),
    .Y(row_selb[0])
);

NAND2X1 _233_ (
    .A(cbsel[2]),
    .B(_4_),
    .Y(_5_)
);

DFFPOSX1 _271_ (
    .D(sr[11]),
    .CLK(sle_bF$buf1),
    .Q(cbsel[2])
);

NOR2X1 _136_ (
    .A(rosel[0]),
    .B(_15_),
    .Y(_16_)
);

NAND2X1 _174_ (
    .A(_44_),
    .B(_42_),
    .Y(_71_[6])
);

DFFSR _268_ (
    .R(div_rst_n),
    .S(vdd),
    .D(_24_),
    .CLK(ro_mux),
    .Q(\g_div[0].q )
);

CLKBUF1 CLKBUF1_insert0 (
    .A(sle),
    .Y(sle_bF$buf3)
);

CLKBUF1 CLKBUF1_insert1 (
    .A(sle),
    .Y(sle_bF$buf2)
);

CLKBUF1 CLKBUF1_insert2 (
    .A(sle),
    .Y(sle_bF$buf1)
);

CLKBUF1 CLKBUF1_insert3 (
    .A(sle),
    .Y(sle_bF$buf0)
);

CLKBUF1 CLKBUF1_insert4 (
    .A(sck),
    .Y(sck_bF$buf3)
);

CLKBUF1 CLKBUF1_insert5 (
    .A(sck),
    .Y(sck_bF$buf2)
);

CLKBUF1 CLKBUF1_insert6 (
    .A(sck),
    .Y(sck_bF$buf1)
);

CLKBUF1 CLKBUF1_insert7 (
    .A(sck),
    .Y(sck_bF$buf0)
);

NAND3X1 _230_ (
    .A(_1_),
    .B(_2_),
    .C(_66_),
    .Y(_3_)
);

BUFX2 _133_ (
    .A(_69_[0]),
    .Y(ro_en[0])
);

BUFX2 _98_ (
    .A(_73_[3]),
    .Y(row_selb[3])
);

INVX1 _171_ (
    .A(_39_),
    .Y(_43_)
);

NOR3X1 _227_ (
    .A(cbsel[1]),
    .B(_76_),
    .C(_67_),
    .Y(_70_[9])
);

DFFPOSX1 _265_ (
    .D(sr[3]),
    .CLK(sle_bF$buf3),
    .Q(row[1])
);

endmodule
