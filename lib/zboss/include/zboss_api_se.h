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
/* PURPOSE: common definitions for Zigbee Smart Energy profile
*/

#ifndef ZBOSS_API_ZSE_H
#define ZBOSS_API_ZSE_H 1

#include "zb_address.h"
#include "zb_types.h"
#include "se/zb_se_device_config.h"
#include "zcl/zb_zcl_config.h"
#include "zcl/zb_zcl_common.h"
#include "zcl/zb_zcl_commands.h"

#include "se/zb_se_config.h"
#include "zcl/zb_zcl_keep_alive.h"

#if 0
#include "se/zb_se_metering_device.h"
#include "se/zb_se_metering_load_control.h"
#include "se/zb_se_in_home_display.h"
#include "se/zb_se_pct_device.h"
#include "se/zb_se_energy_service_interface.h"
#endif


/** @cond DOXYGEN_SE_SECTION */

/** @addtogroup se_secur
 *  @{
 */

#define zb_se_load_ecc_cert zb_zcl_kec_load_ecc_cert
#define zb_se_erase_ecc_cert zb_zcl_kec_erase_ecc_cert

#ifdef ZB_SE_COMMISSIONING
/**
 * @brief Allows to retry CBKE procedure with Trust Center.
 *
 * @details This procedure should be used if the application got @ref ZB_SE_SIGNAL_CBKE_FAILED signal
 *   from the stack to repeat the CBKE using another certificate, which should be loaded before.
 *
 * @param[in] param - reference to the buffer, which will be used
 *                    for outgoing Match Descriptor Request command
 *                    or 0 if a buffer should be allocated.
 *
 * @see zb_se_load_ecc_cert()
 * @see ZB_SE_SIGNAL_CBKE_FAILED
 */
void zb_se_retry_cbke_with_tc(zb_cb_param_t param);
#endif /* ZB_SE_COMMISSIONING */

/**
 * @brief Checks availability of valid keypair for the specified remote device using its short address.
 *
 * @details Valid key is either a TCLK to TC established by CBKE procedure or a partner APS link key
 *   established using partner link keys establishment procedure.
 *
 * @param[in] addr - short address of the remote device
 *
 * @retval ZB_TRUE - valid key exists
 * @retval ZB_FALSE - no valid key exists
 *
 * @par Example
 * If there is no valid keypair, then the key establishment is initiated:
 * @code{.c}
 *   if (dev_addr != 0 && !zb_se_has_valid_key(dev_addr)
 *   {
 *     ZB_SCHEDULE_CALLBACK(zb_se_start_aps_key_establishment, ZB_PACK_2_U16_IN_U32(param, dev_addr));
 *   }
 * @endcode
 *
 * @see zb_se_start_aps_key_establishment()
 * @see zb_se_has_valid_key_by_ieee()
 */
zb_bool_t zb_se_has_valid_key(zb_uint16_t addr);

/**
 * @brief Checks availability of valid keypair for the specified remote device using its address 
 * as a keypair established between a pair of devices.
 *
 * @details Valid key definition is in the @ref zb_se_has_valid_key().
 *
 * @param[in] addr - long address of the remote device
 *
 * @retval ZB_TRUE - valid key exists
 * @retval ZB_FALSE - no valid key exists
 *
 * @see zb_se_start_aps_key_establishment()
 * @see zb_se_has_valid_key()
 */
zb_bool_t zb_se_has_valid_key_by_ieee(zb_ieee_addr_t addr);

/**
 * @brief Retrieves APS link key or TCLK for the remote device.
 *
 * @param[in] addr - short address of the remote device
 * @param[out] link_key - buffer for the key
 *
 * @retval RET_OK - on success
 * @retval RET_NOT_FOUND - link key wasn't found
 *
 * @attention To be used mainly for debug purposes. Key availability should be verified using @ref zb_se_has_valid_key() before making this call.
 *
 * @see zb_se_debug_get_link_key_by_long()
 */
zb_ret_t zb_se_debug_get_link_key(zb_uint16_t addr, zb_uint8_t link_key[ZB_CCM_KEY_SIZE]);

/**
 * @brief Retrieves APS link key or TCLK for the remote device using it's long address.
 *
 * @param[in] ieee - long address of the remote device
 * @param[out] link_key - buffer for the key
 *
 * @retval RET_OK - on success
 * @retval RET_NOT_FOUND - link key wasn't found
 *
 * @attention To be used mainly for debug purposes.
 *
 * @see zb_se_debug_get_link_key()
 */
