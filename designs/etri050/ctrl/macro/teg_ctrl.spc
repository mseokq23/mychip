.subckt teg_ctrl vdd gnd sck sdi sle cck ro_in[0]
+ ro_in[1] ro_in[2] ro_in[3] ro_in[4] ro_in[5] out row_sel[0] row_sel[1]
+ row_sel[2] row_sel[3] row_sel[4] row_sel[5] row_sel[6] row_sel[7] row_sel[8] row_sel[9]
+ row_sel[10] row_sel[11] row_selb[0] row_selb[1] row_selb[2] row_selb[3] row_selb[4] row_selb[5]
+ row_selb[6] row_selb[7] row_selb[8] row_selb[9] row_selb[10] row_selb[11] col_sel[0] col_sel[1]
+ col_sel[2] col_sel[3] col_sel[4] col_sel[5] col_sel[6] col_sel[7] col_selb[0] col_selb[1]
+ col_selb[2] col_selb[3] col_selb[4] col_selb[5] col_selb[6] col_selb[7] cbcm_en[0] cbcm_en[1]
+ cbcm_en[2] cbcm_en[3] cbcm_en[4] cbcm_en[5] cbcm_en[6] cbcm_en[7] cbcm_en[8] cbcm_en[9]
+ ro_en[0] ro_en[1] ro_en[2] ro_en[3] ro_en[4] ro_en[5] cbcm_clk 

