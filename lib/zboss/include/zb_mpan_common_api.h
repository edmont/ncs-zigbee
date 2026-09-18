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
/* PURPOSE: Multi-PAN MAC Common API
*/

#ifndef ZB_MPAN_COMMON_API_H
#define ZB_MPAN_COMMON_API_H 1

#include "zb_ll_radio_api.h"

#ifdef ZB_MUX_SUPPORT_OTHREAD
#include <openthread/ncp.h>
#include <openthread/tasklet.h>
#endif /* ZB_MUX_SUPPORT_OTHREAD */

/** @addtogroup mpan_api
  * @{
  */

/**
 * Some notes about Multi-PAN design.
 *  - The key concepts:
 *    - Multi-PAN layer provides APIs that allows several stacks use the same LL radio
 *      simultaneously.
 *    - The stacks are unaware of each other.
 *      Multi-PAN layer resolves conflicts of concurrent access itself.
 *    - Some operations (frame transmission, Energy Detect scan) can block the radio.
 *      It means that the stack that initiated the operation receives dedicated access to
 *      the radio for the operation time. Other stacks can not use the radio when it is blocked.
 *    - Multi-PAN is designed as a state machine.
 *      It stores current state of each stack and global state of LL radio.
 *      When stack changes its state (i.e. sets TX power or starts to transmit a frame),
 *      Multi-PAN can switch LL radio state immediately if the radio is not blocked or delay the operation
 *      until its unlocking.
 *    - Most of radio functions are asynchronous, they do not wait for operation result and returns immediately.
 *      Operation result can be checked by paired functions
 *      (i.e. zb_mpan_radio_transmit_frame() / zb_mpan_radio_is_last_tx_acked() / zb_mpan_radio_is_ack_timeout() )
 */

/**
 * Multi-PAN integration with platform OSIF layer
 *  - The key concepts:
 *    - Generally, the Multi-PAN layer doesn't depend of specific platform features.
 *      Multi-PAN uses special zb_radio_api_* functions to interact with LL radio.
 *      Platform doesn't directly updates internal Multi-PAN contexts, but
 *      can call Multi-PAN functions/callbacks to notify it about events or operations results.
 *  - Integration notes and requirements;
 *    - Platform should implement zb_radio_api_* functions from `zb_ll_radio_api.h`
 *    - Platform should allow to use different IEEE, short MAC address and short PAN ID per stack.
 *    - In case of hardware Source Matching, platform should allow to distinguish table entries by stack number.
 *    - Platform should add FCS to outgoing frames itself.
 *    - `zb_mpan_radio_set_ack_received` should be called on Immediate Ack receiving.
 *      `zb_mpan_radio_get_stack_waiting_for_ack` can be called
 *       to get id of stack that is waiting Ack by sequence number.
 *    - Platform should use appropriate frame version for outgoing Acks.
 *      `zb_mpan_radio_get_ack_frame_version` can be called to get Ack frame version by stack id.
 *    - `ed_scan_complete` callback should be called when Energy Detect scan is completed.
 *    - `buf_alloc` callback should be called to request buffer to store incoming frame.
 *    - `buf_free` callback should be called to free buffer allocated by `buf_alloc`
 *    - `rx_ind` callback should be called to pass incoming frame to Multi-PAN for further processing.
 *    - `tx_complete` callback should be called to notify Multi-PAN about transmission state.
 *      `ZB_RADIO_API_TX_STATUS_NO_ACK` should be used only when `ZB_MAC_AUTO_ACK_RECV` is defined.
 *    - Platform should not directly set "interrupts status bits" (i.e. TX_INT_STATUS_BIT, RX_INT_STATUS_BIT, TRANS_INT) and
 *      should not directly update stacks contexts ( i.e. MAC_CTX() ).
 */

/**
 * @brief Invalid MAC Sequence Number value
 */
#define ZB_MPAN_INVALID_DSN ZB_MAC_INVALID_DSN

#define ZB_MPAN_RADIO_CAP_ACK_TIMEOUT 0U
#define ZB_MPAN_RADIO_CAP_TX_CSMA_BACKOFF 1U
#define ZB_MPAN_RADIO_CAP_ENERGY_SCAN 2U
#define ZB_MPAN_RADIO_CAP_SLEEP_TX_WITH_CSMA 3U
#define ZB_MPAN_RADIO_CAP_TX_SECURITY 4U
#define ZB_MPAN_RADIO_CAP_TX_AT_TIME 5U
#define ZB_MPAN_RADIO_CAP_RX_AT_TIME 6U

