/* ZBOSS Zigbee software protocol stack
 *
 * Copyright (c) 2012-2026 DSR Corporation, Denver CO, USA.
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
/* PURPOSE: Private header for ZGP Proxy internal declarations
*/

#ifndef ZB_ZGP_PROXY_H
#define ZB_ZGP_PROXY_H 1

#ifdef ZB_ENABLE_ZGP_PROXY

#include "zboss_api_zgp.h"
#include "zb_zgp_common.h"

/**
   @cond internals_doc
   @addtogroup zgp_internal
   @{
*/

/*
  gppFunctionality

  b0	GP feature	0b1
  b1	Direct communication (reception of GPDF via GP stub) 	0b1
  b2	Derived groupcast communication 	0b1
  b3	Pre-commissioned groupcast communication 	0b1
  b4	Full unicast communication	0b0
  b5	Lightweight unicast communication	0b1
  b6	Reserved	0b0
  b7	Bidirectional operation	0b0
  b8	Proxy Table maintenance (active and passive, for GPD mobility and GPP robustness)	0b0
  b9	Reserved	0b0
  b10	GP commissioning	0b1
  b11	CT-based commissioning	0b1
  b12	Maintenance of GPD (deliver channel/key during operation)	0b0
  b13	gpdSecurityLevel = 0b00	0b1
  b14	Deprecated: gpdSecurityLevel = 0b01 	0b0
  b15	gpdSecurityLevel = 0b10	0b1
  b16	gpdSecurityLevel = 0b11	0b1
  b17	Reserved	0b0
  b18	Reserved	0b0
  b19	GPD IEEE address	0b1

  So, for GPPB we have 10011010110000101111
 */

#define ZGP_GPPB_FUNCTIONALITY 0x9ac2f

typedef struct zb_zgp_proxy_table_s
{
  zb_zgp_tbl_t base;

  zb_zgp_tbl_array_t dummy_array[ZB_ZGP_PROXY_TBL_SIZE - 1];
} zb_zgp_proxy_table_t;

/*
Bits Parameters
0..2 ApplicationID
   3 EntryActive
   4 EntryValid
   5 Sequence number capabilities
   6 Lightweight Unicast GPS
   7 Derived Group GPS
   8 Commissioned Group GPS
   9 FirstToForward
  10 InRange
  11 GPD Fixed
  12 HasAllUnicastRoutes
  13 AssignedAlias
  14 SecurityUse
  15 Options Extension
*/
#define ZGP_TBL_PROXY_FILL_OPTIONS(app_id, ea, ev, sn_cap, lw, dg, cg, ftf, ir, fix_loc, haur, asn_alias, secur_use, ext) \
  (((app_id) & 7) | ((!!(ea)) << 3) | ((!!(ev)) << 4) | ((!!(sn_cap)) << 5) | ((!!(lw)) << 6) | ((!!(dg)) << 7) |\
   ((!!(cg)) << 8) | ((!!(ftf)) << 9) | ((!!(ir)) << 10) | ((!!(fix_loc)) << 11) | ((!!(haur)) << 12) |\
    ((!!(asn_alias)) << 13) | ((!!(secur_use)) << 14) | ((!!(ext)) << 15) )

typedef struct zb_zgp_proxy_ctx_s
{
  zb_uint8_t           mode;  /**< Current mode of Proxy side. One of the @ref zb_zgp_mode_t */
  zb_zgp_proxy_table_t table;
} zb_zgp_proxy_ctx_t;

extern zb_zgp_proxy_ctx_t zb_zgp_proxy_ctx;
#define ZGP_PROXY_CTX() zb_zgp_proxy_ctx

