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
/* PURPOSE: Low-Level Radio API
*/

#ifndef ZB_MAP_LL_RADIO_API_H
#define ZB_MAP_LL_RADIO_API_H 1

/* A bit of empty legacy */
#define ZB_TRANSCEIVER_SET_COORD_SHORT_ADDR(x)
#define ZB_TRANSCEIVER_SET_COORD_EXT_ADDR(x)

/* Bunch of legacy from UZ2400 (ZBOSS 1.0) */
#define ZB_MAC_GET_TRANS_INT_FLAG() 0
#define ZB_MAC_READ_INT_STATUS_REG()
#define ZB_MAC_CLEAR_TRANS_INT()
#define ZB_MAC_TRANS_CLEAR_PENDING_BIT()
#define ZB_MAC_TRANS_SET_PENDING_BIT()
#define ZB_TRANS_CUT_SPECIFIC_HEADER(x)

#ifdef ZB_MULTIPAN
#define ZB_TRANSCEIVER_INIT_RADIO() zb_mpan_radio_init(ZB_MPAN_STACK_ID_ZB, NULL, &MAC_CTX().mac_rx_queue)
#define ZB_TRANSCEIVER_DEINIT_RADIO() zb_mpan_radio_deinit(ZB_MPAN_STACK_ID_ZB)

#define ZB_TRANSCEIVER_START_GET_RSSI(_scan_duration_bi) zb_mpan_radio_start_energy_scan(ZB_MPAN_STACK_ID_ZB, (_scan_duration_bi))
#define ZB_TRANSCEIVER_START_GET_ENERGY_LEVEL ZB_TRANSCEIVER_START_GET_RSSI
#define ZB_TRANSCEIVER_GET_ENERGY_LEVEL(out_energy_ptr) zb_mpan_radio_get_energy_measurement(ZB_MPAN_STACK_ID_ZB, (out_energy_ptr))

/* Usage of zb_mac_temp_channel_is_set() call here has 2 assumptions:
 *    - zb_mac_temp_channel_set() sets temporary channel PIB value before
 *      calling ZB_TRANSCEIVER_SET_CHANNEL()
 *    - ZB MAC doesn't try to set working channel when temporary channel PIB value is active.
 *
 * Then, temporary channel itself can not be invalid.
 *
 * When ZB stack switches channel back to operational channel and calls ZB_TRANSCEIVER_SET_CHANNEL(),
 * zb_mac_temp_channel_is_set() still continues to return ZB_TRUE.
 * So, additional condition "channel_number != MAC_PIB().phy_current_channel" is needed to check
 * that new channel is previous operational channel. */
#define ZB_TRANSCEIVER_SET_CHANNEL(page, channel_number) \
  zb_mpan_radio_set_page_and_channel(ZB_MPAN_STACK_ID_ZB, (page), (channel_number), \
  (zb_mac_temp_channel_is_set() && channel_number != MAC_PIB().phy_current_channel))

#define ZB_TRANSCEIVER_SET_PROMISCUOUS(promiscuous_mode) zb_mpan_radio_set_promiscuous_mode((promiscuous_mode))
#define ZB_TRANSCEIVER_GET_PROMISCUOUS() zb_mpan_radio_get_promiscuous_mode()

#define ZB_TRANSCEIVER_UPDATE_LONGMAC() zb_mpan_radio_set_ieee_mac_address(ZB_MPAN_STACK_ID_ZB, MAC_PIB().mac_extended_address)
#define ZB_TRANSCEIVER_UPDATE_SHORT_ADDR() zb_mpan_radio_set_short_address(ZB_MPAN_STACK_ID_ZB, MAC_PIB().mac_short_address)

#define ZB_TRANSCEIVER_SET_PAN_ID(pan_id) zb_mpan_radio_set_pan_id(ZB_MPAN_STACK_ID_ZB, (pan_id))
#define ZB_TRANSCEIVER_UPDATE_PAN_ID() zb_mpan_radio_set_pan_id(ZB_MPAN_STACK_ID_ZB, MAC_PIB().mac_pan_id)

/*
Multipan implementation of Source Matching is HW from the MAC HL point of view.
So SW source match logic must not be compiled in, MAC HL must call the multipan logic.
Below the common multipan layer can be SW or HW source matching.
 */
