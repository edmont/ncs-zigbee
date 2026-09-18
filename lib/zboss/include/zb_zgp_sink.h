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
/* PURPOSE: Private header for ZGP Sink internal declarations
*/

#ifndef ZB_ZGP_SINK_H
#define ZB_ZGP_SINK_H 1

#ifdef ZB_ENABLE_ZGP_SINK

#include "zboss_api_zgp.h"
#include "zb_zgp_common.h"

/**
   @cond internals_doc
   @addtogroup zgp_internal
   @{
*/

/*
  gpsFunctionality

  b0	GP feature	0b1
  b1	Direct communication (reception of GPDF via GP stub) 	device-specific
  b2	Derived groupcast communication 	device-specific
  b3	Pre-commissioned groupcast communication 	device-specific
  b4	Full unicast communication	0b0
  b5	Lightweight unicast communication	device-specific
  b6	Proximity bidirectional operation	0b0
  b7	Multi-hop bidirectional operation	0b0
  b8	Proxy Table maintenance (active and passive, for GPD mobility and proxy robustness)	0b0
  b9	Proximity commissioning (unidirectional and bidirectional)	device-specific
  b10	Multi-hop commissioning (unidirectional and bidirectional)	0b1
  b11	CT-based commissioning	0b1
  b12	Maintenance of GPD (deliver channel/key during operation)	0b0
  b13	gpdSecurityLevel = 0b00  in operation	device-specific
  b14	Deprecated: gpdSecurityLevel = 0b01 	0b0
  b15	gpdSecurityLevel = 0b10	0b1
  b16	gpdSecurityLevel = 0b11	0b1
  b17	Sink Table-based groupcast forwarding	0b0
  b18	Translation Table	device-specific
  b19	GPD IEEE address	0b1

  For Basic Sink in our case:
  - no Translation table (0)
  - no gpdSecurityLevel = 0b00  in operation 0
  - yes Proximity commissioning - 1
  - yes Lightweight unicast communication - 1
  - yes Pre-commissioned groupcast communication - 1
  - yes Derived groupcast communication - 1
  - yes Direct communication (reception of GPDF via GP stub) - 1

  10011000111000101111
 */

#define ZGP_GPSB_FUNCTIONALITY 0x98e2f

#define ZB_ZGP_MAX_CONTACT_STATUS_BITS          8
#define ZB_ZGP_MAX_GPDF_CMD_PAYLOAD_APP_ID_0000 59
#define ZB_ZGP_MAX_GPDF_CMD_PAYLOAD_APP_ID_0010 54

#define ZB_ZGP_UNSEL_TEMP_MASTER_IDX   0xFF
#define ZB_ZGP_TEMP_MASTER_EMPTY_ENTRY 0xFFFF

#define ZB_APP_DESCR_TIMEOUT (20*ZB_TIME_ONE_SECOND)
#define ZB_ZGP_MULTI_SENSOR_COMMISSIONING_TIMEOUT (20*ZB_TIME_ONE_SECOND) /* A.3.6.2.4 */

#define ZB_ZGPS_CMD_PROCESSING_POSTPONED_MS 100U

typedef ZB_PACKED_PRE struct zb_zgp_gp_comm_notification_req_s
{
  /* optimization: use reserved 15 bit of options as indicate that command received in unicast mode */
  zb_uint16_t            options;
  zb_zgpd_addr_t         zgpd_addr;
  zb_uint8_t             endpoint;
  zb_uint32_t            gpd_sec_frame_counter;
  zb_uint8_t             gpd_cmd_id;
  /* +1 bytes for payload size placed at beginning buffer */
  zb_uint8_t             payload[MAX_ZGP_CLUSTER_GPDF_PAYLOAD_SIZE+1];
  zb_zgp_gp_proxy_info_t proxy_info;
  zb_uint32_t            mic;
}
ZB_PACKED_STRUCT zb_zgp_gp_comm_notification_req_t;

typedef struct zb_zgp_sink_table_s
{
  zb_zgp_tbl_t base;

  zb_zgp_tbl_array_t dummy_array[ZB_ZGP_SINK_TBL_SIZE - 1];
} zb_zgp_sink_table_t;

