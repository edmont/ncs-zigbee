/*
 * Copyright (c) 2021 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#pragma once

#ifdef CONFIG_CHIP
#include <platform/CHIPDeviceLayer.h>
#endif

struct k_timer;

class AppTask {
public:
	static AppTask &Instance()
	{
		static AppTask sAppTask;
		return sAppTask;
	};

#ifdef CONFIG_CHIP
	CHIP_ERROR StartApp();
private:
	CHIP_ERROR Init();
#else
	int StartApp();
private:
	int Init();
#endif
};