#define ZB_TRANSCEIVER_SRC_MATCH_ADD_SHORT_ADDR(nb_index, short_addr) zb_mpan_radio_src_match_add_short_addr(ZB_MPAN_STACK_ID_ZB, (short_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_DELETE_SHORT_ADDR(nb_index, short_addr) zb_mpan_radio_src_match_delete_short_addr(ZB_MPAN_STACK_ID_ZB, (short_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_SHORT_SET_PENDING_BIT(short_addr, bit_value) zb_mpan_radio_src_match_short_set_pending_bit((short_addr), (bit_value))

#define ZB_TRANSCEIVER_SRC_MATCH_ADD_IEEE_ADDR(nb_index, ieee_addr) zb_mpan_radio_src_match_add_ieee_addr((ieee_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_DELETE_IEEE_ADDR(nb_index, ieee_addr) zb_mpan_radio_src_match_delete_ieee_addr((ieee_addr))

#define ZB_TRANSCEIVER_SRC_MATCH_TBL_DROP() zb_mpan_radio_src_match_table_drop(ZB_MPAN_STACK_ID_ZB)

#define ZB_TRANSCEIVER_SET_RX_ON_OFF(_rx_on) zb_mpan_radio_set_background_rx_on_off(ZB_MPAN_STACK_ID_ZB, (_rx_on))
#define ZB_TRANSCEIVER_GET_RX_ON_OFF() zb_mpan_radio_get_background_rx_on_off(ZB_MPAN_STACK_ID_ZB)

#define ZB_TRANSCEIVER_SET_TX_POWER(new_power) zb_mpan_radio_set_tx_power(ZB_MPAN_STACK_ID_ZB, (new_power))
#define ZB_TRANSCEIVER_GET_TX_POWER(out_power_ptr) zb_mpan_radio_get_tx_power(ZB_MPAN_STACK_ID_ZB, (out_power_ptr))

#define ZB_TRANS_SEND_FRAME(hdr_len, buf, wait_type) \
  ((void)hdr_len, zb_mpan_radio_transmit_frame(ZB_MPAN_STACK_ID_ZB, (buf), (wait_type), 0u))
#define ZB_TRANS_GET_TX_TIMESTAMP() zb_mpan_radio_get_time(ZB_MPAN_STACK_ID_ZB)

#define ZB_TRANS_REPEAT_SEND_FRAME ZB_TRANS_SEND_FRAME
#define ZB_TRANS_SEND_ACK ZB_TRANS_SEND_FRAME

#define ZB_MAC_SET_TX_INT_STATUS_BIT() /* must not be called directly by the radio level */
#define ZB_MAC_CLEAR_TX_INT_STATUS_BIT() zb_mpan_radio_clear_tx_int_status_bit(ZB_MPAN_STACK_ID_ZB)
#define ZB_MAC_GET_TX_INT_STATUS_BIT() zb_mpan_radio_get_tx_int_status_bit(ZB_MPAN_STACK_ID_ZB)

/* RX status set when full data packet is received */

/**
   Set RX data status to 1 - indicate packet receive
 */
#define ZB_MAC_SET_RX_INT_STATUS_BIT() /* must not be called directly by the radio level */

/**
   Clear RX data status
 */
#define ZB_MAC_CLEAR_RX_INT_STATUS_BIT() zb_mpan_radio_clear_rx_int_status_bit(ZB_MPAN_STACK_ID_ZB)

/**
   Get RX data status
 */
#define ZB_MAC_GET_RX_INT_STATUS_BIT() zb_mpan_radio_get_rx_int_status_bit(ZB_MPAN_STACK_ID_ZB)

#define ZB_TRANS_CHECK_CHANNEL_BUSY_ERROR() (zb_mpan_radio_get_tx_status(ZB_MPAN_STACK_ID_ZB) == ZB_RADIO_API_TX_STATUS_CHANNEL_BUSY)
#define ZB_TRANS_CHECK_TX_LBT_TO_ERROR() (zb_mpan_radio_get_tx_status(ZB_MPAN_STACK_ID_ZB) == ZB_RADIO_API_TX_STATUS_LBT_TO_ERROR)
#define ZB_TRANS_CHECK_TX_RETRY_COUNT_EXCEEDED_ERROR() (zb_mpan_radio_get_tx_status(ZB_MPAN_STACK_ID_ZB) == ZB_RADIO_API_TX_STATUS_RETRY_COUNT_EXCEEDED)
#define ZB_TRANS_CHECK_NO_ACK() (zb_mpan_radio_get_tx_status(ZB_MPAN_STACK_ID_ZB) == ZB_RADIO_API_TX_STATUS_NO_ACK)