zb_ret_t zgp_proxy_table_write(zb_zgpd_id_t *zgpd_id, zgp_tbl_ent_t *ent);
zb_ret_t zgp_proxy_table_read(zb_zgpd_id_t *zgpd_id, zgp_tbl_ent_t *ent);
zb_ret_t zgp_proxy_table_read_by_idx(zb_uint_t idx, zgp_tbl_ent_t *ent);
zb_ret_t zgp_proxy_table_idx(zb_zgpd_id_t *zgpd_id, zb_uint_t *idx);
zb_ret_t zgp_proxy_table_del(zb_zgpd_id_t *zgpd_id);
zb_uint32_t zgp_proxy_table_get_security_counter(zb_zgpd_id_t *zgpd_id);
zb_uint32_t zgp_proxy_table_get_dup_counter(zb_zgpd_id_t *zgpd_id);
zb_ret_t zgp_proxy_table_restore_security_counter(zb_zgpd_id_t *zgpd_id);
zb_ret_t zgp_proxy_table_set_security_counter(zb_zgpd_id_t *zgpd_id, zb_uint32_t counter);
zb_uint8_t zgp_proxy_table_get_search_counter(zb_zgpd_id_t *zgpd_id);
zb_ret_t zgp_proxy_table_set_search_counter(zb_zgpd_id_t *zgpd_id, zb_uint8_t counter);
void zgp_proxy_table_get_lqi_rssi(zb_zgpd_id_t *zgpd_id, zb_uint8_t *lqi_p, zb_int8_t *rssi_p);
void zgp_proxy_table_set_lqi_rssi(zb_zgpd_id_t *zgpd_id, zb_uint8_t lqi, zb_int8_t rssi);
zb_bool_t zb_zgp_is_proxy_table_empty(void);
zb_uint8_t zb_zgp_proxy_table_non_empty_entries_count(void);

/**
 * @brief Search table entry by index in nonempty entries list
 *
 * @param index   [in]   Index of table entry which needed
 * @param ent     [out]  Pointer to allocated memory space for table entry
 *
 */
zb_bool_t zb_zgp_proxy_table_get_entry_by_non_empty_list_index(zb_uint8_t index, zgp_tbl_ent_t *ent);
zb_uint8_t zb_zgp_proxy_table_entry_get_search_counter(zgp_tbl_ent_t *ent);
zb_ret_t zb_zgp_proxy_table_entry_set_search_counter(zgp_tbl_ent_t *ent, zb_uint8_t counter);

/**
 * @brief Get runtime bit field from runtime options
 *
 * @param ent     [in]  Pointer to table entry
 * @param field   [in]  bit field index
 *
 * @return bit field current value
 */
zb_uint8_t zb_zgp_proxy_table_entry_get_runtime_field(zgp_tbl_ent_t *ent, zb_uint8_t field);

/**
 * @brief Set runtime bit field in runtime options
 *
 * @param ent     [in]  Pointer to table entry
 * @param field   [in]  bit field index
 *
 */
void zb_zgp_proxy_table_entry_set_runtime_field(zgp_tbl_ent_t *ent, zb_uint8_t field);

/**
 * @brief Reset runtime bit field current value in runtime options
 *
 * @param ent     [in]  Pointer to table entry
 * @param field   [in]  bit field index
 *
 */
void zb_zgp_proxy_table_entry_clr_runtime_field(zgp_tbl_ent_t *ent, zb_uint8_t field);

#define ZGP_TBL_RUNTIME_GET_VALID(ent) zb_zgp_proxy_table_entry_get_runtime_field(ent, 0)
#define ZGP_TBL_RUNTIME_SET_VALID(ent) zb_zgp_proxy_table_entry_set_runtime_field(ent, 0)
#define ZGP_TBL_RUNTIME_CLR_VALID(ent) zb_zgp_proxy_table_entry_clr_runtime_field(ent, 0)

#define ZGP_TBL_RUNTIME_GET_FIRST_TO_FORWARD(ent) zb_zgp_proxy_table_entry_get_runtime_field(ent, 1)
#define ZGP_TBL_RUNTIME_SET_FIRST_TO_FORWARD(ent) zb_zgp_proxy_table_entry_set_runtime_field(ent, 1)
#define ZGP_TBL_RUNTIME_CLR_FIRST_TO_FORWARD(ent) zb_zgp_proxy_table_entry_clr_runtime_field(ent, 1)

