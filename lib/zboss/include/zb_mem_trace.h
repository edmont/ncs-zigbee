/* ZBOSS Zigbee software protocol stack
 *
 * Copyright (c) 2012-2020 DSR Corporation, Denver CO, USA.
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
/* PURPOSE: trace into RAM area (memory area that is configured to stay untouched during SoC reset).

   At boot, an app may detect a crash by using SoC system reset reason flags,
   in case flags indicate that crash was the reason of the system reset and
   in case there's a trace in the memory area,
   this trace is a crash dump and may be extracted to send it outside of SoC for further analysis.
*/

#ifndef ZB_MEM_TRACE_H
#define ZB_MEM_TRACE_H 1

#include "zb_common.h"

#ifdef ZB_MEMTRACE

/** @addtogroup  ZB_TRACE
 * @{
 */

/**
 * @brief Init mem trace.
 *
 * After initialization, in case there is data in buffer,
 * memtrace stays locked to provide an ability to get
 * all the trace data before new trace batch overwrites it accidantelly
 */
void zb_memtrace_init(void);

/**
   Check whether the mem trace buffer is empty or not.

   @return ZB_TRUE if trace buffer is empty, ZB_FALSE otherwise
 */
zb_bool_t zb_memtrace_is_empty(void);

/**
   Check whether the mem trace is locked or not.

   @return ZB_TRUE if trace is locked, ZB_FALSE otherwise
 */
zb_bool_t zb_memtrace_is_locked(void);

/**
   Lock memtrace so it starts to drop all new trace batch until unlocked

   @return RET_OK in case the mem trace is inited, RET_ERROR otherwise
 */
zb_ret_t zb_memtrace_lock(void);

/**
   Unlock memtrace to make it be able to receive new trace batch
 */
void zb_memtrace_unlock(void);

/**
   Get data portion from the mem trace buffer.

   @return data length, 0 if buffer is empty
 */
zb_uint_t zb_memtrace_get(zb_uint8_t **buf_p, zb_size_t buf_len);

/**
   Flush the data portion from mem trace buffer.

   @param size - data size
 */
void zb_memtrace_flush(zb_size_t size);

/**
   Reset mem trace buffer, it makes mem trace be automatically unlocked
 */
void zb_memtrace_reset(void);

/**
 * @brief Starts batch put to the trace ring buffer
 * @note This call should begin series of zb_memtrace_put_bytes() calls!
 */
void zb_memtrace_batch_start(zb_uint16_t batch_size);

/**
 * @brief Puts buffer to the internal mem trace buffer
 * @param buf - buffer
 * @param len - buffer length
 */
void zb_memtrace_put_bytes(const zb_uint8_t *buf, zb_short_t len);

/**
 * @brief Finishes using of current data batch
 * @note This call should be the last after series of zb_memtrace_put_bytes() calls!
 */
void zb_memtrace_batch_commit(void);

/*! @} */

#endif  /* ZB_MEMTRACE */

#endif  /* ZB_MEM_TRACE_H */