/**
 * @brief Bitmap with low-level radio capabilities
 */
typedef zb_uint16_t zb_mpan_radio_caps_t;

/**
 * @brief Disabled radio state
 */
#define ZB_MPAN_RADIO_STATE_DISABLED 0
/**
 * @brief Receiving radio state
 */
#define ZB_MPAN_RADIO_STATE_RX 1
/**
 * @brief Transmitting radio state
 */
#define ZB_MPAN_RADIO_STATE_TX 2
/**
 * @brief Sleeping radio state
 */
#define ZB_MPAN_RADIO_STATE_SLEEPING 3

/**
 * @brief Multi-PAN radio state.
 * The enumeration is used to store both individual stacks states and
 * actual low-level radio state
 */
typedef zb_uint8_t zb_mpan_radio_state_t;

/**
 * @brief Callback that provides Energy Detect scan result
 * to the stack.
 *
 * @param status Energy Detect scan status
 * @param raw_energy_level raw energy level in [0, 255] range
 */
typedef void (*zb_mpan_radio_ed_scan_complete_cb_t)(zb_ret_t status, zb_uint8_t raw_energy_level);

/**
 * @brief Generates enh-ack using rx buffer or applies security to already formed enh-ack.
 *
 *
 * @param rx_buffer [in] buffer with received frame.
 * @param len length of received buffer.
 * @param frame_param [in] received frame parameters.
 * @param enh_ack [in|out] pointer to enhanced ack buffer.
 * @param enh_ack_len [in|out] pointer to enhanced ack buffer length.
 *
 * @return zb_bool_t ZB_TRUE if enh-ack has been successfully generated.
 *                   ZB_FALSE - otherwise.
 */
typedef zb_bool_t (*zb_mpan_radio_generate_enh_ack_cb_t)(zb_uint8_t *rx_buffer, zb_uint8_t len, zb_radio_api_frame_param_t *frame_param, zb_uint8_t **enh_ack, zb_uint8_t *enh_ack_len);

/**
 * @brief Applies 802.15.4 security to a valid 802.15.4 frame.
 *
 * @param rx_buffer buffer that contains frame to which security should be applied (in place).
 * @param len       buffer length
 * @param frame_param frame parameters (at least, stack_id should be provided)
 *
 * @return zb_bool_t ZB_TRUE if security has been successfully applied to rx_buffer.
 *                   ZB_FALSE otherwise (e.g. if frame_security bit hasn't been set in MHR).
 */
typedef zb_bool_t (*zb_mpan_radio_apply_802_15_4_secur_cb_t)(zb_uint8_t *rx_buffer, zb_uint8_t len, zb_radio_api_frame_param_t *frame_param);

typedef struct zb_mpan_radio_callbacks_s
{
  zb_mpan_radio_ed_scan_complete_cb_t ed_scan_cb;
  zb_mpan_radio_generate_enh_ack_cb_t gen_enh_ack_cb;
  zb_mpan_radio_apply_802_15_4_secur_cb_t apply_802_15_4_secur_cb;
} zb_mpan_radio_callbacks_t;

/* Multi-PAN layer configuration API */

/**
 * @brief Initializes Multi-PAN layer and its internal contexts
 *  - Should be called once before stacks initialization.
 *  - All other Multi-PAN functions must not be called before this function.
 *
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_layer_init(void);

/* Radio configuration API */