X_168_ col[2] _40_ _41_ vdd gnd NAND2X1
X_130_ _69_[3] ro_en[3] vdd gnd BUFX2
X_95_ _73_[6] row_selb[6] vdd gnd BUFX2
X_224_ cbsel[0] _66_ _67_ vdd gnd NAND2X1
X_262_ _49_ _14_ _71_[0] vdd gnd NAND2X1
X_127_ _70_[0] cbcm_en[0] vdd gnd BUFX2
X_165_ col[0] _38_ vdd gnd INVX1
X_259_ _71_[2] _72_[2] vdd gnd INVX1
X_297_ sdi sck_bF$buf0 sr[0] vdd gnd DFFPOSX1
X_92_ _73_[9] row_selb[9] vdd gnd BUFX2
X_221_ _55_ _64_ _60_ _73_[0] vdd gnd NAND3X1
X_124_ _70_[3] cbcm_en[3] vdd gnd BUFX2
X_89_ _74_[0] row_sel[0] vdd gnd BUFX2
X_162_ rosel[2] _17_ _32_ _35_ vdd gnd NAND3X1
X_218_ row[0] _65_ _51_ _74_[2] vdd gnd NOR3X1
X_256_ _39_ _14_ _71_[3] vdd gnd NAND2X1
X_294_ div_rst_n vdd dclk[8] _27_ _g_div[7].q_ vdd 
+ gnd
+ DFFSR
X_159_ _30_ _31_ _32_ vdd gnd NOR2X1
X_197_ _59_ _60_ vdd gnd INVX2
XFILL58050x14550 gnd vdd FILL
X_121_ _70_[6] cbcm_en[6] vdd gnd BUFX2
X_86_ _74_[3] row_sel[3] vdd gnd BUFX2
X_215_ _64_ _65_ vdd gnd INVX2
X_253_ _12_ _69_[0] vdd gnd INVX1
X_118_ _70_[9] cbcm_en[9] vdd gnd BUFX2
X_291_ sr[12] sle_bF$buf1 cbsel[3] vdd gnd DFFPOSX1
X_156_ _g_div[7].q_ div_rst_n _29_ _75_ vdd gnd AOI21X1
X_194_ row[0] _56_ _51_ _74_[10] vdd gnd NOR3X1
X_288_ div_rst_n vdd _33_ _58_ _g_div[4].q_ vdd 
+ gnd
+ DFFSR
X_83_ _74_[6] row_sel[6] vdd gnd BUFX2
X_212_ row[0] _63_ _59_ _74_[4] vdd gnd NOR3X1
X_250_ _11_ _9_ _69_[2] vdd gnd NOR2X1
X_306_ sr[4] sle_bF$buf3 row[2] vdd gnd DFFPOSX1
X_115_ _71_[2] col_selb[2] vdd gnd BUFX2
X_153_ _g_div[0].q_ _24_ vdd gnd INVX1
X_209_ row[0] _62_ _60_ _73_[5] vdd gnd NAND3X1
X_191_ _54_ _56_ vdd gnd INVX2
X_247_ rosel[0] rosel[1] _19_ _10_ vdd gnd NAND3X1
X_285_ sr[15] sle_bF$buf2 rosel[2] vdd gnd DFFPOSX1
X_188_ row[2] _53_ _54_ vdd gnd NOR2X1
X_80_ _74_[9] row_sel[9] vdd gnd BUFX2
X_303_ sr[5] sle_bF$buf0 row[3] vdd gnd DFFPOSX1
X_112_ _71_[5] col_selb[5] vdd gnd BUFX2
X_77_ _75_ out vdd gnd BUFX2
X_150_ _g_div[2].q_ _45_ vdd gnd INVX1
X_206_ _55_ _63_ _51_ _74_[7] vdd gnd NOR3X1
X_244_ cck _66_ _8_ vdd gnd NAND2X1
X_109_ _72_[0] col_sel[0] vdd gnd BUFX2
X_282_ sr[10] sle_bF$buf1 cbsel[1] vdd gnd DFFPOSX1
X_147_ _g_div[7].q_ dclk[8] vdd gnd INVX1
X_185_ row[1] _40_ _51_ vdd gnd NAND2X1
X_279_ sr[13] sle_bF$buf2 rosel[0] vdd gnd DFFPOSX1
X_300_ div_rst_n vdd _45_ _36_ _g_div[2].q_ vdd 
+ gnd
+ DFFSR
X_203_ row[3] _61_ _62_ vdd gnd NOR2X1
X_241_ _7_ _6_ _70_[2] vdd gnd NOR2X1
X_106_ _72_[3] col_sel[3] vdd gnd BUFX2
X_144_ _15_ rosel[0] _26_ vdd gnd AND2X2
X_182_ _49_ _42_ _71_[4] vdd gnd NAND2X1
X_238_ _5_ _3_ _70_[4] vdd gnd NOR2X1
X_276_ sr[9] sck_bF$buf0 sr[10] vdd gnd DFFPOSX1
X_179_ _47_ _48_ vdd gnd INVX1
X_200_ _55_ _54_ _60_ _73_[8] vdd gnd NAND3X1
XFILL57750x10950 gnd vdd FILL
X_103_ _72_[6] col_sel[6] vdd gnd BUFX2
X_141_ rosel[0] rosel[1] ro_in[3] _22_ vdd gnd NAND3X1
X_235_ cbsel[1] _2_ _66_ _6_ vdd gnd NAND3X1
X_273_ sr[5] sck_bF$buf2 sr[6] vdd gnd DFFPOSX1
X_138_ ro_in[0] _17_ _16_ ro_in[2] _18_ vdd 
+ gnd
+ AOI22X1
X_176_ _46_ _41_ _72_[6] vdd gnd NOR2X1
X_100_ _73_[1] row_selb[1] vdd gnd BUFX2
X_232_ cbsel[3] _4_ vdd gnd INVX1
X_270_ sr[6] sle_bF$buf0 col[0] vdd gnd DFFPOSX1
X_135_ rosel[1] _15_ vdd gnd INVX1
XFILL57750x18150 gnd vdd FILL
X_173_ col[0] _37_ _44_ vdd gnd NOR2X1
X_229_ cbsel[0] _2_ vdd gnd INVX1
X_267_ sr[7] sle_bF$buf0 col[1] vdd gnd DFFPOSX1
X_132_ _69_[1] ro_en[1] vdd gnd BUFX2
X_97_ _73_[4] row_selb[4] vdd gnd BUFX2
X_170_ _39_ _42_ _71_[7] vdd gnd NAND2X1
X_226_ cbsel[3] _68_ _76_ vdd gnd NAND2X1
X_264_ sr[18] sck_bF$buf2 sr[19] vdd gnd DFFPOSX1
X_129_ _69_[4] ro_en[4] vdd gnd BUFX2
X_167_ mode[1] _31_ _40_ vdd gnd NOR2X1
X_299_ sr[10] sck_bF$buf1 sr[11] vdd gnd DFFPOSX1
X_94_ _73_[7] row_selb[7] vdd gnd BUFX2
X_223_ mode[0] _30_ _66_ vdd gnd NOR2X1
X_261_ _71_[1] _72_[1] vdd gnd INVX1
X_126_ _70_[1] cbcm_en[1] vdd gnd BUFX2
XFILL57750x25350 gnd vdd FILL
XFILL57450x3750 gnd vdd FILL
X_164_ col[1] _37_ vdd gnd INVX1
X_258_ _44_ _14_ _71_[2] vdd gnd NAND2X1
X_296_ sr[2] sle_bF$buf3 row[0] vdd gnd DFFPOSX1
X_199_ _55_ _56_ _59_ _74_[9] vdd gnd NOR3X1
X_91_ _73_[10] row_selb[10] vdd gnd BUFX2
X_220_ _55_ _65_ _59_ _74_[1] vdd gnd NOR3X1
X_123_ _70_[4] cbcm_en[4] vdd gnd BUFX2
X_88_ _74_[1] row_sel[1] vdd gnd BUFX2
X_161_ _19_ _34_ _69_[5] vdd gnd NOR2X1
X_217_ _55_ _64_ _52_ _73_[2] vdd gnd NAND3X1
X_255_ col[2] _13_ _14_ vdd gnd NOR2X1
X_293_ sr[1] sck_bF$buf0 sr[2] vdd gnd DFFPOSX1
X_158_ mode[0] _31_ vdd gnd INVX1
X_196_ _57_ _40_ _59_ vdd gnd NAND2X1
X_120_ _70_[7] cbcm_en[7] vdd gnd BUFX2
X_85_ _74_[4] row_sel[4] vdd gnd BUFX2
X_214_ row[0] _64_ _52_ _73_[3] vdd gnd NAND3X1
X_252_ _19_ _17_ _32_ _12_ vdd gnd NAND3X1
X_308_ sr[14] sle_bF$buf2 rosel[1] vdd gnd DFFPOSX1
X_117_ _71_[0] col_selb[0] vdd gnd BUFX2
X_290_ sr[17] sck_bF$buf2 sr[18] vdd gnd DFFPOSX1
XFILL58050x7350 gnd vdd FILL
X_155_ sr[19] div_rst_n _29_ vdd gnd NOR2X1
X_193_ _55_ _54_ _52_ _73_[10] vdd gnd NAND3X1
X_249_ _19_ _16_ _11_ vdd gnd NAND2X1
X_287_ sr[7] sck_bF$buf3 sr[8] vdd gnd DFFPOSX1
X_82_ _74_[7] row_sel[7] vdd gnd BUFX2
X_211_ _55_ _62_ _60_ _73_[4] vdd gnd NAND3X1
XFILL57450x10950 gnd vdd FILL
X_305_ sr[2] sck_bF$buf3 sr[3] vdd gnd DFFPOSX1
X_114_ _71_[3] col_selb[3] vdd gnd BUFX2
X_79_ _74_[10] row_sel[10] vdd gnd BUFX2
X_152_ _g_div[6].q_ _27_ vdd gnd INVX1
X_208_ row[0] _63_ _51_ _74_[6] vdd gnd NOR3X1
X_190_ row[0] _55_ vdd gnd INVX4
X_246_ _32_ _9_ vdd gnd INVX1
X_284_ div_rst_n vdd _58_ _45_ _g_div[3].q_ vdd 
+ gnd
+ DFFSR
X_149_ _g_div[3].q_ _58_ vdd gnd INVX1
X_187_ row[3] _53_ vdd gnd INVX1
X_302_ sr[16] sck_bF$buf2 sr[17] vdd gnd DFFPOSX1
X_111_ _71_[6] col_selb[6] vdd gnd BUFX2
X_205_ _62_ _63_ vdd gnd INVX2
X_243_ _7_ _3_ _70_[0] vdd gnd NOR2X1
X_108_ _72_[1] col_sel[1] vdd gnd BUFX2
X_281_ div_rst_n vdd _27_ _21_ _g_div[6].q_ vdd 
+ gnd
+ DFFSR
X_146_ rosel[2] _28_ _25_ _18_ ro_mux vdd 
+ gnd
+ AOI22X1
X_184_ _50_ _41_ _72_[4] vdd gnd NOR2X1
X_278_ sr[6] sck_bF$buf2 sr[7] vdd gnd DFFPOSX1
X_202_ row[2] _61_ vdd gnd INVX1
X_240_ _1_ _7_ _67_ _70_[3] vdd gnd NOR3X1
X_105_ _72_[4] col_sel[4] vdd gnd BUFX2
X_143_ _23_ _25_ vdd gnd INVX1
XFILL58050x10950 gnd vdd FILL
X_181_ col[1] col[0] _49_ vdd gnd NOR2X1
X_237_ cbsel[1] _5_ _67_ _70_[5] vdd gnd NOR3X1
X_275_ sr[3] sck_bF$buf3 sr[4] vdd gnd DFFPOSX1
X_178_ _47_ _42_ _71_[5] vdd gnd NAND2X1
X_102_ _72_[7] col_sel[7] vdd gnd BUFX2
X_140_ rosel[0] ro_in[1] _15_ _20_ vdd gnd NAND3X1
X_234_ _1_ _5_ _67_ _70_[7] vdd gnd NOR3X1
XFILL57450x25350 gnd vdd FILL
X_272_ sr[8] sle_bF$buf3 col[2] vdd gnd DFFPOSX1
X_137_ rosel[0] rosel[1] _17_ vdd gnd NOR2X1
X_175_ _44_ _46_ vdd gnd INVX1
X_269_ sr[13] sck_bF$buf1 sr[14] vdd gnd DFFPOSX1
XFILL58050x18150 gnd vdd FILL
X_231_ _76_ _3_ _70_[8] vdd gnd NOR2X1
X_134_ _0_ cbcm_clk vdd gnd BUFX2
X_99_ _73_[2] row_selb[2] vdd gnd BUFX2
X_172_ _41_ _43_ _72_[7] vdd gnd NOR2X1
X_228_ cbsel[1] _1_ vdd gnd INVX1
X_266_ sr[4] sck_bF$buf3 sr[5] vdd gnd DFFPOSX1
X_169_ _41_ _42_ vdd gnd INVX1
X_131_ _69_[2] ro_en[2] vdd gnd BUFX2
XFILL57750x3750 gnd vdd FILL
X_96_ _73_[5] row_selb[5] vdd gnd BUFX2
X_225_ cbsel[2] _68_ vdd gnd INVX1
X_263_ _71_[0] _72_[0] vdd gnd INVX1
X_128_ _69_[5] ro_en[5] vdd gnd BUFX2
X_166_ _37_ _38_ _39_ vdd gnd NOR2X1
XFILL58050x25350 gnd vdd FILL
X_298_ sr[9] sle_bF$buf1 cbsel[0] vdd gnd DFFPOSX1
X_93_ _73_[8] row_selb[8] vdd gnd BUFX2
X_222_ row[0] _65_ _59_ _74_[0] vdd gnd NOR3X1
X_260_ _47_ _14_ _71_[1] vdd gnd NAND2X1
X_125_ _70_[2] cbcm_en[2] vdd gnd BUFX2
X_163_ _35_ _69_[4] vdd gnd INVX1
X_219_ row[0] _64_ _60_ _73_[1] vdd gnd NAND3X1
X_257_ _71_[3] _72_[3] vdd gnd INVX1
X_295_ sr[8] sck_bF$buf0 sr[9] vdd gnd DFFPOSX1
X_198_ row[0] _54_ _60_ _73_[9] vdd gnd NAND3X1
X_90_ _73_[11] row_selb[11] vdd gnd BUFX2
X_122_ _70_[5] cbcm_en[5] vdd gnd BUFX2
X_87_ _74_[2] row_sel[2] vdd gnd BUFX2
X_160_ _26_ _32_ _34_ vdd gnd NAND2X1
X_216_ _55_ _65_ _51_ _74_[3] vdd gnd NOR3X1
X_254_ mode[0] _30_ _13_ vdd gnd NAND2X1
X_119_ _70_[8] cbcm_en[8] vdd gnd BUFX2
X_292_ sr[16] sle_bF$buf0 div_rst_n vdd gnd DFFPOSX1
X_157_ mode[1] _30_ vdd gnd INVX1
X_195_ row[1] _57_ vdd gnd INVX1
XFILL57750x150 gnd vdd FILL
X_289_ sr[0] sle_bF$buf2 mode[0] vdd gnd DFFPOSX1
X_84_ _74_[5] row_sel[5] vdd gnd BUFX2
X_213_ row[3] row[2] _64_ vdd gnd NOR2X1
X_251_ rosel[2] _34_ _69_[1] vdd gnd NOR2X1
X_307_ div_rst_n vdd _36_ _24_ _g_div[1].q_ vdd 
+ gnd
+ DFFSR
X_116_ _71_[1] col_selb[1] vdd gnd BUFX2
X_154_ _g_div[4].q_ _33_ vdd gnd INVX1
X_192_ _55_ _56_ _51_ _74_[11] vdd gnd NOR3X1
X_248_ _10_ _9_ _69_[3] vdd gnd NOR2X1
X_286_ sr[0] sck_bF$buf0 sr[1] vdd gnd DFFPOSX1
X_189_ row[0] _54_ _52_ _73_[11] vdd gnd NAND3X1
X_81_ _74_[8] row_sel[8] vdd gnd BUFX2
X_210_ _55_ _63_ _59_ _74_[5] vdd gnd NOR3X1
X_304_ sr[12] sck_bF$buf1 sr[13] vdd gnd DFFPOSX1
X_113_ _71_[4] col_selb[4] vdd gnd BUFX2
X_78_ _74_[11] row_sel[11] vdd gnd BUFX2
X_151_ _g_div[5].q_ _21_ vdd gnd INVX1
X_207_ _55_ _62_ _52_ _73_[6] vdd gnd NAND3X1
X_245_ _8_ _0_ vdd gnd INVX1
X_283_ sr[15] sck_bF$buf3 sr[16] vdd gnd DFFPOSX1
X_148_ _g_div[1].q_ _36_ vdd gnd INVX1
XFILL58050x150 gnd vdd FILL
X_186_ _51_ _52_ vdd gnd INVX2
X_301_ sr[1] sle_bF$buf3 mode[1] vdd gnd DFFPOSX1
X_110_ _71_[7] col_selb[7] vdd gnd BUFX2
X_204_ row[0] _62_ _52_ _73_[7] vdd gnd NAND3X1
X_242_ cbsel[1] _7_ _67_ _70_[1] vdd gnd NOR3X1
X_107_ _72_[2] col_sel[2] vdd gnd BUFX2
X_280_ sr[11] sck_bF$buf1 sr[12] vdd gnd DFFPOSX1
X_145_ ro_in[4] _17_ _26_ ro_in[5] _28_ vdd 
+ gnd
+ AOI22X1
X_183_ _49_ _50_ vdd gnd INVX1
X_239_ _4_ _68_ _7_ vdd gnd NAND2X1
X_277_ div_rst_n vdd _21_ _33_ _g_div[5].q_ vdd 
+ gnd
+ DFFSR
X_201_ row[0] _56_ _59_ _74_[8] vdd gnd NOR3X1
X_104_ _72_[5] col_sel[5] vdd gnd BUFX2
X_142_ _19_ _22_ _20_ _23_ vdd gnd NAND3X1
X_180_ _48_ _41_ _72_[5] vdd gnd NOR2X1
X_236_ _5_ _6_ _70_[6] vdd gnd NOR2X1
X_274_ sr[14] sck_bF$buf1 sr[15] vdd gnd DFFPOSX1
X_139_ rosel[2] _19_ vdd gnd INVX1
X_177_ col[1] _38_ _47_ vdd gnd NOR2X1
XFILL58050x3750 gnd vdd FILL
X_101_ _73_[0] row_selb[0] vdd gnd BUFX2
X_233_ cbsel[2] _4_ _5_ vdd gnd NAND2X1
X_271_ sr[11] sle_bF$buf1 cbsel[2] vdd gnd DFFPOSX1
X_136_ rosel[0] _15_ _16_ vdd gnd NOR2X1
X_174_ _44_ _42_ _71_[6] vdd gnd NAND2X1
X_268_ div_rst_n vdd _24_ ro_mux _g_div[0].q_ vdd 
+ gnd
+ DFFSR
XCLKBUF1_insert0 sle sle_bF$buf3 vdd gnd CLKBUF1
XCLKBUF1_insert1 sle sle_bF$buf2 vdd gnd CLKBUF1
XCLKBUF1_insert2 sle sle_bF$buf1 vdd gnd CLKBUF1
XCLKBUF1_insert3 sle sle_bF$buf0 vdd gnd CLKBUF1
XCLKBUF1_insert4 sck sck_bF$buf3 vdd gnd CLKBUF1
XCLKBUF1_insert5 sck sck_bF$buf2 vdd gnd CLKBUF1
XCLKBUF1_insert6 sck sck_bF$buf1 vdd gnd CLKBUF1
XCLKBUF1_insert7 sck sck_bF$buf0 vdd gnd CLKBUF1
X_230_ _1_ _2_ _66_ _3_ vdd gnd NAND3X1
X_133_ _69_[0] ro_en[0] vdd gnd BUFX2
X_98_ _73_[3] row_selb[3] vdd gnd BUFX2
X_171_ _39_ _43_ vdd gnd INVX1
X_227_ cbsel[1] _76_ _67_ _70_[9] vdd gnd NOR3X1
X_265_ sr[3] sle_bF$buf3 row[1] vdd gnd DFFPOSX1

.ends
.end
