/* ZBOSS Zigbee software protocol stack
*
* Copyright (c) 2012-2023 DSR Corporation, Denver CO, USA.
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
/* PURPOSE: Multi-PAN internal API
*/

#ifndef ZB_MPAN_INTERNAL_API_H
#define ZB_MPAN_INTERNAL_API_H 1

#include "mac_internal.h"
#include "mac_source_matching.h"

#include "zb_mpan_common_api.h"

#ifdef ZB_MUX_SUPPORT_OTHREAD
#include <openthread/tasklet.h>
#endif

/** @addtogroup mpan_internal_api
  * @{
  */

#define ZB_MPAN_MAX_STACKS 2U

/* Set short PAN ID */
#define ZB_MPAN_PENDING_CMD_SET_SHORT_PAN_ID 0U
/* Set short MAC address */
#define ZB_MPAN_PENDING_CMD_SET_SHORT_ADDR 1U
/* Set IEEE address */
#define ZB_MPAN_PENDING_CMD_SET_IEEE_ADDR 2U
/* Set Promiscuous Mode */
#define ZB_MPAN_PENDING_CMD_SET_PROMISCUOUS_MODE 3U
/* Transmit a frame */
#define ZB_MPAN_PENDING_CMD_TX 4U
/* Perform ED Scan operation */
#define ZB_MPAN_PENDING_CMD_ED_SCAN 5U
/* Set TX power value */
#define ZB_MPAN_PENDING_CMD_SET_TX_POWER 6U
/* Set ED Threshold value */
#define ZB_MPAN_PENDING_CMD_SET_ED_THRESHOLD 7U

typedef zb_uint8_t zb_mpan_pending_cmd_t;

/* A bit of magic to simplify SW vs HW vs SW/HW switch for a source matching */
#if defined(ZB_MAC_SOFTWARE_PB_MATCHING)
#define SOFTWARE_PB_MATCHING_PRESENT
#if defined(ZB_MAC_SWITCHABLE_PB_MATCHING)
#define HW_PB_MATCHING_PRESENT
#define IF_SW_MATCHING if (is_mac_source_matching_software())
#define ELSE_SW_MATCHING else
#endif
#else
#define HW_PB_MATCHING_PRESENT
#endif
#ifndef IF_SW_MATCHING
#define IF_SW_MATCHING
#endif
#ifndef ELSE_SW_MATCHING
#define ELSE_SW_MATCHING
#endif

#ifdef HW_PB_MATCHING_PRESENT

/* Source matching: Add Short Address */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_ADD_SHORT_ADDR 0U
/* Source matching: Delete Short Address */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_DELETE_SHORT_ADDR 1U
/* Source matching: Set Pending Bit by Short Address */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_SET_PENDING_BIT_BY_SHORT 2U
/* Source matching: Add IEEE address */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_ADD_IEEE_ADDR 3U
/* Source matching: Delete IEEE address */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_DELETE_IEEE_ADDR 4U
/* Source matching: Table Drop */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_TABLE_DROP 5U
/* Source matching: Table Drop IEEE Addresses */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_TABLE_DROP_IEEE_ADDRS 6U
/* Source matching: Table Drop Short Addresses */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_TABLE_DROP_SHORT_ADDRS 7U

/* Source matching: Invalid Command */
#define ZB_MPAN_PENDING_CMD_SRC_MATCH_INVALID 255U

typedef zb_uint8_t zb_mpan_src_match_pending_cmd_type_t;

#define ZB_MPAN_PENDING_SRC_MATCH_CMDS_QUEUE_SIZE 4U

typedef struct zb_mpan_src_match_pending_cmd_s
{
  zb_mpan_stack_id_t stack_id;
  zb_mpan_src_match_pending_cmd_type_t cmd;

  union
  {
    struct
    {
      zb_uint16_t short_addr;
    } short_addr_req;

    struct
    {
      zb_ieee_addr_t ieee_addr;
    } ieee_addr_req;

    struct
    {
      zb_uint16_t short_addr;
      zb_bool_t bit_value;
    } pending_bit_by_short;

  } cmd_param;
} zb_mpan_src_match_pending_cmd_t;