/**
 * @brief Initializes stack's radio
 *  - Should be called once during stacks initialization.
 *  - All other Multi-PAN functions with zb_mpan_stack_id_t parameter
 *    must not be called before this function.
 *
 * @param stack_id stack id
 * @param callbacks pointer to structure that contains callbacks
 *                   that will be called from mpan layer
 * @param mac_rx_queue mac rx queue used to process incoming frames by abstract platform (e.g. OT).
 *                  Mpan layer stores frames that were received from radio layer in this queue
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_init(
  zb_mpan_stack_id_t stack_id,
  zb_mpan_radio_callbacks_t *callbacks,
  zb_rx_queue_t *mac_rx_queue);

/**
 * @brief De-initializes stack's radio
 * Deinitialization is possible only when both stacks reset working channels,
 * but now deinitialization is disabled for Multi-PAN.
 * Application will be notified instead (see zb_mpan_no_working_channel_event() function
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_deinit(zb_mpan_stack_id_t stack_id);

#ifdef ZB_MUX_SUPPORT_OTHREAD
/**
 * @brief Provides OpenThread instance to Multi-PAN.
 *  - Multi-PAN can use only one OT instance.
 *  - Should be called once between \ref zb_mpan_layer_init() and \ref zb_mpan_radio_init() calls.
 *
 * @param ot_instance OT instance pointer
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_layer_set_ot_instance(otInstance *ot_instance);

/**
 * @brief Returns OpenThread instance from Multi-PAN.
 *
 * @return otInstance* OT instance pointer
 */
otInstance *zb_mpan_layer_get_ot_instance(void);

#ifdef ZB_NSNG
/**
 * @brief Start delayed reception (needed only for CSL, supported only on NS)
 *
 * @param channel_number channel_number to listen on (2.4 GHz)
 * @param start_time     start time in us to start rx
 * @param duration       rx duration in us
 * @return zb_ret_t      result code
 *
 * @note This function should be used ONLY on NS, in monolithic OT build. (For testing purposes)
 */
zb_ret_t zb_mpan_radio_receive_at(zb_uint8_t channel_number,
                                  zb_time_t start_time,
                                  zb_time_t duration);
#endif /* ZB_NSNG */
#endif /* ZB_MUX_SUPPORT_OTHREAD */

/**
 * @brief Returns radio capabilities bitmap for the specified stack.
 *
 * @param stack_id stack id
 * @return zb_mpan_radio_caps_t radio capabilities bitmap
 */
zb_mpan_radio_caps_t zb_mpan_radio_get_capabilities(zb_mpan_stack_id_t stack_id);

/**
 * @brief Checks if the stack's radio is in promiscuous mode
 *
 * @param stack_id stack id
 * @return zb_bool_t ZB_TRUE if the stack's radio is in promiscuous mode
 */
zb_bool_t zb_mpan_radio_get_promiscuous_mode(zb_mpan_stack_id_t stack_id);

/**
 * @brief Enables or disables promiscuous mode for specified stack's radio
 *
 * @param stack_id stack id
 * @param promiscuous_mode promiscuous mode
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_promiscuous_mode(zb_mpan_stack_id_t stack_id, zb_bool_t promiscuous_mode);

/**
 * @brief Sets stack's radio short PAN ID
 *
 * @param stack_id stack id
 * @param pan_id short PAN ID
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_pan_id(zb_mpan_stack_id_t stack_id, zb_uint16_t pan_id);

/**
 * @brief Returns stack's radio short PAN ID
 *
 * @param stack_id stack id
 * @return zb_uint16_t short PAN ID
 */
zb_uint16_t zb_mpan_radio_get_pan_id(zb_mpan_stack_id_t stack_id);

/**
 * @brief Returns radio IEEE address from hardware
 *
 * @param stack_id stack id
 * @param out_ieee_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_get_hw_long_addr(zb_mpan_stack_id_t stack_id, zb_ieee_addr_t ieee_addr);

/**
 * @brief Sets stack's radio IEEE address.
 * Each stack can use own IEEE address.
 *
 * @param stack_id stack id
 * @param ieee_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_ieee_mac_address(zb_mpan_stack_id_t stack_id, const zb_ieee_addr_t ieee_addr);

/**
 * @brief Returns stack's radio IEEE address.
 *
 * @param stack_id stack id
 * @param out_ieee_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_get_ieee_mac_address(zb_mpan_stack_id_t stack_id, zb_ieee_addr_t out_ieee_addr);

/**
 * @brief Sets stack's radio short MAC address
 *
 * @param stack_id stack id
 * @param short_addr short MAC address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_short_address(zb_mpan_stack_id_t stack_id, zb_uint16_t short_addr);

/**
 * @brief Returns stack's radio short MAC address
 *
 * @param stack_id stack id
 * @return zb_uint16_t short address
 */
zb_uint16_t zb_mpan_radio_get_short_address(zb_mpan_stack_id_t stack_id);