/* 11/23/2022 [VK]
 * It is required to parse GP Pairing Configuration with
 * Application Description correctly and should be used in RAM ONLY.
 *
 * We should pass a report ID to zgp_sink_handle_gp_pairing_configuration()
 * after zgp_parse_gp_pairing_configuration_app_descr() to put report descriptors
 * to a ZGPD entry by it.
 *
 * Default struct zgp_report_desc_t is used to store in NVRAM and should NOT contain report_id.
 */
typedef ZB_PACKED_PRE struct zgp_report_desc_pairing_config_s
{
  zb_uint8_t  report_id;
  zgp_report_desc_options_t  options;
  zb_uint16_t timeout;
  zb_uint8_t  point_descs_data_len;
  zb_uint8_t  point_descs_data[ZB_ZGP_APP_DESCR_REPORT_DATA_SIZE]; /* contains array of not parsed zgp_data_point_desc_t */
} ZB_PACKED_STRUCT zgp_report_desc_pairing_config_t;

/**
 * @brief Parsed values of GPDF frame
 *
 * Structure contains GPDF information that is needed for mapping by ZGP to ZCL mapping layer
 */
typedef ZB_PACKED_PRE struct zb_gpdf_to_zcl_info_s
{
  /* gpdf info fields */
  zb_uint8_t   mac_seq_num;       /**< MAC sequence number */
  zb_uint8_t   nwk_frame_ctl;     /**< NWK frame control */
  zb_uint8_t   nwk_ext_frame_ctl; /**< Extended NWK frame control */
  zb_zgpd_id_t zgpd_id;           /**< ZGPD ID */
  zb_uint8_t   zgpd_cmd_id;       /**< ZGPD command ID */
  /* persisted fields */
  union {
    struct {
      zb_bitfield_t report_desc:1;
      zb_bitfield_t switch_cfg:1;
      zb_bitfield_t reserved:6;
    } bit;
    zb_uint8_t all_bits;
  } options;                      /**< Options what the extra info is filled in */
  zgp_report_desc_t report_descr; /**< Report descriptor the incoming compact attribute index points to */
  zb_gpdf_comm_switch_gen_cfg_t switch_cfg; /**< Switch configuration */
  /* context fields */
  zb_bufid_t   buf_iterator;
}
ZB_PACKED_STRUCT zb_gpdf_to_zcl_info_t;

#define ZB_GPDF_INFO_COPY_TO_MAPPING_INFO(mapping_info, info)            \
  (mapping_info)->mac_seq_num = (info)->mac_seq_num;                     \
  (mapping_info)->nwk_frame_ctl = (info)->nwk_frame_ctl;                 \
  (mapping_info)->nwk_ext_frame_ctl = (info)->nwk_ext_frame_ctl;         \
  (mapping_info)->zgpd_id.app_id = (info)->zgpd_id.app_id;               \
  switch ((mapping_info)->zgpd_id.app_id) {                              \
    case ZB_ZGP_APP_ID_0000:                                             \
      (mapping_info)->zgpd_id.addr.src_id = (info)->zgpd_id.addr.src_id; \
      break;                                                             \
    case ZB_ZGP_APP_ID_0010:                                             \
      (mapping_info)->zgpd_id.endpoint = (info)->zgpd_id.endpoint;       \
      ZB_IEEE_ADDR_COPY((mapping_info)->zgpd_id.addr.ieee_addr,          \
                        (info)->zgpd_id.addr.ieee_addr);                 \
      break;                                                             \
    default:                                                             \
      ZB_ASSERT(0);                                                      \
  }                                                                      \
  (mapping_info)->zgpd_cmd_id = (info)->zgpd_cmd_id

#define ZB_GPDF_MAPPING_INFO_INIT(mapping_info)                          \
  (mapping_info)->buf_iterator = ZB_BUF_INVALID

typedef struct zgp_runtime_app_description_ctx_s
{
  zb_gpdf_info_t gpdf_info;
  zb_uint8_t     report_idx;
  zb_uint8_t     point_desc_offset;
}zgp_runtime_app_description_ctx_t;

/*
Bits: 0..2      3..4                    5                               6               7               8               9
ApplicationID   Communication mode      Sequence number capabilities    RxOnCapability  FixedLocation   AssignedAlias   Security use
*/

