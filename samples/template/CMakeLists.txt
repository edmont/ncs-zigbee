#
# Copyright (c) 2024 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project("Zigbee+Matter dual protocol template")

# ============================================================================
# Application Sources and Includes
# ============================================================================

target_include_directories(app PRIVATE
    include
    src
)

target_sources(app PRIVATE
    src/main.c
    src/app_task.cpp
    src/app_task_c.cpp
)

# ============================================================================
# Matter Configuration
# ============================================================================

# Fix mbedTLS API compatibility for NCS 3.1.0's mbedTLS 3.6.4
zephyr_compile_definitions(MBEDTLS_DEPRECATED_REMOVED=1)

# Enable GNU STD support for Matter
include(${ZEPHYR_CONNECTEDHOMEIP_MODULE_DIR}/config/nrfconnect/app/enable-gnu-std.cmake)

# Matter Data Model
include(${ZEPHYR_CONNECTEDHOMEIP_MODULE_DIR}/src/app/chip_data_model.cmake)
include(${ZEPHYR_NRF_MODULE_DIR}/samples/matter/common/cmake/data_model.cmake)

# Matter Common Sources
include(${ZEPHYR_NRF_MODULE_DIR}/samples/matter/common/cmake/source_common.cmake)

# ZAP Configuration
include(${ZEPHYR_NRF_MODULE_DIR}/samples/matter/common/cmake/zap_helpers.cmake)
ncs_get_zap_parent_dir(ZAP_PARENT_DIR)
target_include_directories(app PRIVATE ${ZAP_PARENT_DIR})

# Generate Matter data model
ncs_configure_data_model()
