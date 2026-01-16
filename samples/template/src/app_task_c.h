/*
 * Copyright (c) 2021 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Start the application task.
 * 
 * @return 0 on success, negative error code on failure
 */
int app_task_start(void);

#ifdef __cplusplus
}
#endif