zb_ret_t zb_se_debug_get_link_key_by_long(zb_ieee_addr_t ieee, zb_uint8_t link_key[ZB_CCM_KEY_SIZE]);

/**
 * @brief Retrieves current NWK key.
 *
 * @param[out] key - buffer for the key
 *
 * @retval RET_OK - on success
 * @retval RET_NOT_FOUND - NWK key wasn't found
 *
 * @attention To be used mainly for debug purposes.
 */
zb_ret_t zb_se_debug_get_nwk_key(zb_uint8_t key[ZB_CCM_KEY_SIZE]);

#ifdef ZB_ENABLE_SE
/**
 * @brief Deletes CBKE link key.
 *
 * @cond DOCS_DEV_NOTES
 * Something more could be added on this function...
 * @endcond
 *
 * @param[in] ieee_address - long address of the device
 */
void zb_se_delete_cbke_link_key(zb_ieee_addr_t ieee_address);
#endif /* ZB_ENABLE_SE */


/**
 * @brief Retrieves APS link key generated from the current installcode.
 *
 * @param[out] key - buffer for the key
 *
 * @retval RET_OK - on success
 * @retval RET_NOT_FOUND - no installcode found
 * @retval RET_PROTOCOL_ERROR - bad CRC in installcode
 *
 * @attention To be used mainly for debug purposes.
 */
zb_ret_t zb_se_debug_get_ic_key(zb_uint8_t key[ZB_CCM_KEY_SIZE]);

/**
 *  @brief Starts procedure of partner APS link key establishment with the specified device.
 *
 *  @details ZBOSS indicates completion status of this procedure by passing
 *           @ref ZB_SE_SIGNAL_APS_KEY_READY and @ref ZB_SE_SIGNAL_APS_KEY_FAIL signals
 *           to the application's signal handler.
 *           Application should process these signals if needed.
 *
 *  @param[in] cb_param - packed reference to the buffer which will be used for outgoing Match Descriptor
 *                     Request command and short address of the remote device
 *
 *  @see ZB_SE_SIGNAL_APS_KEY_READY
 *  @see ZB_SE_SIGNAL_APS_KEY_FAIL
 *  @see ZB_SE_SIGNAL_CBKE_OK
 *  @see zb_se_has_valid_key()
 */
void zb_se_start_aps_key_establishment(zb_cb_param_t cb_param);


/** @} */ /* se_secur */


/** @addtogroup se_comm
 *  @{
 */

#ifdef ZB_SE_COMMISSIONING
#ifdef ZB_COORDINATOR_ROLE
/**
 * @brief Initiates SE device as a Zigbee 2.4 GHz Coordinator.
 *
 * @param[in] channel_mask - Zigbee channel mask
 *
 * @par Example
 * Energy Service Device parameters definition:
 * @snippet se/energy_service_interface/se_esi_zc.c ESI_DEV_DEFINE_PARAMS
 * Initialization of ESI device:
 * @snippet se/energy_service_interface/se_esi_zc.c ESI_DEV_INIT
 * Zigbee role setting:
 * @snippet se/energy_service_interface/se_esi_zc.c ESI_DEV_SET_ROLE
 */
void zb_se_set_network_coordinator_role(zb_uint32_t channel_mask);
#endif /* ZB_COORDINATOR_ROLE */



#ifdef ZB_ED_FUNC
/**
 * @brief Initiates SE device as a Zigbee 2.4 GHz End Device.
 *
 * @param[in] channel_mask - Zigbee channel mask
 *
 * @par Example
 * Metering Device parameters definition:
 * @snippet se/metering/se_el_metering_zed.c METERING_DEV_DEFINE_PARAMS
 * Initialization of Metering device:
 * @snippet se/metering/se_el_metering_zed.c METERING_DEV_INIT
 * Zigbee role setting:
 * @snippet se/metering/se_el_metering_zed.c METERING_DEV_SET_ROLE
 */
void zb_se_set_network_ed_role(zb_uint32_t channel_mask);
#endif /* ZB_ED_FUNC */

#ifdef ZB_ROUTER_ROLE
/**
 * @brief Initiates SE device as a Zigbee 2.4 GHz Router.
 *
 * @param[in] channel_mask - Zigbee channel mask
 *
 * @par Example
 * In-Home Display parameters definition:
 * @snippet se/in_home_display/se_ihd_zr.c IHD_DEV_DEFINE_PARAMS
 * Initialization of IHD device:
 * @snippet se/in_home_display/se_ihd_zr.c IHD_DEV_INIT
 * Zigbee role setting:
 * @snippet se/in_home_display/se_ihd_zr.c IHD_DEV_SET_ROLE
 */
