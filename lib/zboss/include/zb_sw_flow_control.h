/* ZBOSS Zigbee software protocol stack
 *
 * Copyright (c) 2012-2024 DSR Corporation, Denver CO, USA.
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
/* PURPOSE: software flow control implementation using XON/XOFF codes */

#ifndef ZB_SW_FLOW_CONTROL_H
#define ZB_SW_FLOW_CONTROL_H 1

#include "zb_types.h"
#include "zb_errors.h"

#ifdef ZB_MUX_SW_FLOW_CONTROL

#define ZB_SW_FLOW_CONTROL_XON 0x11U
#define ZB_SW_FLOW_CONTROL_XOFF 0x13U

/**
 * Minimum percent of used buffer memory to enable data receiving
 * (e.g. send XON when <= 20% of RX buffer is used)
 */
#define ZB_SW_FLOW_CONTROL_XON_THRESHOLD_PERCENT_DEFAULT 20U
/**
 * Maximum percent of used buffer memory to disable data receiving
 * (e.g. send XOFF when >= 80% of RX buffer is used)
 */
#define ZB_SW_FLOW_CONTROL_XOFF_THRESHOLD_PERCENT_DEFAULT 80U

#define ZB_SW_FLOW_CONTROL_CHECK_XON_THRESHOLD(used_buffer_size, total_buffer_size) \
  ((used_buffer_size) <= ((total_buffer_size) * ZB_SW_FLOW_CONTROL_XON_THRESHOLD_PERCENT_DEFAULT / 100U))

#define ZB_SW_FLOW_CONTROL_CHECK_XON_THRESHOLD_RB(rb_ptr) \
  ZB_SW_FLOW_CONTROL_CHECK_XON_THRESHOLD(                \
    ZB_RING_BUFFER_USED_SPACE(rb_ptr),                    \
    ZB_RING_BUFFER_CAPACITY(rb_ptr))

#define ZB_SW_FLOW_CONTROL_CHECK_XOFF_THRESHOLD(used_buffer_size, total_buffer_size) \
  (used_buffer_size >= (total_buffer_size * ZB_SW_FLOW_CONTROL_XOFF_THRESHOLD_PERCENT_DEFAULT / 100U))

#define ZB_SW_FLOW_CONTROL_CHECK_XOFF_THRESHOLD_RB(rb_ptr) \
  ZB_SW_FLOW_CONTROL_CHECK_XOFF_THRESHOLD(                \
    ZB_RING_BUFFER_USED_SPACE(rb_ptr),                    \
    ZB_RING_BUFFER_CAPACITY(rb_ptr))


typedef zb_ret_t (*zb_sw_flow_control_send_cb_t)(zb_uint8_t byte);


typedef struct zb_sw_flow_control_ctx_s
{
  /* ZB_TRUE by default or if XON is received,
   * ZB_FALSE if XOFF is received */
  zb_bool_t tx_on;

  /* ZB_TRUE by default or if XON is sent,
   * ZB_FALSE is XOFF is pending or is sent */
  zb_bool_t rx_on;

  /**
   * Callback to send raw data.
   * The callback is needed to allow different transports to use
   * the flow control feature.
   */
  zb_sw_flow_control_send_cb_t data_send_cb;
} zb_sw_flow_control_ctx_t;


zb_ret_t zb_sw_flow_control_init(
  zb_sw_flow_control_ctx_t *fc_ctx,
  zb_sw_flow_control_send_cb_t data_send_cb);


zb_bool_t zb_sw_flow_control_process_control_byte(
  zb_sw_flow_control_ctx_t *fc_ctx,
  zb_uint8_t byte);


zb_ret_t zb_sw_flow_control_enable_rx(zb_sw_flow_control_ctx_t *fc_ctx, zb_bool_t enable);


zb_ret_t zb_sw_flow_control_enable_tx(zb_sw_flow_control_ctx_t *fc_ctx, zb_bool_t enable);


zb_uint16_t zb_sw_flow_control_filter_data_buffer(
  zb_sw_flow_control_ctx_t *fc_ctx,
  zb_uint8_t *buf,
  zb_uint16_t buf_size);

#endif /* ZB_MUX_SW_FLOW_CONTROL */

#endif /* ZB_SW_FLOW_CONTROL_H */