#define ZGP_TBL_RUNTIME_FIRST_TO_FORWARD_UPDATE(ent, value)\
  {\
    if ((value))\
      ZGP_TBL_RUNTIME_SET_FIRST_TO_FORWARD((ent));\
    else\
      ZGP_TBL_RUNTIME_CLR_FIRST_TO_FORWARD((ent));\
  }

#define ZGP_TBL_RUNTIME_GET_HAS_ALL_UNICAST_ROUTES(ent) zb_zgp_proxy_table_entry_get_runtime_field(ent, 2)
#define ZGP_TBL_RUNTIME_SET_HAS_ALL_UNICAST_ROUTES(ent) zb_zgp_proxy_table_entry_set_runtime_field(ent, 2)
#define ZGP_TBL_RUNTIME_CLR_HAS_ALL_UNICAST_ROUTES(ent) zb_zgp_proxy_table_entry_clr_runtime_field(ent, 2)

#define ZGP_TBL_GET_SEARCH_COUNTER(ent) zb_zgp_proxy_table_entry_get_search_counter(ent)
#define ZGP_TBL_SET_SEARCH_COUNTER(ent, counter) zb_zgp_proxy_table_entry_set_search_counter(ent, counter)

#define ZB_ZGP_GP_PROXY_TBL_REQ_GET_APP_ID(opt)\
  ((opt) & 0x07)

#define ZB_ZGP_GP_PROXY_TBL_REQ_GET_REQ_TYPE(opt)\
  (((opt) >> 3) & 3)

#define ZB_ZGP_GP_PROXY_TBL_REQ_FILL_OPT(app_id, req_type)\
  ((app_id) | (((req_type) & 3) << 3))

/*! @} */

#ifdef ZB_CERTIFICATION_HACKS
typedef struct zgp_proxy_cert_hacks_s
{
  zb_bitfield_t gp_proxy_ignore_duplicate_gp_frames:1; /*!< If set to 1, disable proxy drop duplicate gp frames */
  zb_bitfield_t gp_proxy_replace_gp_notif_sec_level:1; /*!< If set to 1, proxy replaces security level
                                                        *   ONLY in options of the GP Notification packet */
  zb_uint8_t    gp_proxy_replace_sec_level;            /*!< data to set in replace mode*/
  zb_bitfield_t gp_proxy_replace_gp_notif_sec_key_type:1; /*!< If set to 1, proxy replaces security key type
                                                        *   ONLY in options of the GP Notification packet */
  zb_uint8_t    gp_proxy_replace_sec_key_type;         /*!< data to set in replace mode*/
  zb_bitfield_t gp_proxy_replace_gp_notif_sec_frame_counter:1; /*!< If set to 1, proxy replaces security frame counter */
  zb_uint32_t   gp_proxy_replace_sec_frame_counter;    /*!< data to set in replace mode*/
  zb_callback_t gp_proxy_gp_notif_req_cb;              /*!< Called before proxy send gp notification */
  zb_callback_t gp_proxy_gp_comm_notif_req_cb;         /*!< Called before proxy send gp commissioning notification */
  zb_bitfield_t gp_proxy_replace_comm_app_id:1;        /*!< If set to 1, proxy replaces app_id in commissioning frame */
  zb_bitfield_t gp_proxy_replace_comm_app_id_format:1; /*!< If set to 1, proxy replaces app_id in commissioning frame and its format */
  zb_uint8_t    gp_proxy_replace_comm_app_id_value;    /*!< data to set in replace mode*/
  zb_bitfield_t gp_proxy_replace_comm_options:1;       /*!< If set to 1, proxy replaces app_id in commissioning frame */
  zb_uint16_t   gp_proxy_replace_comm_options_value;   /*!< data to set in replace mode*/
  zb_uint16_t   gp_proxy_replace_comm_options_mask;    /*!< mask to set in replace mode*/

  zb_bitfield_t gp_proxy_replace_comm_gpd_id:1;        /*!< If set to 1, proxy replaces gpd_id in commissioning frame */
  zb_uint32_t   gp_proxy_replace_comm_gpd_id_value;    /*!< data to set in replace mode*/
  zb_ieee_addr_t gp_proxy_replace_comm_gpd_ieee_value;    /*!< data to set in replace mode*/
  zb_uint8_t    gp_proxy_replace_comm_gpd_ep_value;    /*!< data to set in replace mode*/
} zgp_proxy_cert_hacks_t;