typedef struct zb_mpan_src_match_pending_cmd_queue_s
{
  zb_mpan_src_match_pending_cmd_t cmd_queue[ZB_MPAN_PENDING_SRC_MATCH_CMDS_QUEUE_SIZE];

  zb_uint8_t cmd_queue_size;
} zb_mpan_src_match_pending_cmd_queue_t;

#endif /* HW_PB_MATCHING_PRESENT */

/**
 * @brief Transmission of frame without Ack request.
 * The frame is successfully sent.
 * The status is also used to indicate successful transmission of outgoing Ack
 *  for received frame.
 */
#define ZB_MPAN_TX_FINISH_TYPE_SENT_NO_ACK 0U
/**
 * @brief Transmission of frame with Ack request.
 * The frame is successfully sent and the Ack is received
 */
#define ZB_MPAN_TX_FINISH_TYPE_SENT_ACKED 1U
/**
 * @brief Transmission of frame with Ack request.
 * The frame is not sent or the MAC Ack is not received
 * See \ref zb_radio_api_tx_status_t enumeration for possible errors
 */
#define ZB_MPAN_TX_FINISH_TYPE_TX_ERROR 2U
/**
 * @brief Transmission of frame with Ack request.
 * The frame is successfully sent and the Enh Ack is received
 */
#define ZB_MPAN_TX_FINISH_TYPE_SENT_ENH_ACKED 3U


typedef zb_uint8_t zb_mpan_tx_finish_type_t;

typedef struct zb_mpan_pending_tx_ctx_s
{
  zb_bufid_t frame_buf;
  zb_uint8_t wait_type;
  zb_time_t tx_at;
} zb_mpan_pending_tx_ctx_t;

typedef struct zb_mpan_pending_ed_scan_s
{
  zb_uint32_t scan_duration_bi;
} zb_mpan_pending_ed_scan_t;


typedef struct zb_mpan_stack_ctx_s
{
  zb_mpan_radio_ed_scan_complete_cb_t ed_scan_cb;
  zb_mpan_radio_generate_enh_ack_cb_t gen_enh_ack_cb;
  zb_mpan_radio_apply_802_15_4_secur_cb_t apply_802_15_4_secur_cb;

  zb_rx_queue_t *rx_queue;

  zb_mpan_radio_state_t radio_state;
  zb_uint8_t operational_page;
  zb_uint8_t operational_channel;

  /* True if stack is operating on temporary channel */
  zb_bool_t is_on_tmp_channel;
  /* True if stack requested switching to some channel, but Multi-PAN
   * waits for the radio unblocking by other stack */
  zb_bool_t pending_radio_channel_switching;
  /* True if stack requested radio resetting when it was transmitting
   * a frame or waiting for Energy Detect result */
  zb_bool_t pending_radio_deinit;

  zb_uint16_t short_pan_id;
  zb_uint16_t short_addr;
  zb_ieee_addr_t ext_mac_addr;
  /* Bitfield to store pending configuration commands
   * (i.e. setting of short pan id, short address,
   * extended MAC address),
   * see \ref zb_mpan_pending_cmd_t enumeration */
  zb_uint16_t pending_conf_commands;

  zb_uint8_t tx_wait_type;
  zb_uint16_t tx_wait_dsn;
  zb_bool_t tx_acked;
  zb_bool_t tx_ack_timeout_expired;

  zb_bool_t tx_int_status_bit;
  zb_bool_t rx_int_status_bit;
  /* TX status for the most recent transmission */
  zb_radio_api_tx_status_t last_tx_status;

  zb_mpan_pending_tx_ctx_t pending_tx;
  zb_mpan_pending_ed_scan_t pending_ed_scan;

  zb_uint8_t last_energy_level;

  zb_int8_t tx_power;

  /* Energy Detect Threshold in dBm (only for OT) */
  zb_int8_t ed_threshold_dbm;

  zb_bool_t promiscuous_mode;

  /* Timestamp of the last transmitted frame */
  zb_time_t last_tx_timestamp;
} zb_mpan_stack_ctx_t;