#define ZGP_TBL_SINK_FILL_OPTIONS(app_id, comm_mode, sn_cap, rxon_cap, fix_loc, asn_alias, secur_use) \
  (((app_id) & 7) | (((comm_mode) & 3) << 3) | ((!!(sn_cap)) << 5) | ((!!(rxon_cap)) << 6) | ((!!(fix_loc)) << 7) | ((!!(asn_alias)) << 8) | ((!!(secur_use)) << 9))

typedef struct zb_zgp_sink_ctx_s
{
  zb_uint8_t                mode; /**< Current mode of Sink side. One of the @ref zb_zgp_mode_t */
  /* Since commissioning doesn't necessarily end after one pairing,
   * pairing endpoint needs to be placed outside of comm_data
   * because comm_data is cleared after each commissioned device.
   */
  zb_uint8_t                pairing_endpoint;            /**< Endpoint for current commissioniing process */

  zb_uint8_t                mode_change_reason; /**< Reason for mode change @ref zb_zgp_mode_change_reason_t */

  /* b0 - if 1 - start comm/stop comm by gp_sink_commissioning_mode request
   * b1 - if 1 - unicast proxy commissioning mode, otherwise - broadcast mode
   * b7-b15 - gp_sink_commissioning_mode options */
  zb_uint16_t               comm_mode_opt;

  zgp_approve_comm_params_t app_comm_params;    /**< Commissioning (or Pairing Configuration) params for Application approval */
  zb_bufid_t                pairing_conf_buf;   /**< Reference to buffer with GP Pairing Configuration command */

  /* new Sink table, unified with Proxy table */
  zb_zgp_sink_table_t       table;

  #define ZB_ZGP_APP_TBL_SIZE ZB_ZGP_SINK_TBL_SIZE
  zgp_runtime_app_tbl_ent_t app_table[ZB_ZGP_APP_TBL_SIZE];

  zgp_runtime_app_description_ctx_t app_descr_ctx;

  /* ZGP InvolveTC (A.3.3.2.6 gpsSecurityLevel attribute)

    According to the current version of the specification, sinks joining a distributed Zigbee network
    or joining using the default Trust Centre Link Key SHALL set this bit to 0b0.
    Sinks joining the Zigbee network using IC-based unique link key SHALL set this bit to 0b1

    We use this bitfield just to remember the join type until the authorized_signal will be generated.

    The procedure is:

    1. Joiner receives Transport Key in zb_aps_in_transport_key()
       and we see what key type is for the provisioning key.
       It calls zb_zgp_notification_network_join_begins() with the flag indicating whether the key was IC based or not.
    2. Joiner finalize tclk updation by zdo_secur_update_tclk_done() and calls zb_zgp_notification_network_join_done()
  */
  zb_bitfield_t ic_based_join_type:1;
  zb_bitfield_t aligned:7;
} zb_zgp_sink_ctx_t;

extern zb_zgp_sink_ctx_t zb_zgp_sink_ctx;
#define ZGP_SINK_CTX() zb_zgp_sink_ctx

zb_ret_t zgp_sink_table_write(zb_zgpd_id_t *zgpd_id, zgp_tbl_ent_t *ent);
zb_ret_t zgp_sink_table_read(zb_zgpd_id_t *zgpd_id, zgp_tbl_ent_t *ent);
zb_ret_t zgp_sink_table_read_by_idx(zb_uint_t idx, zgp_tbl_ent_t *ent);
zb_ret_t zgp_sink_table_idx(zb_zgpd_id_t *zgpd_id, zb_uint_t *idx);
zb_ret_t zgp_sink_table_del(zb_zgpd_id_t *zgpd_id);
zb_uint32_t zgp_sink_table_get_security_counter(zb_zgpd_id_t *zgpd_id);
zb_uint32_t zgp_sink_table_get_dup_counter(zb_zgpd_id_t *zgpd_id);
zb_ret_t zgp_sink_table_restore_security_counter(zb_zgpd_id_t *zgpd_id);
zb_ret_t zgp_sink_table_set_security_counter(zb_zgpd_id_t *zgpd_id, zb_uint32_t counter);
void zgp_sink_get_lqi_rssi(zb_zgpd_id_t *zgpd_id, zb_uint8_t *lqi_p, zb_int8_t *rssi_p);
void zgp_sink_set_lqi_rssi(zb_zgpd_id_t *zgpd_id, zb_uint8_t lqi, zb_int8_t rssi);
zb_bool_t zb_zgp_is_sink_table_empty(void);
zb_uint8_t zb_zgp_sink_table_non_empty_entries_count(void);
zb_bool_t zb_zgp_sink_table_get_entry_by_non_empty_list_index(zb_uint8_t index, zgp_tbl_ent_t *ent);

