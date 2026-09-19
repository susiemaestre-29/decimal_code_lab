# Makefile for the Decimal Code Lab cocotb tests (Tiny Tapeout template layout)
#   RTL simulation:        make
#   gate-level simulation: make GATES=yes   (needs gate_level_netlist.v from the GDS flow)

SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
PROJECT_SOURCES = project.v

ifneq ($(GATES),yes)

# RTL simulation
SIM_BUILD = sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))

else

# Gate-level simulation. The netlist is copied in by the GDS workflow as gate_level_netlist.v.
# It is built from IHP SG13G2 cells (sg13g2_*), so the standard-cell models are needed too;
# the wildcard finds them wherever the runner's PDK folder is called.
SIM_BUILD = sim_build/gl
COMPILE_ARGS += -DGL_TEST
COMPILE_ARGS += -DFUNCTIONAL
COMPILE_ARGS += -DSIM

VERILOG_SOURCES += $(wildcard $(PDK_ROOT)/*/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v)
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v

endif

COMPILE_ARGS += -I$(SRC_DIR)
VERILOG_SOURCES += $(PWD)/tb.v

TOPLEVEL = tb

# List test modules (no .py suffix). For cocotb 1.x use MODULE = test instead.
COCOTB_TEST_MODULES = test

include $(shell cocotb-config --makefiles)/Makefile.sim