#define ZB_TRANSCEIVER_ENABLE_AUTO_ACK() zb_radio_api_enable_auto_imm_ack(ZB_TRUE)

#define ZB_GO_IDLE()

#define ZB_GET_HW_LONG_ADDR(addr) zb_mpan_radio_get_hw_long_addr(ZB_MPAN_STACK_ID_ZB, addr)

#define ZB_MAC_SET_ACK_TIMED_OUT()   zb_mpan_radio_set_ack_timeout_expired(ZB_MPAN_STACK_ID_ZB)
#define ZB_MAC_CLEAR_ACK_TIMED_OUT() zb_mpan_radio_clear_ack_waiting_ctx(ZB_MPAN_STACK_ID_ZB)


#else  /* !ZB_MULTIPAN */

/* That branch is for implementing ZBOSS MAC via the common radio low level designed for multipan but without a multipan itself.
   Not sure when will we implement it..
 */

#define ZB_TRANSCEIVER_INIT_RADIO() zb_radio_api_init_zb()
#define ZB_TRANSCEIVER_DEINIT_RADIO() zb_radio_api_deinit()

#define ZB_TRANSCEIVER_START_GET_RSSI(_scan_duration_bi) zb_radio_api_start_get_energy_level((_scan_duration_bi))
#define ZB_TRANSCEIVER_START_GET_ENERGY_LEVEL ZB_TRANSCEIVER_START_GET_RSSI
#define ZB_TRANSCEIVER_GET_ENERGY_LEVEL(out_energy_ptr) zb_radio_api_get_energy_level((out_energy_ptr))

#define ZB_TRANSCEIVER_SET_CHANNEL(page, channel_number) zb_radio_api_set_channel((page), (channel_number))

#define ZB_TRANSCEIVER_SET_PROMISCUOUS(promiscuous_mode) zb_radio_api_set_promiscuous_mode((promiscuous_mode))
#define ZB_TRANSCEIVER_GET_PROMISCUOUS() zb_radio_api_get_promiscuous_mode()

#define ZB_TRANSCEIVER_SET_SHORT_ADDR(short_addr) zb_radio_api_set_short_addr(ZB_MPAN_STACK_ID_ZB, (short_addr))

#define ZB_TRANSCEIVER_SET_PAN_ID(pan_id) zb_radio_api_set_pan_id(ZB_MPAN_STACK_ID_ZB, (pan_id))

#define ZB_TRANSCEIVER_SRC_MATCH_ADD_SHORT_ADDR(nb_index, short_addr) zb_radio_api_src_match_add_short_addr(ZB_MPAN_STACK_ID_ZB, (nb_index), (short_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_DELETE_SHORT_ADDR(nb_index, short_addr) zb_radio_api_src_match_delete_short_addr(ZB_MPAN_STACK_ID_ZB, (nb_index), (short_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_SHORT_SET_PENDING_BIT(short_addr, bit_value) zb_radio_api_src_match_set_pending_bit_by_short(ZB_MPAN_STACK_ID_ZB, (short_addr), ZB_U2B((bit_value)))

#define ZB_TRANSCEIVER_SRC_MATCH_ADD_IEEE_ADDR(nb_index, ieee_addr) zb_radio_api_src_match_add_ieee_addr(ZB_MPAN_STACK_ID_ZB, (nb_index), (ieee_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_DELETE_IEEE_ADDR(nb_index, ieee_addr) zb_radio_api_src_match_delete_ieee_addr(ZB_MPAN_STACK_ID_ZB, (nb_index), (ieee_addr))
#define ZB_TRANSCEIVER_SRC_MATCH_IEEE_SET_PENDING_BIT(ieee_addr, bit_value) zb_radio_api_src_match_set_pending_bit_by_ieee(ZB_MPAN_STACK_ID_ZB, (ieee_addr), ZB_U2B((bit_value)))

