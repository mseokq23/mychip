v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {ETRI 0.5um NMOS Id-Vg (VDS = 0.1 V) - model: ETRI open-source kit (nfet)} -200 -260 0 0 0.4 0.4 {}
C {nmos4.sym} 200 0 0 0 {name=M1 model=nfet w=20u l=20u del=0 m=1}
C {lab_pin.sym} 220 -30 0 1 {name=p1 sig_type=std_logic lab=d}
C {lab_pin.sym} 180 0 0 0 {name=p2 sig_type=std_logic lab=g}
C {gnd.sym} 220 30 0 0 {name=l1 lab=GND}
C {gnd.sym} 220 0 3 0 {name=l2 lab=GND}
C {vsource.sym} 400 0 0 0 {name=VD value=0.1 savecurrent=false}
C {lab_pin.sym} 400 -30 0 1 {name=p3 sig_type=std_logic lab=d}
C {gnd.sym} 400 30 0 0 {name=l3 lab=GND}
C {vsource.sym} 0 0 0 0 {name=VG value=0 savecurrent=false}
C {lab_pin.sym} 0 -30 0 1 {name=p4 sig_type=std_logic lab=g}
C {gnd.sym} 0 30 0 0 {name=l4 lab=GND}
C {code_shown.sym} -200 -200 0 0 {name=MODELS only_toplevel=true format="tcleval( @value )" value=".include $::ETRI050_MODEL"}
C {code_shown.sym} -200 -150 0 0 {name=CONTROL only_toplevel=true value="
.control
dc VG 0 5 0.01
let id = -i(VD)
meas dc vt find v(g) when id=1e-7
echo \\"Vt (W/L = 20/20 um, ID = 0.1 uA) = $&vt V\\"
.endc
"}