/**
 * @brief Sets stack's radio page and channel.
 * The following cases are supported:
 *   1. The new channel is temporary
 *      Just set the channel as is
 *   2. Both channels are invalid, but new channel is valid
 *      Just set the channel as current working channel
 *   3. The other stack has different valid channel
 *      Check that channels are the same or channel_number is invalid and set the channel or return an error
 *   4. Both channels becomes invalid
 *      Prevent radio deinitialization (default behavior) and just notify application
 *
 * @param stack_id stack id
 * @param page_number page number
 * @param channel_number channel number
 * @param is_temporary_channel ZB_TRUE if the channel is temporary
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_page_and_channel(
    zb_mpan_stack_id_t stack_id,
    zb_uint8_t page_number,
    zb_uint8_t channel_number,
    zb_bool_t is_temporary_channel);

/**
 * @brief Returns primary (non-temporary) operational page and channel.
 * Multi-PAN stores primary page and channel values when switching low-level radio on temporary channel.
 *
 * Stack's MAC layers can request these values to implement additional channel access conflict resolution.
 * (e.g. OT platform uses the values to return preferred channel mask)
 *
 * @param[out] out_page_number primary (non-temporary) page
 * @param[out] out_channel_number primary (non-temporary) channel
 */
void zb_mpan_radio_get_primary_operational_page_and_channel(
    zb_uint8_t *out_page_number,
    zb_uint8_t *out_channel_number);

/**
 * @brief Returns current stack's radio page
 *
 * @param stack_id stack id
 * @return zb_uint8_t page number
 */
zb_uint8_t zb_mpan_radio_get_current_page(zb_mpan_stack_id_t stack_id);

/**
 * @brief Returns current stack's radio channel
 *
 * @param stack_id stack id
 * @return zb_uint8_t channel number
 */
zb_uint8_t zb_mpan_radio_get_current_channel(zb_mpan_stack_id_t stack_id);

/**
 * @brief Sets Energy Detect Threshold for LL radio
 * The functions updates the Low-Level radio's threshold immediately
 * if radio is unlocked or delays it until unlocking.
 *
 * @param stack_id stack id
 * @param threshold threshold value in dBm
 * @return zb_ret_t status code
 */
zb_ret_t zb_mpan_radio_set_energy_detect_threshold(zb_mpan_stack_id_t stack_id, zb_int8_t threshold_dbm);

/**
 * @brief Gets Energy Detect Threshold from LL radio
 * If the radio is blocked and threshold updating is delayed, the function
 * returns current value directly from LL radio.
 *
 * @param stack_id stack id
 * @param out_threshold threshold value in dBm
 * @return zb_ret_t status code
 */
zb_ret_t zb_mpan_radio_get_energy_detect_threshold(zb_mpan_stack_id_t stack_id, zb_int8_t *out_threshold_dbm);

/**
 * @brief Returns current time from the transceiver.
 *
 * @param stack_id stack id
 * @return zb_time_t current time
 */
zb_time_t zb_mpan_radio_get_time(zb_mpan_stack_id_t stack_id);


/* Radio state API */

/**
 * @brief Enables stack radio (switches its state to sleeping) or disables it.
 *  - The following states transitions are allowed:
 *    - disabled -> sleeping
 *    - sleeping -> disabled
 *    - RX -> disabled
 *
 * @param stack_id stack id
 * @param enable enable status
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_enable(zb_mpan_stack_id_t stack_id, zb_bool_t enable);

/**
 * @brief Checks if the stack radio is enabled
 *
 * @param stack_id stack id
 * @return zb_bool_t ZB_TRUE if the radio is enabled
 */
zb_bool_t zb_mpan_radio_is_enabled(zb_mpan_stack_id_t stack_id);

/**
 * @brief Switches stack's radio state to sleeping
 *  - The function allows only RX -> sleeping transition.
 *  - Disabled -> sleeping transition can be triggered only by \ref zb_mpan_radio_enable()
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_sleep(zb_mpan_stack_id_t stack_id);

/**
 * @brief Enables or disables RX on stack's radio.
 * Internal implementation switches stack's radio state to RX or sleeping.
 *  - The following states transitions are allowed:
 *    - sleeping -> RX
 *    - RX -> sleeping
 *
 * @param stack_id stack id
 * @param is_rx_on ZB_TRUE to enable RX
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_background_rx_on_off(zb_mpan_stack_id_t stack_id, zb_bool_t is_rx_on);

/**
 * @brief Checks if the stack's radio enables and can receive new frames
 * Note that the function returns ZB_TRUE if the radio is in TX state.
 *
 * @param stack_id stack id
 * @return zb_bool_t ZB_TRUE if the radio can receive new frames
 */