#define ZGP_CACHED_SINK_ENTRY() ZGP_SINK_CTX().table.base.cached

#define ZGP_INVALID_MATCH_DEV_TABLE_IDX 0xFF

zgp_runtime_app_tbl_ent_t *zb_zgp_alloc_app_tbl_ent_by_id(zb_zgpd_id_t *zgpd_id_p);
zgp_runtime_app_tbl_ent_t *zb_zgp_alloc_app_tbl_ent_with_switch_info_by_id(zb_zgpd_id_t *zgpd_id_p, zb_gpdf_comm_switch_info_t switch_info);
zgp_runtime_app_tbl_ent_t *zb_zgp_get_app_tbl_ent_by_alias(zb_uint16_t addr);
zgp_runtime_app_tbl_ent_t *zb_zgp_get_app_tbl_ent_by_id(zb_zgpd_id_t *zgpd_id_p);
void zb_zgp_erase_app_table_ent_by_id(zb_zgpd_id_t *zgpd_id_p);
void zb_zgp_erase_app_tbl_ent(zgp_runtime_app_tbl_ent_t *ent);
zgp_report_desc_t *zb_zgp_get_report_desc_from_app_tbl(zb_zgpd_id_t *zgpd_id_p, zb_uint8_t report_idx);
zb_uint32_t zb_zgp_app_desc_receive_reports_count(const zgp_runtime_app_tbl_ent_t *ent);

typedef ZB_PACKED_PRE struct zb_zgp_gp_notification_req_s
{
  zb_uint16_t            options;
  zb_zgpd_addr_t         zgpd_addr;
  zb_uint8_t             endpoint;
  zb_uint32_t            gpd_sec_frame_counter;
  zb_uint8_t             gpd_cmd_id;
  /* +1 bytes for payload size placed at beginning buffer */
  zb_uint8_t             payload[MAX_ZGP_CLUSTER_GPDF_PAYLOAD_SIZE+1];
  zb_zgp_gp_proxy_info_t proxy_info;
}
ZB_PACKED_STRUCT zb_zgp_gp_notification_req_t;

enum zb_zgp_pairing_conf_actions_send_pairing_e
{
  ZGP_PAIRING_CONF_NO_SEND_PAIRING,
  ZGP_PAIRING_CONF_SEND_PAIRING
};

typedef ZB_PACKED_PRE struct zb_zgp_gp_pairing_conf_s
{
  zb_uint8_t     actions;
  zb_uint16_t    options;
  zb_zgpd_addr_t zgpd_addr;
  zb_uint8_t     endpoint;
  zb_uint8_t     device_id;
  zb_uint8_t     frwd_radius;
  zb_uint8_t     num_paired_endpoints;
  zb_uint8_t     paired_endpoints[ZB_ZGP_MAX_PAIRED_ENDPOINTS];
  zb_uint8_t     app_info;

  union
  {
    /* A.3.3.4.6.7, Table 35
     * Fields for GP Pairing Configuration with action = 0b101.
     * They need to be put separately since most fields common for
     * other actions are forbidden for this one.
     */
    struct app_descr_flds_s
    {
      zb_uint8_t total_num_of_reports;
      zb_uint8_t num_of_reports;
      zgp_report_desc_pairing_config_t reports[ZB_ZGP_APP_DESCR_REPORTS_NUM];
    } app_descr;

    /* A.3.3.4.6.7, Table 35
     * Fields for GP Pairing Configuration with actions 0b000-0b100
     */
    struct actions_flds_s
    {
      zgp_pair_group_list_t sgrp[ZB_ZGP_MAX_SINK_GROUP_PER_GPD];
      zb_uint16_t    assigned_alias;
      zb_uint8_t     sec_options;
      zb_uint32_t    sec_frame_counter;
      zb_uint8_t     key[ZB_CCM_KEY_SIZE];
      zb_uint16_t    manuf_id;
      zb_uint16_t    model_id;
      zb_zgp_gpd_cmds_list_t gpd_cmds_list;
      zb_zgp_cluster_list_t cl;
      zb_gpdf_comm_switch_info_t switch_info;
    } action_flds;

  } u;
}
ZB_PACKED_STRUCT zb_zgp_gp_pairing_conf_t;

