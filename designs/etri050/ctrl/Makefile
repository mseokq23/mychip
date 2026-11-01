# Control block teg_ctrl: RTL simulation, synthesis with the kit liberty, gate-level simulation
#   make sim       RTL + self-checking testbench (Icarus Verilog)
#   make synth     Yosys with the kit liberty -> build/teg_ctrl_syn.v, cell count and LEF area
#   make gatesim   the same testbench on the synthesized netlist with the kit cell models
#   make flow      place and route with qflow (run_flow.sh)
#   make qflowsim  the testbench on the netlist qflow synthesized (build/qflow/synthesis)
REPO  := $(abspath ../../..)
KIT   ?= $(firstword $(wildcard $(REPO)/.pdk/ETRI050_DesignKit) $(wildcard $(HOME)/ETRI050_DesignKit))
LIB   := $(KIT)/digital_ETRI/khu_etri05_stdcells.lib
LEF   := $(KIT)/digital_ETRI/etri050_stdcells.lef
CELLV := $(KIT)/digital_ETRI/khu_etri05_stdcells.v
YOSYS ?= yosys
TOP   := teg_ctrl
B     := build

.PHONY: all sim synth gatesim flow qflowsim clean check-kit
all: sim synth gatesim

check-kit:
	@test -f "$(LIB)" || { echo "ETRI kit not found (KIT=$(KIT)); run scripts/setup-etri050.sh"; exit 1; }

sim: | $(B)
	iverilog -g2005 -o $(B)/tb_rtl.vvp tb/tb_$(TOP).v $(TOP)/$(TOP).v
	vvp -n $(B)/tb_rtl.vvp | tee $(B)/sim_rtl.log
	@grep -q 'TB RESULT: PASS' $(B)/sim_rtl.log

synth: check-kit | $(B)
	$(YOSYS) -q -l $(B)/synth.log -p "read_verilog $(TOP)/$(TOP).v; synth -top $(TOP) -flatten; dfflibmap -liberty $(LIB); abc -liberty $(LIB); opt_clean; stat; write_verilog -noattr $(B)/$(TOP)_syn.v"
	python3 cell_area.py $(B)/$(TOP)_syn.v $(LEF) $(TOP) | tee $(B)/area.txt

gatesim: synth
	iverilog -g2005 -Ttyp -o $(B)/tb_gate.vvp tb/tb_$(TOP).v $(B)/$(TOP)_syn.v $(CELLV)
	vvp -n $(B)/tb_gate.vvp | tee $(B)/sim_gate.log
	@grep -q 'TB RESULT: PASS' $(B)/sim_gate.log

flow: check-kit
	bash run_flow.sh

qflowsim: check-kit
	iverilog -g2005 -Ttyp -o $(B)/tb_qflow.vvp tb/tb_$(TOP).v $(B)/qflow/synthesis/$(TOP).rtlnopwr.v $(CELLV)
	vvp -n $(B)/tb_qflow.vvp | tee $(B)/sim_qflow.log
	@grep -q 'TB RESULT: PASS' $(B)/sim_qflow.log

$(B):
	mkdir -p $@

clean:
	rm -rf $(B)