zb_bool_t zb_mpan_radio_get_background_rx_on_off(zb_mpan_stack_id_t stack_id);

/**
 * @brief Returns current stack's radio state
 *
 * @param stack_id stack id
 * @return zb_mpan_radio_state_t radio state
 */
zb_mpan_radio_state_t zb_mpan_radio_get_state(zb_mpan_stack_id_t stack_id);

/* Pending bits API */

/**
 * @brief Adds the short MAC address to Source Match table
 *
 * @param stack_id stack id
 * @param short_addr short MAC address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_add_short_addr(
  zb_mpan_stack_id_t stack_id,
  zb_uint16_t short_addr);

/**
 * @brief Deletes the short MAC address from Source Match table
 *
 * @param stack_id stack id
 * @param short_addr short MAC address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_delete_short_addr(
  zb_mpan_stack_id_t stack_id,
  zb_uint16_t short_addr);

/**
 * @brief Sets pending bit value for the specified short MAC address
 * The function is intended for ZB stack.
 *
 * @param short_addr short MAC address
 * @param bit_value pending bit value
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_short_set_pending_bit(
    zb_uint16_t short_addr,
    zb_bool_t bit_value);

/**
 * @brief Adds the IEEE address to Source Match table
 * The function is intended for OT stack.
 *
 * @param ieee_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_add_ieee_addr(
  const zb_ieee_addr_t ieee_addr);

/**
 * @brief Deletes the IEEE address from Source Match table
 *
 * @param ieee_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_delete_ieee_addr(
  const zb_ieee_addr_t ieee_addr);

/**
 * @brief Clears Source Match table of specified stack
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_table_drop(zb_mpan_stack_id_t stack_id);

/**
 * @brief Removes all IEEE addresses from Source Match table
 *
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_table_drop_ieee_addrs(void);

/**
 * @brief Removes all short MAC addresses from Source Match table
 * for specified stack
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_src_match_table_drop_short_addrs(zb_mpan_stack_id_t stack_id);

/**
 * @brief Tries to find Source Match table entry
 * by stack id and short MAC address
 *
 * @param stack_id stack id
 * @param short_addr short address
 * @return zb_int_t address reference
 */
zb_int_t zb_mpan_radio_src_match_seek_short_addr(
  zb_mpan_stack_id_t stack_id,
  zb_uint16_t short_addr);

/**
 * @brief Tries to find Source Match table entry
 * by IEEE address
 *
 * @param ieee_addr IEEE address
 * @return zb_int_t result code
 */
zb_int_t zb_mpan_radio_src_match_seek_ieee_addr(
  const zb_ieee_addr_t ieee_addr);

/* Energy Scan API  */

/**
 * @brief Starts Energy Scan for the specified stack's
 * The function starts Energy Scan if radio is unlocked or delays it until unlocking.
 *
 * @param stack_id stack id
 * @param scan_duration_bi scan duration in Beacon intervals
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_start_energy_scan(zb_mpan_stack_id_t stack_id, zb_uint32_t scan_duration_bi);

/**
 * @brief Stops Energy Scan if it is in progress and gets the most recent Energy Level value
 * in units in range [0, 255]
 *
 * @param stack_id stack id
 * @param[out] out_energy_measurement Energy Level value
 * @return zb_ret_t
 */
zb_ret_t zb_mpan_radio_get_energy_measurement(zb_mpan_stack_id_t stack_id, zb_uint8_t *out_energy_measurement);

/**
 * @brief Measures RSSI in synchronous mode and returns its value or error code.
 *
 * @param stack_id stack id
 * @param[out] out_rssi_dbm out RSSI value in dBm
 * @return zb_ret_t RET_OK or error code
 */
zb_ret_t zb_mpan_radio_measure_rssi_sync(zb_mpan_stack_id_t stack_id, zb_int8_t *out_rssi_dbm);