zgp_proxy_cert_hacks_t* zb_zgp_proxy_cert_hacks_get(void);
extern zgp_proxy_cert_hacks_t zb_zgp_proxy_cert_hacks;

#define ZGP_PROXY_CERT_HACKS() zb_zgp_proxy_cert_hacks
#endif  /* ZB_CERTIFICATION_HACKS */

/**
 * @brief Check that Proxy functionality is linked
 *
 * @return ZB_FALSE in case it is weak function
 *         ZB_TRUE if Proxy functionality is linked
 */
zb_bool_t zb_zgp_proxy_is_linked(void);

/**
 * @brief Check that Proxy functionality is available in runtime
 *
 * @return ZB_FALSE in case it is disabled by device role
 *         ZB_TRUE if Proxy functionality is available
 */
zb_bool_t zb_zgp_proxy_is_available(void);

/**
 * @brief Proxy initialization
 *
 */
void zb_zgp_proxy_init(void);
zb_ret_t zgp_proxy_table_init();
zb_bool_t age_proxy_table();

void zb_zgp_proxy_set_default_endpoint_values(zb_af_endpoint_desc_t * gp_ep);

typedef ZB_PACKED_PRE struct zb_zgp_gp_pairing_req_s
{
  zb_uint32_t    options;
  zb_zgpd_addr_t zgpd_addr;
  zb_uint8_t     endpoint;
  zb_ieee_addr_t sink_ieee_addr;
  zb_uint16_t    sink_nwk_addr;
  zb_uint16_t    sink_group_id;
  zb_uint8_t     dev_id;
  zb_uint32_t    sec_frame_counter;
  zb_uint8_t     key[ZB_CCM_KEY_SIZE];
  zb_uint16_t    assigned_alias;
  zb_uint8_t     frwd_radius;
}
ZB_PACKED_STRUCT zb_zgp_gp_pairing_req_t;

/**
 * @brief Handle proxy GP Pairing command
 *
 * @param param  [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.5.2
 */
zb_ret_t zgp_proxy_handle_gp_pairing_cmd(zb_bufid_t param);

/**
 * @brief Handle proxy GP Commissioning Mode command
 *
 * @param param  [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.5.3
 */
zb_ret_t zgp_proxy_handle_gp_commissioning_mode_cmd(zb_bufid_t param);

/**
 * @brief Handle proxy GP Response command
 *
 * @param param  [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.5.4
 */
zb_ret_t zgp_proxy_handle_gp_response_cmd(zb_bufid_t param);

/**
 * @brief Handle GP Proxy Table Request command, perform proxy table response
 *
 * @param param  [in]  Buffer reference
 *
 * @see ZGP spec, A.3.4.3.1
 */
zb_ret_t zgp_proxy_handle_proxy_table_request_cmd(zb_bufid_t param);

zb_ret_t zgp_proxy_handle_read_proxy_table(zb_bufid_t param);

void zb_gp_proxy_data_indication(zb_cb_param_t param);
void zb_gp_proxy_mlme_get_cfm_cb(zb_bufid_t param);
void zb_gp_proxy_mlme_set_cfm_cb(zb_bufid_t param);

void zb_zgp_proxy_commissioning_mode_expired(zb_cb_param_t param);

zb_ret_t zgp_proxy_table_enumerate(zb_zgp_ent_enumerate_ctx_t *ctx, zgp_tbl_ent_t *ent);

zb_uint8_t zb_zgp_proxy_mode_get(void);

void zb_zgp_proxy_leave_from_commissioning_mode();

#endif  /* ZB_ENABLE_ZGP_PROXY */
#endif /* ZB_ZGP_PROXY_H */
