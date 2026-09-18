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
/* PURPOSE: Zigbee address management (internal)
*/

#ifndef ZB_ADDRESS_INTERNAL_H
#define ZB_ADDRESS_INTERNAL_H 1

/*! \addtogroup ZB_NWK_ADDR */
/*! @{ */

/*! @cond internals_doc */

/**
 * @brief Gets NVRAM page index for address location.
 *
 * Actually, addresses storage uses current NVRAM page to read and write addresses datasets.
 * The only exception is NVRAM migration procedure.
 * In that case all individual address datasets will be discarded and
 * the full address map dataset will be written.
 * To perform migration procedure it is needed to read individual addresses from the previous page.
 *
 * @param addr_location address location
 */
#define ZB_ADDRESS_LOCATION_NVRAM_GET_PAGE(addr_location) \
  (ZB_U2B(ZB_NVRAM().migration_in_progress) ? ZB_NVRAM_MIGRATION_PREV_PAGE() : ZB_NVRAM().current_page)
#define ZB_ADDRESS_LOCATION_NVRAM_GET_OFFSET(addr_location) ((addr_location) * (zb_uint32_t)4U)

#define ZB_ADDRESS_LOCATION_VALUE(nvram_page, nvram_offset) ((zb_address_location_t)((nvram_offset) / 4U))


void zb_address_dump_redirs(void);

void zb_address_entry_clear(zb_address_ieee_ref_t ref);

/**
 * @brief Inplace alternative of \ref zb_address_by_ieee_func.
 * If address entry with given IEEE address is not found,
 * the function creates entry with given IEEE address location in NVRAM.
 * The function is intended to create address entry with temporary NVRAM location
 * during NVRAM migration to prevent incremental datasets writing.
 *
 * @param ieee - IEEE device address
 * @param ieee_loc - IEEE address location in NVRAM
 * @param create - if TRUE, create address entry if it does not exist
 * @param lock - if TRUE, lock address entry
 * @param ref_p - (out) address reference
 *
 * @return status code
 */
zb_ret_t zb_address_by_ieee_inplace_func(
  TRACE_ADDR_PROTO
  const zb_ieee_addr_t ieee,
  zb_address_location_t ieee_loc,
  zb_bool_t create,
  zb_bool_t lock,
  zb_address_ieee_ref_t *ref_p);

#define zb_address_by_ieee_inplace(ieee, ieee_loc, create, lock, ref_p) \
  zb_address_by_ieee_inplace_func(TRACE_ADDR_CALL (ieee), (ieee_loc), (create), (lock), (ref_p))

/* IEEE addresses storage */

void zb_addr_map_read_ieee_addr_nvram(
  zb_address_location_t addr_location,
  zb_ieee_addr_t out_ieee_addr);

void zb_addr_map_update_addr_nvram(
  zb_address_ieee_ref_t addr_ref,
  const zb_ieee_addr_t ieee_addr,
  zb_address_location_t *out_addr_location);

void zb_addr_map_delete_addr_nvram(
  zb_address_ieee_ref_t addr_ref);

zb_bool_t zb_addr_map_is_ieee_equal_nvram(
  const zb_address_location_t addr_location,
  const zb_ieee_addr_t ieee_addr_to_cmp);

zb_bool_t zb_addr_map_is_ieee_equal_or_not_set_nvram(
  const zb_address_location_t addr_location,
  const zb_ieee_addr_t ieee_addr_to_cmp);

zb_bool_t zb_addr_map_is_ieee_set_nvram(
  zb_address_location_t addr_location);

zb_bool_t zb_addr_map_is_ieee_zero_nvram(
  zb_address_location_t addr_location);

zb_bool_t zb_addr_map_is_ieee_unknown_nvram(
  zb_address_location_t addr_location);


#define ZB_ADDR_MAP_STORAGE_READ_IEEE(addr_location, out_ieee_addr) \
  zb_addr_map_read_ieee_addr_nvram((addr_location), (out_ieee_addr))

#define ZB_ADDR_MAP_STORAGE_UPDATE_ADDR(addr_ref, ieee_addr, out_addr_location) \
  zb_addr_map_update_addr_nvram((addr_ref), (ieee_addr), (out_addr_location))

#define ZB_ADDR_MAP_STORAGE_REMOVE_ADDR(addr_ref) \
  zb_addr_map_delete_addr_nvram((addr_ref))

#define ZB_ADDR_MAP_STORAGE_IS_IEEE_EQUAL(addr_location, ieee_addr_to_cmp) \
  zb_addr_map_is_ieee_equal_nvram((addr_location), (ieee_addr_to_cmp))

#define ZB_ADDR_MAP_STORAGE_IS_IEEE_EQUAL_OR_NOT_SET(addr_location, ieee_addr_to_cmp) \
  zb_addr_map_is_ieee_equal_or_not_set_nvram((addr_location), (ieee_addr_to_cmp))

#define ZB_ADDR_MAP_STORAGE_IS_IEEE_SET(addr_location) \
  zb_addr_map_is_ieee_set_nvram((addr_location))

#define ZB_ADDR_MAP_STORAGE_IS_IEEE_ZERO(addr_location) \
  zb_addr_map_is_ieee_addr_zero_nvram((addr_location))

#define ZB_ADDR_MAP_STORAGE_IS_IEEE_UNKNOWN(addr_location) \
  zb_addr_map_is_ieee_addr_unknown_nvram((addr_location))

#if defined(ZB_DEBUG_ADDR)
void zb_address_print_addr_table(void);
#endif /* ZB_DEBUG_ADDR */

#ifdef ZB_DEBUG_ADDR_EXT
void zb_address_verify_no_stale_refs(zb_address_ieee_ref_t addr_ref, zb_bool_t verify_delayed);
#endif /* ZB_DEBUG_ADDR_EXT */

/*! @endcond */

/*! @} */


#endif /* ZB_ADDRESS_INTERNAL_H */
