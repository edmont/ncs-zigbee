/*
 * Copyright (c) 2021 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "app_task_c.h"
#include "app_task.h"

#ifdef CONFIG_CHIP
#include <platform/CHIPDeviceLayer.h>
#endif

int app_task_start(void)
{
#ifdef CONFIG_CHIP
    CHIP_ERROR err = AppTask::Instance().StartApp();
    return (err == CHIP_NO_ERROR) ? 0 : -1;
#else
    return AppTask::Instance().StartApp();
#endif
}
