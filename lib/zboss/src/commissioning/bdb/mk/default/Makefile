#/* ZBOSS Zigbee software protocol stack
# *
# * Copyright (c) 2012-2020 DSR Corporation, Denver CO, USA.
# * www.dsr-zboss.com
# * www.dsr-corporation.com
# * All rights reserved.
# *
# * This is unpublished proprietary source code of DSR Corporation
# * The copyright notice does not evidence any actual or intended
# * publication of such source code.
# *
# * ZBOSS is a registered trademark of Data Storage Research LLC d/b/a DSR
# * Corporation
# *
# * Commercial Usage
# * Licensees holding valid DSR Commercial licenses may use
# * this file in accordance with the DSR Commercial License
# * Agreement provided with the Software or, alternatively, in accordance
# * with the terms contained in a written agreement between you and
# * DSR.
#
# PURPOSE:

BUILD_HOME ?= ../..
include $(BUILD_HOME)/Options

ifneq ($(NOZigbee),y)

SRCS = zdo_commissioning_bdb.c \
       zdo_commissioning_bdb_formation.c \
       bdb_finding_binding.c \
       bdb_touchlink.c \
       bdb_tc_connectivity.c \
       bdb_preinst_nwk.c

all: $(COMM_BDB_LIB) $(COMM_BDB_LIB_ZC) $(COMM_BDB_LIB_ZR) $(COMM_BDB_LIB_ED)

$(COMM_BDB_LIB) : $(OBJS)
	$(MAKE_LIB)

$(COMM_BDB_LIB_ED) : $(OBJS_ED)
	$(MAKE_LIB)

$(COMM_BDB_LIB_ZC) : $(OBJS_ZC)
	$(MAKE_LIB)

$(COMM_BDB_LIB_ZR) : $(OBJS_ZR)
	$(MAKE_LIB)
else

all:

endif