typedef ZB_PACKED_PRE struct zb_zgp_gp_sink_comm_mode_s
{
  zb_uint8_t     options;
  zb_uint16_t    gpm_addr_for_sec;
  zb_uint16_t    gpm_addr_for_pair;
  zb_uint8_t     sink_endpoint;
}
ZB_PACKED_STRUCT zb_zgp_gp_sink_comm_mode_t;

/**
 * @brief Convert GPDF packet to ZCL packet (packets)
 *
 * @param buf_ref [in] Reference to buffer with GPDF packet.
 *                   Buffer parameter contains filled @ref zb_gpdf_to_zcl_info_t struct
 */
void zb_zgp_gpdf_to_zcl(zb_cb_param_t buf_ref);

zb_ret_t zb_zgp_get_next_point_descr(zb_uint8_t **rpos, zb_uint8_t *max_pos, zgp_data_point_desc_t *point_desc);

/**
 * @brief ZGP Command type related to mapping table iterating
 *
 */
typedef enum zb_zgp_command_type_e
{
  ZGP_COMMAND_TYPE_NEW = 0,       /**< Command type is unknown at the moment, used for first iteration */
  ZGP_COMMAND_TYPE_UNDEFINED,     /**< GPD Command ID wasn't found, using 0xFF for further translations */
  ZGP_COMMAND_TYPE_REGULAR        /**< GPD Command ID was found, using actual code for further translations */
} zb_zgp_command_type_t;

/**
 * @brief Mapping table iteration auxiliary struct
 *
 */
typedef ZB_PACKED_PRE struct zb_zgp_mapping_table_iterator_s
{
  zb_uint16_t   index;  /**< Mapping table index for next iteration*/
  zb_uint8_t    command_type; /** Command type @ref zb_zgp_command_type_t */
} ZB_PACKED_STRUCT zb_zgp_mapping_table_iterator_t;

/**
 * @brief Set new value of mapping table iterator
 *
 */
#define ZGP_MAPPING_TABLE_SET_ITERATOR(iterator, index_, type) \
  (iterator)->index = (index_); \
  (iterator)->command_type = (type);

#ifdef ZB_CERTIFICATION_HACKS
typedef struct zgp_sink_cert_hacks_s
{
  zb_bitfield_t gp_sink_use_assigned_alias_for_dgroup_commissioning:1; /*!< If set to 1, Sink will use assignead alias
                                                                        *  instead derived alias for
                                                                        *  next commissioning process */
  zb_bitfield_t gp_sink_replace_sec_lvl_on_pairing:1;  //replace sec_lvl on pairing
  zb_bitfield_t gp_sink_sec_lvl_on_pairing:2;
  zb_uint16_t   gp_sink_assigned_alias;
  zb_uint16_t   gp_sink_pairing_dest;                  /*!< destination of GP pairing, by default is
                                                        * 0xFFFD */
} zgp_sink_cert_hacks_t;

zgp_sink_cert_hacks_t* zb_zgp_sink_cert_hacks_get(void);
extern zgp_sink_cert_hacks_t zb_zgp_sink_cert_hacks;

#define ZGP_SINK_CERT_HACKS() zb_zgp_sink_cert_hacks
#endif  /* ZB_CERTIFICATION_HACKS */

/**
 * @brief Check that Sink functionality is linked
 *
 * @return ZB_FALSE in case it is weak function
 *         ZB_TRUE if Sink functionality is linked
 */
zb_bool_t zb_zgp_sink_is_linked(void);

/**
 * @brief Check that Sink functionality is available in runtime
 *
 * @return ZB_FALSE in case it is disabled by device role
 *         ZB_TRUE if Sink functionality is available
 */
zb_bool_t zb_zgp_sink_is_available(void);

/**
 * @brief Sink initialization
 *
 */
void zb_zgp_sink_init(void);
zb_ret_t zgp_sink_table_init();
zb_bool_t age_sink_table();