/**
 * @brief Sets TX power for the LL radio.
 * The function sets the value if radio is unlocked or delays it until unlocking.
 * If stacks set different values, LL radio will use the maximum one.
 *
 * @param stack_id stack id
 * @param tx_power TX power value in dBm
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_tx_power(zb_mpan_stack_id_t stack_id, zb_int8_t tx_power);

/**
 * @brief Returns the current TX power for the stack's radio.
 *
 * @param stack_id stack id
 * @param[out] out_tx_power TX power value in dBm
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_get_tx_power(zb_mpan_stack_id_t stack_id, zb_int8_t *out_tx_power);

/* Radio operations API */

/**
 * @brief Transmits a frame
 *
 * The function will not free the frame buffer, but may block it until the TX is done.
 * Do not use or deallocate the buffer between calling the function and TX done indication.
 *
 * For frames with Ack request Multi-PAN will keep TX state until Ack is received or timeout
 * is expired. There is no TX -> Ack-RX transition.
 *
 * The function may be used to send outgoing Ack for received data frame (see \ref zb_mac_send_ack).
 * The stack must not send new frames between receiving new packet and sending outgoing Ack for that packet.
 *
 * @param stack_id stack id which issued the frame
 * @param frame_buf buffer with the frame
 * @param wait_type TX waiting type (no wait, waiting for Ack, CSMA/CA waiting, CSL)
 * @param tx_at scheduled TX time
 * @return zb_ret_t sending status
 */
zb_ret_t zb_mpan_radio_transmit_frame(
    zb_mpan_stack_id_t stack_id,
    zb_bufid_t frame_buf,
    zb_uint8_t wait_type,
    zb_time_t tx_at);

/**
 * @brief Checks if transceiver received Ack for the last transmitted frame
 *
 * @param stack_id stack id
 */
zb_bool_t zb_mpan_radio_is_last_tx_acked(zb_mpan_stack_id_t stack_id);

/**
 * @brief Checks if MAC Ack receiving timeout is expired for the most recent transmission
 *
 * @param stack_id stack id
 */
zb_bool_t zb_mpan_radio_is_ack_timeout(zb_mpan_stack_id_t stack_id);

/**
 * @brief Clears acknowledging status for the last transmitted frame
 *
 * @param stack_id stack id
 */
void zb_mpan_radio_clear_ack_waiting_ctx(zb_mpan_stack_id_t stack_id);

/**
 * @brief Gets TX status for the most recent transmission
 *
 * @param stack_id stack id
 * @return zb_radio_api_tx_status_t TX status
 */
zb_radio_api_tx_status_t zb_mpan_radio_get_tx_status(zb_mpan_stack_id_t stack_id);

/**
 * @brief Checks if Multi-PAN layer allows blocking IO iteration
 * (returns false when there are some OT tasklets)
 *
 * @return zb_bool_t permission status of IO iterations
 */
zb_bool_t zb_mpan_radio_allow_blocking_io_iteration(void);

/**
 * @brief Handles received radio packets in a main loop, out of ISR context
 */
void zb_mpan_radio_io_iteration(void);

/* Events API */

/**
 * @brief Notifies application that there are no working channel
 * (both stacks reset their working channel)
 */
ZB_WEAK_PRE void ZB_WEAK zb_mpan_no_working_channel_event(void);


/* Internal Multi-PAN functions */

/**
 * @brief Switches stack's radio state from current state to requested state.
 *  - Switches stack's radio state if the transition is allowed
 *    or returns error code if the transition is temporarily blocked.
 *  - Triggers assertion error if the transition is invalid.
 *
 * @param stack_id stack id
 * @param state requested radio state
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_set_stack_state(zb_mpan_stack_id_t stack_id, zb_mpan_radio_state_t state);

/**
 * @brief Switches stack's radio state to RX
 *  - The following states transitions are allowed:
 *    - sleeping -> RX
 *    - TX -> RX
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_start_rx_mode(zb_mpan_stack_id_t stack_id);

/**
 * @brief Switches stack's radio state to TX
 *  - The following states transitions are allowed:
 *    - RX -> TX
 *    - sleeping -> TX
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t zb_mpan_radio_start_tx_mode(zb_mpan_stack_id_t stack_id);

/**
 * @brief Returns stack id that is transmitting a frame or
 * and ZB_MPAN_STACK_ID_UNDEFINED.
 *
 * @return zb_mpan_stack_id_t stack id that is transmitting now.
 */