#define ZB_TRANSCEIVER_SRC_MATCH_TBL_DROP() zb_radio_api_source_match_table_drop(ZB_MPAN_STACK_ID_ZB)
#define ZB_TRANSCEIVER_SRC_MATCH_IEEE_TBL_DROP() zb_radio_api_source_match_table_drop_ieee(ZB_MPAN_STACK_ID_ZB)
#define ZB_TRANSCEIVER_SRC_MATCH_SHORT_IEEE_TBL_DROP() zb_radio_api_source_match_table_drop_short(ZB_MPAN_STACK_ID_ZB)

#define ZB_TRANSCEIVER_SET_RX_ON_OFF(_rx_on) zb_radio_api_set_rx_on((_rx_on))
#define ZB_TRANSCEIVER_GET_RX_ON_OFF() zb_radio_api_is_rx_on()

#define ZB_TRANSCEIVER_SET_TX_POWER(new_power)  zb_radio_api_set_tx_power((new_power))
#define ZB_TRANSCEIVER_GET_TX_POWER(out_power_ptr) zb_radio_api_get_tx_power((out_power_ptr))

#define ZB_GET_HW_LONG_ADDR(addr) zb_radio_api_get_hw_long_addr(ZB_MPAN_STACK_ID_ZB, addr)

/**
   Synchronous data send.
   At HW the function returned when TX initiated, but not completed. At NS it
   returns when entire packet written to the socket.

   Note:used hack to detect ACK: check hdr_len.
   TODO: change MAC to use separate macro to send ACK.
 */

#define ZB_TRANS_SEND_FRAME(hdr_len, buf, wait_type) zb_radio_api_send_zb((buf), (wait_type))

#define ZB_TRANS_REPEAT_SEND_FRAME ZB_TRANS_SEND_FRAME
#define ZB_TRANS_SEND_ACK ZB_TRANS_SEND_FRAME

#define ZB_TRANS_GET_TX_TIMESTAMP() zb_radio_api_get_tx_timestamp()

#define ZB_MAC_SET_TX_INT_STATUS_BIT() zb_radio_api_set_tx_done_bit(ZB_TRUE)
#define ZB_MAC_CLEAR_TX_INT_STATUS_BIT() zb_radio_api_set_tx_done_bit(ZB_FALSE)
#define ZB_MAC_GET_TX_INT_STATUS_BIT() ZB_B2U(zb_radio_api_get_tx_done_bit())

#define ZB_TRANSCEIVER_UPDATE_LONGMAC() zb_radio_api_set_mac_addr(ZB_MPAN_STACK_ID_ZB, MAC_PIB().mac_extended_address)
#define ZB_TRANSCEIVER_UPDATE_SHORT_ADDR() zb_radio_api_set_short_addr(ZB_MPAN_STACK_ID_ZB, MAC_PIB().mac_short_address)

#define ZB_TRANSCEIVER_UPDATE_PAN_ID() zb_radio_api_set_pan_id(ZB_MPAN_STACK_ID_ZB, MAC_PIB().mac_pan_id)

#define ZB_GO_IDLE() zb_radio_api_go_idle()
#define ZB_IS_TRANSPORT_BUSY() zb_radio_api_is_transport_busy()

#define ZB_RADIO_INT_DISABLE() zb_radio_api_enable_interrupts(ZB_FALSE)
#define ZB_RADIO_INT_ENABLE()  zb_radio_api_enable_interrupts(ZB_TRUE)

#if 0
/* Legacy for UZ2400. Kill it later */
/**
   Get transceiver interrupt - run i/o iteration w/o block
 */
#define ZB_MAC_GET_TRANS_INT_FLAG() ZB_B2U(zb_radio_api_get_transceiver_int_flag())

/**
   Set transceiver interrupt flag
 */
#define ZB_MAC_SET_TRANS_INT() zb_radio_api_set_transceiver_int_flag(ZB_TRUE)

/**
   Clear transceiver interrupt flag
 */
#define ZB_MAC_CLEAR_TRANS_INT() zb_radio_api_set_transceiver_int_flag(ZB_FALSE)
/**
   Read interrupt status register
 */
