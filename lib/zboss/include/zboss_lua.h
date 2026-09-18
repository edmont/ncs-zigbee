/* ZBOSS Zigbee software protocol stack
 *
 * Copyright (c) 2012-2025 DSR Corporation, Denver CO, USA.
 * www.dsr-zboss.com
 * www.dsr-corporation.com
 * All rights reserved.
 *
 * This is unpublished proprietary source code of DSR Corporation
 * The copyright notice does not evidence any actual or intended
 * publication of such source code.
 *
 * ZBOSS is a registered trademark of Data Storage Research LLC d/b/a DSR
 * Corporation
 *
 * Commercial Usage
 * Licensees holding valid DSR Commercial licenses may use
 * this file in accordance with the DSR Commercial License
 * Agreement provided with the Software or, alternatively, in accordance
 * with the terms contained in a written agreement between you and
 * DSR.
 */

#ifndef ZBOSS_LUA_H
#define ZBOSS_LUA_H

#include "zboss_api.h"
#include "lauxlib.h"

void zb_lua_require_zboss(lua_State* L);

void zb_lua_call_app_main(lua_State* L);
void zb_lua_call_app_signal_handler(lua_State* L, zb_cb_param_t param);

/* TODO: Consider dealing with allocator... */
/* TODO: Deal with standard C funcs that are not implemented really in embedded */
lua_State* zb_lua_newstate(void);

/* TODO: Route lua msgs (e.g. error) to trace */

/* Load lua program from string */
/* This function could be used for link-time inclusion of scripts.
 * Link-time logic can be implemented at application level, yet a reference would be nice. */
void zb_lua_load_from_string(lua_State* L, const char* str);

/* Load lua program from nvram */
/* TODO: consider adding argument that identifies script.
 * What if there are multiple scripts in nvram? */
void zb_lua_load_from_nvram(lua_State* L);

#endif
