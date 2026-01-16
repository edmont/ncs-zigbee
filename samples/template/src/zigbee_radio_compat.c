/**
 * Zigbee Radio Driver Compatibility Patch
 * 
 * This file provides wrapper functions for Zigbee radio to avoid symbol
 * conflicts with OpenThread L2 layer during protocol switching.
 * 
 * The Zigbee radio functions have been renamed in zb_nrf_transceiver.c:
 *   - ieee802154_init() → zigbee_ieee802154_init()
 *   - ieee802154_handle_ack() → zigbee_ieee802154_handle_ack()
 * 
 * This file provides weak wrappers that default to Zigbee but can be
 * overridden by the protocol manager for runtime switching.
 */

#include <zephyr/net/net_if.h>
#include <zephyr/net/net_pkt.h>

/* Forward declare the renamed Zigbee implementations */
extern void zigbee_ieee802154_init(struct net_if *iface);
extern enum net_verdict zigbee_ieee802154_handle_ack(struct net_if *iface, struct net_pkt *pkt);

/* Weak wrappers that can be overridden for protocol switching */
__weak void ieee802154_init(struct net_if *iface)
{
    /* Default to Zigbee during startup */
    zigbee_ieee802154_init(iface);
}

__weak enum net_verdict ieee802154_handle_ack(struct net_if *iface, struct net_pkt *pkt)
{
    /* Default to Zigbee during startup */
    return zigbee_ieee802154_handle_ack(iface, pkt);
}