#define ZB_MAC_READ_INT_STATUS_REG() zb_radio_api_read_transceiver_int_register()
#endif

/* RX status set when full data packet is received */

/**
   Set RX data status to 1 - indicate packet receive
 */
#define ZB_MAC_SET_RX_INT_STATUS_BIT() zb_radio_api_set_rx_done_bit(ZB_TRUE)

/**
   Clear RX data status
 */
#define ZB_MAC_CLEAR_RX_INT_STATUS_BIT() zb_radio_api_set_rx_done_bit(ZB_FALSE)

/**
   Get RX data status
 */
#define ZB_MAC_GET_RX_INT_STATUS_BIT() zb_radio_api_get_rx_done_bit()

/**
   Return 1 if TX failed because of channel access error
 */
#define ZB_TRANS_CHECK_CHANNEL_BUSY_ERROR() zb_radio_api_check_channel_busy_error()
#define ZB_TRANS_CHECK_TX_LBT_TO_ERROR() zb_radio_api_check_tx_lbt_to_error()
#define ZB_TRANS_CHECK_TX_RETRY_COUNT_EXCEEDED_ERROR() zb_radio_api_check_tx_retry_count_exceeded_error()
#define ZB_TRANS_CHECK_NO_ACK() zb_radio_api_check_no_ack()

#define ZB_TRANSCEIVER_SET_BROADCAST_FILTERING(accept_br) zb_radio_api_set_broadcast_filtering((accept_br))

#define ZB_TRANSCEIVER_ENABLE_AUTO_ACK() zb_radio_api_enable_auto_imm_ack(ZB_TRUE)

/* Start continuous transmission. Used in TP_154_PHY24_TRANSMIT_02 test.*/
#define ZB_TRANS_TX_CARRIER_DATA(channel, timeout_bi) zb_radio_api_tx_carrier_data((channel), (timeout_bi))

#endif  /* ZB_MULTIPAN */


#ifdef ZB_ENABLE_PTA
#define ZB_TRANSCEIVER_SET_PTA_STATE() zb_pta_set_state_pib((zb_bool_t)MAC_PIB().pta_state);
#define ZB_TRANSCEIVER_SET_PTA_PRIORITY() zb_pta_set_prio_pib(MAC_PIB().pta_priority)
#define ZB_TRANSCEIVER_SET_PTA_OPTIONS() zb_pta_set_pta_options_pib(MAC_PIB().pta_options, MAC_PIB().pta_options_len)
#define ZB_TRANSCEIVER_GET_PTA_STATE() zb_pta_get_state()
#define ZB_TRANSCEIVER_GET_PTA_PRIORITY() zb_pta_get_prio_pib()
#define ZB_TRANSCEIVER_GET_PTA_OPTIONS(opt,len) zb_pta_get_options_pib(opt,len)

#define ZB_TRANSCEIVER_GET_PTA_LO_PRI_REQ() zb_pta_get_pta_lo_pri_req()
#define ZB_TRANSCEIVER_GET_PTA_HI_PRI_REQ()  zb_pta_get_pta_hi_pri_req()
#define ZB_TRANSCEIVER_GET_PTA_LO_PRI_DENIED()  zb_pta_get_pta_lo_pri_denied()
#define ZB_TRANSCEIVER_GET_PTA_HI_PRI_DENIED()  zb_pta_get_pta_hi_pri_denied()
#define ZB_TRANSCEIVER_GET_PTA_DENIED_RATE()  zb_pta_get_pta_tx_aborted()
#define ZB_TRANSCEIVER_GET_CCA_RETRIES() zb_pta_get_cca_retries()

#endif  /* ZB_ENABLE_PTA */

/* Some PHY testing */
#define ZB_TRANSCEIVER_PERFORM_CCA(out_rssi_ptr) zb_radio_api_perform_cca(out_rssi_ptr)
#define ZB_TRANSCEIVER_GET_SYNC_RSSI() zb_radio_api_get_sync_rssi_dbm()

/* PANCoordinator field of Beacon frame */
#define ZB_TRANSCEIVER_SET_PAN_COORDINATOR(pan_coord) (void)pan_coord

/** @} */

#endif /* ZB_MAP_LL_RADIO_API_H */
