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
/* PURPOSE: PTA level for Multipan Low-Level Radio API and MAC LL
*/

#ifndef ZB_PTA_H
#define ZB_PTA_H 1

/** @addtogroup zb_pta
  * @{
  */



/*
Some timings for PTA sim for nsng, in us. Note: nsng only!
 */

#define ZB_NSNG_GRANT_WAIT_MAX 100u

#define ZB_PTA_CCA_GRANT_SYNC_WAIT 50u
#define ZB_PTA_ZGP_GRANT_SYNC_WAIT 60u
#define ZB_PTA_GRANT_SYNC_RX_WAIT 50u

/* PTRA API for multipan and MAC LL */

/**
   Check that PTA is now enabled at runtime
 */
zb_bool_t zb_pta_is_enabled(void);

/**
   Check GRANT line is now active
 */
zb_bool_t zb_pta_check_grant(void);

/**
   Set REQ and, maybe, PRI lines, sync wait for GRANT, register GRANT change callback

   @param for_tx - if true, we are about to start TX operation, else RX (optionally with ACK send)
   @param pri - if true, PTA logic can do priority escalation if it is configured in
   @param grant_wait_us - sync wait for GRANT that number of us. That value can be 0, in that case grant_change_cb must be non-NULL. It must not be too big.
   @param grant_change_cb - callback to be called at GRANT line change. Can be NULL. If NULL, supposing grant_wait_us > 0. Note: both values can be filled

   @return true if it is ok to continue operation (GRANT is set), else false. If returned false, grant_change_cb may be called at GRANT line change
 */
zb_bool_t zb_pta_set_req(zb_bool_t for_tx, zb_bool_t pri, zb_uint32_t grant_wait_us, zb_callback_t grant_change_cb);

/**
   Cleat REQ and PRI lines
 */
void zb_pta_clear_req(void);

/**
   Get current state of GRANT line
 */
zb_bool_t zb_pta_get_state(void);


/* Interface for MAC PIB */

void zb_pta_set_state_pib(zb_bool_t enable);

void zb_pta_set_prio_pib(zb_uint8_t prio);

zb_uint8_t zb_pta_get_prio_pib(void);

void zb_pta_set_pta_options_pib(zb_uint8_t *options, zb_uint_t len);

void zb_pta_get_options_pib(zb_uint8_t *opt, zb_uint8_t *optlen);

/* Diagnostic counters */

/* getters */
zb_uint32_t zb_pta_get_pta_lo_pri_req(void);
zb_uint32_t zb_pta_get_pta_hi_pri_req(void);
zb_uint32_t zb_pta_get_pta_lo_pri_denied(void);
zb_uint32_t zb_pta_get_pta_hi_pri_denied(void);
zb_uint32_t zb_pta_get_pta_tx_aborted(void);
zb_uint32_t zb_pta_get_cca_retries(void);

/* setters */
void zb_pta_req_denied(void);
void zb_pta_tx_aborted(void);
void zb_pta_cca_retry(void);
void zb_pta_reset_counters(void);

/* Interface for osif. Functions to be called from the generic PTA logic */

void zb_pta_gpio_init(void);

void zb_pta_gpio_deinit(void);

void zb_pta_gpio_set_grant_change_cb(zb_callback_t grant_change_cb);

void zb_pta_gpio_set_req(zb_bool_t req, zb_bool_t pri);

zb_bool_t zb_pta_gpio_get_grant(void);

void zb_pta_gpio_wait_grant(zb_uint32_t grant_wait_us);

/* Routines specific for PTA simulation in nsng build */
/**
   Check that pta GRANT is set for transmitting.  That could be a parameter for
   zb_pta_gpio_wait_grant. But the knowledge of the operation type is not
   necessary for GPIO level at the real HW, so use that routine instead.
 */
zb_bool_t zb_pta_is_transmitting(void);

zb_bool_t zb_pta_is_no_cb(void);
/**
@}
*/


#endif  /* ZB_PTA_H */