zb_mpan_stack_id_t zb_mpan_radio_get_transmitting_stack(void);

/* Interrupts API */

/**
 * @brief Sets data frame TX interrupt status bit for the specified stack.
 * TX interrupt happens right after frame transmission (without waiting for Ack)
 *
 * @param stack_id stack id
 */
void zb_mpan_radio_set_data_frame_tx_int_bit(zb_mpan_stack_id_t stack_id);

/**
 * @brief Clears data frame TX interrupt status bit for the specified stack.
 * TX interrupt happens right after frame transmission (without waiting for Ack)
 *
 * @param stack_id stack id
 */
void zb_mpan_radio_clear_tx_int_status_bit(zb_mpan_stack_id_t stack_id);

/**
 * @brief Returns data frame TX interrupt status bit for the specified stack.
 * TX interrupt happens right after frame transmission (without waiting for Ack)
 *
 * @param stack_id stack id
 * @return zb_bool_t bit value
 */
zb_bool_t zb_mpan_radio_get_tx_int_status_bit(zb_mpan_stack_id_t stack_id);

/**
 * @brief Sets data frame RX interrupt status bit for the specified stack.
 * RX interrupt happens right after frame receiving
 * (order of RX interrupt and outgoing Ack sending is not specified).
 *
 * @param stack_id stack id
 */
void zb_mpan_radio_frame_set_rx_int_status_bit(zb_mpan_stack_id_t stack_id);

/**
 * @brief Clears data frame RX interrupt status bit for the specified stack.
 * RX interrupt happens right after frame receiving
 * (order of RX interrupt and outgoing Ack sending is not specified).
 *
 * @param stack_id stack id
 */
void zb_mpan_radio_clear_rx_int_status_bit(zb_mpan_stack_id_t stack_id);

/**
 * @brief Returns data frame RX interrupt status bit for the specified stack.
 * RX interrupt happens right after frame receiving
 * (order of RX interrupt and outgoing Ack sending is not specified).
 *
 * @param stack_id stack id
 * @return zb_bool_t status bit value
 */
zb_bool_t zb_mpan_radio_get_rx_int_status_bit(zb_mpan_stack_id_t stack_id);

/**
 * @brief Checks if Immediate Ack can be sent for the specified frame
 *
 * @param frame_buffer frame data
 * @return zb_bool_t ZB_TRUE if LL radio can send Immediate Ack
 */
zb_bool_t zb_mpan_can_imm_ack(zb_uint8_t *frame_buffer);

/**
 * @brief Checks if any Multi-PAN stack is waiting for Ack
 * with specified DSN and returns the stack id
 *
 * @param ack_dsn Ack DSN
 * @return zb_mpan_stack_id_t id of the stack that waits for the Ack
 */
zb_mpan_stack_id_t zb_mpan_radio_get_stack_waiting_for_ack(zb_uint8_t ack_dsn);

/**
 * @brief Indicates that Multi-MAC stack received Ack for waiting frame
 *
 * @param stack_id stack id
 * @param ack_dsn Ack DSN value
 * @param ack_pending_bit Ack pending bit value
 * @param ack_version Ack frame version
 */
void zb_mpan_radio_set_ack_received(zb_mpan_stack_id_t stack_id, zb_uint8_t ack_dsn, zb_bool_t ack_pending_bit, zb_uint8_t ack_version);

/**
 * @brief Indicates that Multi-MAC stack received Ack timeout error
 *
 * @param stack_id stack id with Ack timeout
 */
void zb_mpan_radio_set_ack_timeout_expired(zb_cb_param_t stack_id);

/**
 * @brief Checks which stack (ZB, OT or both) may accept a frame pointed by frame_payload_ptr,
 *          then puts stack_id into `frame_param`.
 *           To see a list of supported stack_id values @ref mpan_stack_id.
 *
 * @param frame_payload_ptr [in]  pointer to MAC header followed by payload.
 *                                This buffer won't be modified.
 * @param frame_param       [in/out] pointer frame parameters (not NULL).
 *                                Only stack_id field will be changed.
 *
 * @return zb_bool_t true  if ZB or OT stack (or both) may accept frame pointed.
 *                         Also, stack_id value will be set to corresponding value.
 *                   false if frame can't be accepted by any stack.
 *                         In this case, stack_id value will be also set to ZB_MPAN_STACK_ID_UNDEFINED.
 */