void zb_se_set_network_router_role(zb_uint32_t channel_mask);
#endif /* ZB_ROUTER_ROLE */

#ifdef ZB_COORDINATOR_ROLE
/**
 * @brief Initiates device as a Zigbee Multi-MAC Select device coordinator.
 *
 * @param[in] channel_list - pointer to the Zigbee channel list
 *
 * @note This function selects device ZC if impossible in SE profile.
 * This API supposes @p channel_list can contain either single 2.4 GHz entry or 1 or more Sub-GHz entries,
 * so ZC will be either 2.4-only or Sub-GHz-only depending on @p channel_list contents.
 */
void zb_se_set_network_coordinator_role_select_device(zb_channel_list_t channel_list);

/**
 * @brief Initiates device as a Zigbee Multi-MAC Switch device coordinator.
 *
 * @param[in] channel_list - pointer to the Zigbee channel list
 *
 * @note Requires 2 MAC interfaces. Not every hardware supports Switch ZC role.
 */
void zb_se_set_network_coordinator_role_switch_device(zb_channel_list_t channel_list);

/**
 * @brief Opens the network for joining for a specified amount of time.
 *
 * @param[in] timeout_s - amount of time (sec) after which joining will be disabled
 *
 * @note This function should be called at Trust Center only.
 *
 * @par Example
 * Energy Service Device parameters definition:
 * @snippet se/energy_service_interface/se_esi_zc.c ESI_DEV_DEFINE_PARAMS
 * Usage of zb_se_permit_joining():
 * @snippet se/energy_service_interface/se_esi_zc.c PERMIT_JOINING
 */
void zb_se_permit_joining(zb_time_t timeout_s);
#endif /* ZB_COORDINATOR_ROLE */

#ifdef ZB_ED_FUNC
/**
 * @brief Initiates device as a Zigbee Multi-MAC Select device end device.
 * @param[in] channel_list - pointer to the Zigbee channel list
 * @parblock
 * If @p channel_list contains 2.4 only entry, work as 2.4-only device.
 * If @p hannel_list contains Sub-GHz entries and no 2.4 entry, work as Sub-GHz-only device.
 * If @p channel_list contains both 2.4 and Sub-GHz entries, work as true Select device trying to join at 2.4 when at Sub-GHz.
 * @endparblock
 *
 * @cond DOCS_DEV_NOTES
 * In order to display funcs absent in doxygen docs, use || defined(DOXYGEN)
 * Should it be used at every #if??
 * @endcond
 */
void zb_se_set_network_ed_role_select_device(zb_channel_list_t channel_list);
#endif /* ZB_ED_FUNC */


/**
 * @brief Puts the device into the Auto-Joining state.
 *
 * @details Auto-Joining state implies performing of PAN joining attempts with defined
 *   timeouts between retries.
 *
 * @param[in]  param - reference to the buffer, which will be used for outgoing network discovery
 *                     request or 0 if buffer should be allocated.
 *
 * @retval RET_OK - successfully stopped
 * @retval RET_ERROR - auto-join is either in progress or wasn't started
 *
 * @par Example
 * Enabling auto-join on button click via function pointer:
 * @snippet se/in_home_display/se_ihd_zr.c AUTO_JOIN
 */
zb_ret_t zb_se_auto_join_start(zb_bufid_t param);


/**
 * @brief Stops the Auto-Join process started with @ref zb_se_auto_join_start.
 *
 * @retval RET_OK - successfully stopped
 * @retval RET_ERROR - auto-join is either in progress or wasn't started
 *
 * @par Example
 * Disabling auto-join on button click via function pointer:
 * @snippet se/in_home_display/se_ihd_zr.c AUTO_JOIN
 */
zb_ret_t zb_se_auto_join_stop(void);
#endif /* ZB_SE_COMMISSIONING */


#if defined(ZB_SE_ENABLE_SERVICE_DISCOVERY_PROCESSING) || defined(DOXYGEN)

