#/* ZBOSS Zigbee software protocol stack
# *
# * Copyright (c) 2012-2024 DSR Corporation, Denver CO, USA.
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

include $(CLEAR_VARS)
LOCAL_MODULE := libcommbdb

SRCS :=
include $(BUILD_HOME)/commissioning/bdb/Makefile

LOCAL_C_INCLUDES := $(COMMON_INCLUDES)
LOCAL_SRC_FILES  := $(addprefix $(BUILD_HOME)/commissioning/bdb/, $(SRCS))
LOCAL_CFLAGS     := $(COMMON_C_FLAGS)

include $(BUILD_STATIC_LIBRARY)