void zb_zgp_sink_set_default_endpoint_values(zb_af_endpoint_desc_t * gp_ep);

/**
 * @brief Handle GP Notification command
 *
 * @param param   [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.4.1
 */
zb_ret_t zgp_sink_handle_gp_notification_cmd(zb_bufid_t param);

/**
 * @brief Handle GP Commissioning Notification command
 *
 * @param param   [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.4.3
 */
zb_ret_t zgp_sink_handle_gp_comm_notification_cmd(zb_bufid_t param);

/**
 * @brief Handle GP Sink Commissioning Mode command
 *
 * @param param   [in]  Buffer reference
 * @param status  [out] ZCL status
 *
 * @see ZGP spec, A.3.3.4.8
 */
zb_ret_t zgp_sink_handle_gp_sink_commissioning_mode_cmd(zb_bufid_t param, zb_uint8_t *status);

/**
 * @brief Handle GP Pairing Configuration command
 *
 * @param param   [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.4.6
 */
zb_ret_t zgp_sink_handle_gp_pairing_configuration_cmd(zb_bufid_t param);

/**
 * @brief Handle GP Sink Table Request command, perform sink table response
 *
 * @param param   [in]  Buffer reference
 *
 * @see ZGP spec, A.3.3.4.7
 */
zb_ret_t zgp_sink_handle_sink_table_request_cmd(zb_bufid_t param);

zb_ret_t zgp_sink_handle_read_sink_table(zb_bufid_t param);

void zb_gp_sink_data_indication(zb_cb_param_t param);
void zb_gp_sink_mlme_get_cfm_cb(zb_bufid_t param);
void zb_gp_sink_mlme_set_cfm_cb(zb_bufid_t param);

void zb_zgps_app_descr_timeout(zb_cb_param_t param);

/**
 * @brief Accept/reject gp pairing configuration
 *
 * @param accept     [in]  ZB_TRUE  - accepted
 *                         ZB_FALSE - rejected
 */
void zgp_sink_accept_gp_pairing_configuration(zb_bool_t accept);

void zb_zgp_handle_app_descr_init_values(zb_zgpd_id_t *zgpd_id_p);
void zb_zgp_init_app_descr_handler(zb_zgpd_id_t *zgpd_id, zb_uint32_t sec_cnt);

void zb_zgps_unbind_aps_group_for_aliasing(zb_zgp_sink_tbl_ent_t *ent);

zb_ret_t zgp_sink_table_enumerate(zb_zgp_ent_enumerate_ctx_t *ctx, zgp_tbl_ent_t *ent);

zb_uint8_t zb_zgp_sink_mode_get(void);

#define ZB_ZGP_SET_SINK_COMM_MODE(opt) \
  ZGP_SINK_CTX().comm_mode_opt = (1 | (ZGP_SINK_CTX().comm_mode_opt & 2) | ((opt) << 8))

#define ZB_ZGP_CLR_SINK_COMM_MODE()\
  ZGP_SINK_CTX().comm_mode_opt = (ZGP_SINK_CTX().comm_mode_opt & 2)

#define ZB_ZGP_SET_PROXY_COMM_MODE_COMMUNICATION(cm)\
  ZGP_SINK_CTX().comm_mode_opt = ((ZGP_SINK_CTX().comm_mode_opt & ~2) | ((!!(cm)) << 1))

#define ZB_ZGP_SINK_IS_SEND_ENTER_OR_LEAVE_FOR_PROXIES()\
  (((ZGP_SINK_CTX().comm_mode_opt & 1) == 0) || ((ZGP_SINK_CTX().comm_mode_opt & 1) == 1 &&\
                                             (ZB_ZGP_GP_SINK_COMM_MODE_GET_INV_PROXIES((ZGP_SINK_CTX().comm_mode_opt & 0xFF00) >> 8))))

#define ZB_ZGP_GET_SINK_COMM_MODE_START_STOP_CAUSE() \
  ((ZGP_SINK_CTX().comm_mode_opt) & 1)

#define ZGP_PROXY_COMM_MODE_IS_UNICAST()\
  ((ZGP_SINK_CTX().comm_mode_opt >> 1) & 1)

/*! @} */

#endif  /* ZB_ENABLE_ZGP_SINK */
#endif /* ZB_ZGP_SINK_H */
