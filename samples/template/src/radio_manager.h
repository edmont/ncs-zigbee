/**
 * Radio Manager for Protocol Switching
 * 
 * This module manages the IEEE 802.15.4 radio shared between Zigbee and OpenThread/Matter.
 * Protocols are never active simultaneously - the radio is switched between them.
 * 
 * Protocol State Machine:
 *   ZIGBEE_ACTIVE → (Matter commissioning) → COMMISSIONING → THREAD_ACTIVE
 */

#ifndef RADIO_MANAGER_H
#define RADIO_MANAGER_H

#include <zephyr/kernel.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Protocol states for radio management
 */
typedef enum {
    RADIO_PROTOCOL_NONE = 0,       ///< Radio not initialized
    RADIO_PROTOCOL_ZIGBEE,         ///< Zigbee active on radio
    RADIO_PROTOCOL_COMMISSIONING,  ///< Transitioning (BLE commissioning)
    RADIO_PROTOCOL_THREAD          ///< Thread/Matter active on radio
} radio_protocol_t;

/**
 * Get current active protocol on the radio
 * @return Current protocol state
 */
radio_protocol_t radio_manager_get_active_protocol(void);

/**
 * Initialize radio for Zigbee operation
 * @return 0 on success, negative error code on failure
 */
int radio_manager_start_zigbee(void);

/**
 * Stop Zigbee and prepare for protocol switch
 * @return 0 on success, negative error code on failure
 */
int radio_manager_stop_zigbee(void);

/**
 * Initialize radio for Thread/OpenThread operation
 * @return 0 on success, negative error code on failure
 */
int radio_manager_start_thread(void);

/**
 * Stop Thread and prepare for protocol switch
 * @return 0 on success, negative error code on failure
 */
int radio_manager_stop_thread(void);

#ifdef __cplusplus
}
#endif

#endif /* RADIO_MANAGER_H */
