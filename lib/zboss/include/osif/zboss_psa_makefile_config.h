/*
 * Copyright (c) 2025 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#ifndef ZBOSS_PSA_MAKEFILE_CONFIG_H
#define ZBOSS_PSA_MAKEFILE_CONFIG_H

/*
 * Wrapper for the Makefile build of zb_psa_crypto.c. Includes the Zephyr child
 * image PSA config, then clears PSA_WANT_GENERATE_RANDOM so Oberon header
 * checks pass without the full Cracen DRBG driver graph (RNG is linked via the
 * application nRF Security build at runtime).
 */
#include "nrf-psa-crypto-config.h"
#undef PSA_WANT_GENERATE_RANDOM

#endif /* ZBOSS_PSA_MAKEFILE_CONFIG_H */