typedef struct zb_mpan_ctx_s
{
#ifdef ZB_MUX_SUPPORT_OTHREAD
  otInstance *ot_instance;
#ifdef ZB_NSNG
  /* These variables aren't used anywhere except OT monolithic build that supports CSL rx.
     OT monolithic build supported only on NS platform,
      so there is no need to keep these variables on other platforms. */
  zb_time_t csl_rx_start;
  zb_time_t csl_rx_stop;
#endif
#endif /* ZB_MUX_SUPPORT_OTHREAD */

  zb_bool_t is_inited;

  zb_mpan_radio_caps_t radio_caps;

  zb_bool_t is_radio_inited;

  zb_mpan_stack_id_t exclusive_access_stack_id;
  zb_mpan_stack_id_t prev_exclusive_access_stack_id;

  /* Stack id that is blocking LL radio right now
   * (i.e. for TX operation or Energy Detect scan) */
  zb_mpan_stack_id_t blocking_operation_stack_id;
  zb_mpan_stack_id_t prev_blocking_operation_stack_id;

  zb_mpan_radio_state_t working_radio_state;
  zb_uint8_t operational_page;
  zb_uint8_t operational_channel;
  /* Cached tx power value.
     This value returned from zb_mpan_radio_get_tx_power request
      if radio tries to get tx power while radio is busy.  */
  zb_int8_t tx_power_value;

  /* Multi-PAN stores primary (non-temporary) page/channel values after
   * switching to temporary channel.
   * Stack's MAC layers can request these values to implement additional channel access conflict resolution
   * (e.g. OT platform uses the values to return preferred channel mask) */
  zb_uint8_t primary_primary_operational_page;
  zb_uint8_t primary_primary_operational_channel;

  /* True if radio is operating on temporary channel */
  zb_bool_t is_on_tmp_channel;

  /* True if any transmission is in progress.
   * Associated restrictions:
   *    - blocking_operation_stack_id is initialized
   *    - working_radio_state == ZB_MPAN_RADIO_STATE_TX
   * */
  zb_bool_t tx_in_progress;

  /* True if Energy Detect scan is in progress
   * Associated restrictions:
   *    - blocking_operation_stack_id is initialized
   *    - working_radio_state == ZB_MPAN_RADIO_STATE_RX
   * */
  zb_bool_t ed_scan_in_progress;

#ifdef HW_PB_MATCHING_PRESENT
  zb_mpan_src_match_pending_cmd_queue_t pending_src_match;
#endif /* HW_PB_MATCHING_PRESENT */

  zb_mpan_stack_ctx_t stacks_ctx[ZB_MPAN_MAX_STACKS];
} zb_mpan_ctx_t;

#define ZB_MPAN_CTX() s_mpan_ctx
#define ZB_MPAN_STACK_CTX(stack_id) s_mpan_ctx.stacks_ctx[stack_id]

/**
 * @brief Checks if the stack has exclusive access to the radio
 *
 * @param stack_id
 * @return zb_bool_t
 */
zb_bool_t zb_mpan_radio_is_exclusive_access_granted(zb_mpan_stack_id_t stack_id);

/**
 * @brief Checks if there is any pending synchronous command to execute
 *
 * @param stack_id
 * @param pending_cmd
 * @return zb_bool_t
 */
zb_bool_t zb_mpan_is_command_pending(zb_mpan_stack_id_t stack_id, zb_mpan_pending_cmd_t pending_cmd);

/**
 * @brief Checks if the specified stack can start any blocking operation or switch low-level radio state
 *
 * @param stack_id
 * @return zb_bool_t
 */
zb_bool_t zb_mpan_can_stack_use_ll_radio(zb_mpan_stack_id_t stack_id);
/**
 * @brief Checks if the specified stack is performing blocking operation
 *
 * @param stack_id
 * @return zb_bool_t
 */
zb_bool_t zb_mpan_radio_is_blocking_operation_in_progress(zb_mpan_stack_id_t stack_id);

/** @} */

#endif /* ZB_MPAN_INTERNAL_API_H */