zb_bool_t zb_mpan_radio_get_stack_id_by_frame_ptr(const zb_uint8_t *frame_payload_ptr, zb_radio_api_frame_param_t *frame_param);

/**
 * @brief Returns frame version of IEEE 802.15.4 Ack for specified stack
 *
 * @param stack_id stack id
 * @return zb_uint8_t frame version (see @mac_frame_version)
 */
zb_uint8_t zb_mpan_radio_get_ack_frame_version(zb_mpan_stack_id_t stack_id);

/** @} */

#if defined ZB_MULTIPAN && (defined(ZB_MAC_SWITCHABLE_PB_MATCHING) || defined(ZB_MAC_SOFTWARE_PB_MATCHING))

/** @addtogroup mpan_sw_matching
  * @{
  */

/**
 * @brief Initialize software Source Match table
 *
 */
void mpan_sw_src_match_init(void);

/**
 * @brief Calculates pending bit value for the specified frame
 *
 * @param buf frame buffer
 * @param frame_param frame parameter
 * @return zb_bool_t pending bit value
 */
zb_bool_t mpan_sw_src_match_calc_pend_bit(zb_uint8_t *buf, zb_radio_api_frame_param_t *frame_param);

/**
 * @brief Adds the short MAC address to Source Match table
 *
 * @param stack_id stack id
 * @param short_addr short MAC address
 * @param[out] idxp index of updated table entry
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_add_short_addr(zb_mpan_stack_id_t stack_id, zb_uint16_t short_addr, zb_int_t *idxp);

/**
 * @brief Deletes the short MAC address from Source Match table
 *
 * @param stack_id stack id
 * @param short_addr short MAC address
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_delete_short_addr(zb_mpan_stack_id_t stack_id, zb_uint16_t short_addr);

/**
 * @brief Sets pending bit value for the specified short MAC address
 *
 * @param short_addr short MAC address
 * @param bit_value pending bit value
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_set_pending_bit(zb_uint16_t short_addr, zb_uint8_t bit_value);

/**
 * @brief Returns pending bit value from specified Source Match table entry
 *
 * @param index table entry index
 * @return zb_bool_t pending bit value
 */
zb_bool_t mpan_sw_src_match_test_zb_pending_bit(zb_int_t index);

/**
 * @brief Adds the IEEE address to Source Match table
 *
 * @param long_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_add_ieee_addr(const zb_ieee_addr_t long_addr);

/**
 * @brief Deletes the IEEE address from Source Match table
 *
 * @param long_addr IEEE address
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_delete_ieee_addr(const zb_ieee_addr_t long_addr);

/**
 * @brief Clears the Source Match table entries for the specified stack
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_drop(zb_mpan_stack_id_t stack_id);

/**
 * @brief Deletes IEEE addresses from Source Match table
 *
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_drop_ieee(void);

/**
 * @brief Deletes short MAC addresses from Source Match table for the specified stack
 *
 * @param stack_id stack id
 * @return zb_ret_t result code
 */
zb_ret_t mpan_sw_src_match_drop_short(zb_mpan_stack_id_t stack_id);

/**
 * @brief Tries to find Source Match table entry
 * by stack id and short MAC address
 *
 * @param stack_id stack id
 * @param short_addr short MAC address
 * @return zb_int_t address reference
 */
zb_int_t mpan_sw_src_match_seek_short_addr(zb_mpan_stack_id_t stack_id, zb_uint16_t short_addr);

/**
 * @brief Tries to find Source Match table entry
 * by IEEE address
 *
 * @param long_addr IEEE address
 * @return zb_int_t address reference
 */
zb_int_t mpan_sw_src_match_seek_ieee_addr(const zb_ieee_addr_t long_addr);

/**
 * @brief Checks if it is needed to use source matching for the specified frame
 *
 * @param cmd_ptr frame data
 * @param frame_param frame parameter
 * @return zb_bool_t ZB_TRUE if source matching is needed
 */
zb_bool_t zb_mpan_need_src_match(zb_uint8_t *cmd_ptr, zb_radio_api_frame_param_t *frame_param);

/** @} */
#endif

#endif /* ZB_MPAN_COMMON_API_H */
