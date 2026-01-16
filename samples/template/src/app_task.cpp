/*
 * Copyright (c) 2021 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
 */

#include "app_task.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#ifdef CONFIG_CHIP
#include "app/matter_init.h"
#include "app/task_executor.h"
#include "board/board.h"
#include "lib/core/CHIPError.h"
#include "lib/support/CodeUtils.h"
#include <setup_payload/OnboardingCodesUtil.h>
#endif

#ifdef CONFIG_CHIP
LOG_MODULE_DECLARE(app, CONFIG_CHIP_APP_LOG_LEVEL);
#else
LOG_MODULE_REGISTER(app, LOG_LEVEL_INF);
#endif

#ifdef CONFIG_CHIP
using namespace ::chip;
using namespace ::chip::app;
using namespace ::chip::DeviceLayer;

CHIP_ERROR AppTask::Init()
{
	/* Initialize Matter stack */
	ReturnErrorOnFailure(Nrf::Matter::PrepareServer());

	if (!Nrf::GetBoard().Init()) {
		LOG_ERR("User interface initialization failed.");
		return CHIP_ERROR_INCORRECT_STATE;
	}

	/* Register Matter event handler that controls the connectivity status LED based on the captured Matter network
	 * state. */
	ReturnErrorOnFailure(Nrf::Matter::RegisterEventHandler(Nrf::Board::DefaultMatterEventHandler, 0));

	return Nrf::Matter::StartServer();
}

CHIP_ERROR AppTask::StartApp()
{
	ReturnErrorOnFailure(Init());

	while (true) {
		Nrf::DispatchNextTask();
	}

	return CHIP_NO_ERROR;
}

#else
// Non-Matter implementation for Zigbee+Matter dual protocol
int AppTask::Init()
{
	LOG_INF("Initializing Zigbee+Matter dual protocol application");
	return 0;
}

int AppTask::StartApp()
{
	if (Init() != 0) {
		LOG_ERR("Application initialization failed");
		return -1;
	}

	LOG_INF("Zigbee+Matter Template Application started");
	
	while (true) {
		k_sleep(K_MSEC(100));
		// TODO: Add protocol switching logic here
	}
	
	return 0;
}
#endif