/**
 * @brief Puts device into the Service Discovery state.
 * @anchor zse_service_disc_dev_t
 *
 * @details The Service Discovery mechanism is used to find other devices on the network
 *          that offer services matching those of the initiator device.
 *          The initiator device will receive a series of devices that meet the discovery criteria.
 *          It should decide whether to bind with each found device based
 *          on the @p cluster_id and @p commodity_type (see \ref zse_service_disc_dev_t) values. The process stops when no more devices are available.
 *
 * @param[in] endpoint - source endpoint for service discovery
 *
 * @retval RET_OK - on success
 * @retval RET_INVALID_PARAMETER_1 - specified endpoint is invalid (zero, non-SE, has no client clusters)
 *
 * @par Example
 * @b ZBOSS signal retrieving and preprocessing:
 * @snippet se/in_home_display/se_ihd_zr.c SIGNAL_HANDLER_GET_SIGNAL
 * @ref ZB_SE_SIGNAL_SERVICE_DISCOVERY_START signal handling:
 * @snippet se/in_home_display/se_ihd_zr.c SIGNAL_HANDLER_START_DISCOVERY
 */
zb_ret_t zb_se_service_discovery_start(zb_uint8_t endpoint);


/**
 * @brief Stops Service Discovery process started with @ref zb_se_service_discovery_start().
 * @details This call allows for the premature termination of receiving matched devices
 *          without waiting for the process to finish.
 *          It is not a mandatory call for stopping the Service Discovery, but it can be useful
 *          if the initiator decides to break the discovery for some reason
 *          (e.g., if it doesn't need to bind multiple devices).
 */
void zb_se_service_discovery_stop(void);


/**
 * @brief Allows enabling or disabling support for multiple commodity networks.
 *
 * @details In networks that support multiple commodities, the Service Discovery process
 *          will return multiple instances of certain clusters.
 *          The multiple-commodity feature allows the application to determine the type of
 *          metering, price, etc., that it has discovered by analyzing the @p commodity_type attribute
 *          (see \ref zse_service_disc_dev_t).
 *          In a single-commodity network, this attribute is not supported, meaning all commodities are of the same type.
 *
 * @param[in] enabled - flag (1|0) indicates whether multiple-commodity support should be enabled
 *
 * @note Multiple commodity feature is enabled in ZBOSS stack by default.
 */
void zb_se_service_discovery_set_multiple_commodity_enabled(zb_uint8_t enabled);

/**
 * @brief Sends Bind Request command to the discovered SE device.
 *
 *
 * @param[in] param    - reference to the buffer, which will be used for outgoing ZDO Bind Request command
 * @param[in] dst_ieee - address of the found device
 * @param[in] dst_ep   - device's endpoint
 *
 * @note This function should only be called after the application receives the @ref ZB_SE_SIGNAL_SERVICE_DISCOVERY_DO_BIND signal.
 * @note Device information (address, endpoint) should be taken from a signal's parameter.
 *          Cluster ID will be taken automatically by stack.
 *
 * @par Example
 * ZBOSS signal retrieving and preprocessing:
 * @snippet se/in_home_display/se_ihd_zr.c SIGNAL_HANDLER_GET_SIGNAL
 * @ref ZB_SE_SIGNAL_SERVICE_DISCOVERY_DO_BIND signal parameters retrieval:
 * @snippet se/in_home_display/se_ihd_zr.c SIGNAL_HANDLER_DO_BIND
 * @ref ZB_SE_SIGNAL_SERVICE_DISCOVERY_DO_BIND signal handling:
 * @snippet se/in_home_display/se_ihd_zr.c SIGNAL_HANDLER_BIND_DEV
 *
 * @see zb_se_signal_service_discovery_bind_params_t()
 * @see ZB_SE_SIGNAL_SERVICE_DISCOVERY_DO_BIND
 */
void zb_se_service_discovery_bind_req(zb_bufid_t param, zb_ieee_addr_t dst_ieee, zb_uint8_t dst_ep);

#endif

/** @name SE Runtime
 *  @{
 */

#ifdef ZB_SE_COMMISSIONING
/**
   Informs ZBOSS that application is starting high-frequency mode at the given cluster.

   This routine is meaningful when working in Sub-Ghz mode only.

   High frequency messages are messages transmitted more
   frequently than once per 30 seconds. SE 1.4 specification does not
   define what is "message", so ZBOSS treats it as "packets using the same
   cluster".
   High frequency messages must not require APS ACK and must set
   "Disable Default Response" bit.

   Normally ZBOSS detects high-frequency messages
   automatically, so only second message over the same cluster can be
   "high frequency message".  But SE certification testing requires
   message to be "high frequency" starting from the first message, so
   ZBOSS implemented explicit routine.

   @param clusterid - cluster ID.
 */
void zb_start_high_freq_msgs(zb_uint16_t clusterid);
#endif /* ZB_SE_COMMISSIONING */

/** @} */ /* se_runtime */


/** @} */ /* se_comm */

/** @endcond */ /* DOXYGEN_SE_SECTION */

#endif /* ZBOSS_API_ZSE_H */
