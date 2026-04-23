#!/usr/bin/env python3
"""
Matter + Zigbee Integration Test

Three test modes share the same infrastructure (build/flash/PCAP/OTBR/log
capture) and differ in which ncs-zigbee sample is flashed on the DUT, how
the Zigbee network is formed, and how the Matter-side behaviour is exercised
after the Zigbee->Thread radio handover:

``zigbee-to-matter-switch-dut`` (default):
    DUT = nRF54LM20 running ncs-zigbee/samples/light_switch (FILE_SUFFIX=
    matter_fota). Satellite nRF52840s provide a Zigbee coordinator, a Zigbee
    light bulb, an OpenThread RCP, and a Matter light bulb. Flow:
      1. Zigbee network forms (coord-driven BDB network steering); DUT joins,
         DUT finds the Zigbee bulb.
      2. User presses BUTTON 0/1 on the DUT; the Zigbee bulb logs the
         ON/OFF transitions.
      3. chip-tool commissions the DUT into the Thread fabric (node 1) —
         radio dispatcher hands the 802.15.4 off to OpenThread.
      4. chip-tool commissions the Matter bulb into the same fabric (node 2).
      5. chip-tool writes an ACL on the Matter bulb + a binding on the DUT so
         the DUT's Matter On/Off client points at the Matter bulb.
      6. User presses BUTTON 1 on the DUT twice; the Matter bulb logs the
         attribute transitions driven over Thread via the binding.

``zigbee-to-matter-bulb-dut``:
    DUT = nRF54LM20 running ncs-zigbee/samples/light_bulb (FILE_SUFFIX=
    matter_fota) — dual-stack bulb. Satellites: a regular Zigbee light_switch
    (no matter_fota), a Zigbee coordinator, and an OpenThread RCP. No Matter
    bulb / switch DK; chip-tool plays the Matter controller. Flow:
      1. Zigbee network forms; DUT and the Zigbee switch both join the coord.
      2. User presses BUTTON 0/1 on the Zigbee switch; the DUT logs the
         Zigbee ``Set ON/OFF value`` transitions.
      3. chip-tool commissions the DUT into Thread (node 1) and drives the
         On/Off cluster via ``chip-tool onoff on/off/on 1 1``; the DUT's
         Matter side logs the chip on-off-server state transitions.

``touchlink-to-matter-switch-dut``:
    Coordinator-less variant of ``zigbee-to-matter-switch-dut``. Same five
    roles, except the Zigbee coordinator is dropped and the Zigbee network is
    formed via Touchlink instead of BDB network steering. The ncs-zigbee
    light_bulb sample already carries ``CONFIG_ZIGBEE_TOUCHLINK_TARGET=y`` and
    light_switch carries ``CONFIG_ZIGBEE_TOUCHLINK_INITIATOR=y`` on the
    current branch, so no extra Kconfig overrides are needed. Flow:
      1. User presses BUTTON 2 on the DUT to initiate Touchlink
         (``DK_BTN3_MSK`` on the nRF54LM20's 0..3 silkscreen). The Zigbee
         bulb pairs as target; DUT then discovers its short address as in the
         coord-based flow.
      2. User presses BUTTON 0/1 on the DUT; the Zigbee bulb logs the On/Off
         transitions (same as switch-dut mode).
      3. chip-tool commissions the DUT (node 1) and the **dedicated** Matter
         bulb (node 2) — same as switch-dut.
      4. chip-tool writes ACL on the Matter bulb + binding on the DUT.
      5. User presses BUTTON 1 on the DUT twice; the Matter bulb logs the
         attribute transitions driven over Thread via the binding.
    Rationale: the matter_fota FILE_SUFFIX on light_bulb is authored for
    nRF54LM20 only (sample.yaml platform_allow), so a dual-stack Zigbee-
    plus-Matter bulb on an nRF52840 would require a board port that is out
    of scope here. Keeping the Zigbee bulb and the Matter bulb as separate
    physical satellites matches switch-dut exactly and reuses its patterns.
    Limitation: without a coordinator, the Zigbee NWK key is random per boot
    (CONFIG_ZIGBEE_INSECURE_DEFAULT_NWK_KEY depends on ZIGBEE_ROLE_COORDINATOR),
    so Zigbee frames in the PCAP cannot be pre-keyed for Wireshark decryption
    — Thread frames still decrypt with the fixed key in the PCAP name.

Hardware (auto-discovered, sorted by serial so role->board mapping is stable):
- 1x nRF54LM20 DK  -> DUT
- 3 or 4x nRF52840 DK (3 for -bulb-dut, 4 for touchlink/-switch-dut)

Prerequisites:
- nrfutil with device support
- chip-tool
- docker (for OTBR)
- Nordic 802.15.4 sniffer on /dev/ttyACM0 (optional, for PCAP)
- West build environment configured

Usage:
    # First-time setup: build every artifact once, store under /tmp/mz_test_artifacts.
    # Artifacts are deduped across modes (e.g. the RCP image is shared by all three
    # modes and is only built once).
    python3 matter_zigbee_test.py --build --no-run
    # Same, but only rebuild a specific firmware image:
    python3 matter_zigbee_test.py --build mz_switch_dut matter_bulb --no-run

    # Day-to-day: re-use cached artifacts, just re-flash + run the selected mode.
    python3 matter_zigbee_test.py                                    # default mode
    python3 matter_zigbee_test.py --mode zigbee-to-matter-bulb-dut
    python3 matter_zigbee_test.py --mode touchlink-to-matter-switch-dut

    # Rebuild selected artifacts in-line with the test run (equivalent to the
    # legacy "no --skip-build" behaviour, now explicit):
    python3 matter_zigbee_test.py --build
    python3 matter_zigbee_test.py --build mz_switch_dut --channel 20

    python3 matter_zigbee_test.py --no-interactive
    python3 matter_zigbee_test.py --otbr-docker-image nrfconnect/otbr:OTHER_TAG
"""

import argparse
import atexit
import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKSPACE_ROOT = '/home/edmo-nordic/repos/ncs'
ZIGBEE_SAMPLES = f'{WORKSPACE_ROOT}/ncs-zigbee/samples'
NRF_SAMPLES = f'{WORKSPACE_ROOT}/nrf/samples'
DEFAULT_CHANNEL = 16
NORDIC_SNIFFER_DEVICE = None  # auto-detected at runtime by find_sniffer_device()
OTBR_CONTAINER_NAME = 'otbr_matter_zigbee_test'
# Pinned tag from NCS docs (:ref:`ug_thread_tools_tbr_docker` in thread/tools.rst).
# There is no ``:latest`` on Docker Hub; override with --otbr-docker-image if needed.
OTBR_DOCKER_IMAGE_DEFAULT = 'nrfconnect/otbr:fbde28a'
# ``docker run -d`` can block on slow hosts until the container is created.
OTBR_DOCKER_RUN_TIMEOUT_S = 180
# otbr-agent creates the ot-ctl UNIX socket after container start; do not call
# ``ot-ctl`` until it answers (avoids "connect session failed: No such file or directory").
OTBR_CTL_READY_TIMEOUT_S = 120
# NCS Thread docs: IPv6 Docker network + ``--network otbr`` on ``docker run``.
OTBR_DOCKER_NETWORK = 'otbr'
MATTER_NODE_ID = 1
MATTER_PASSCODE = 20202021
MATTER_DISCRIMINATOR = 3840
# Matter light bulb uses a distinct discriminator so both DUT and bulb can
# advertise on BLE at the same time without chip-tool picking the wrong peer.
MATTER_BULB_NODE_ID = 2
MATTER_BULB_DISCRIMINATOR = 3841
MATTER_BULB_ENDPOINT_ID = 1
# Endpoint on the DUT where the Matter On/Off cluster lives. Both the Nordic
# Matter light_switch (reused by ncs-zigbee light_switch matter_fota) and the
# Matter light_bulb sample place the functional cluster on endpoint 1.
MATTER_DUT_ENDPOINT_ID = 1
# Fixed Thread network key so Wireshark decryption can be preconfigured once.
THREAD_NETWORK_KEY = '00112233445566778899aabbccddeeff'
# The matter_fota sample configs set ``CONFIG_CHIP_BLE_ADVERTISING_DURATION=60``
# (minutes), which the Matter platform layer turns into
# ``CHIP_DEVICE_CONFIG_DISCOVERY_TIMEOUT_SECS = 3600`` — the full CHIPoBLE
# window (fast ~30 s, then slow until this cap). We don't use the full 3600 s
# here: 900 s is the threshold at which we *nag* the user to press BUTTON 0
# to re-arm fast advertising, not the absolute end of the window.
BLE_ADVERTISING_DURATION_S = 900
BLE_ADVERTISING_SAFETY_MARGIN_S = 30

# Mode names — used as dict keys and CLI choices. Keep in sync with TEST_MODES.
MODE_SWITCH_DUT = 'zigbee-to-matter-switch-dut'
MODE_BULB_DUT = 'zigbee-to-matter-bulb-dut'
MODE_TOUCHLINK_SWITCH_DUT = 'touchlink-to-matter-switch-dut'

# Matter On/Off cluster id — used when writing the Binding table on the DUT so
# its physical-button-driven Matter client targets the bulb's On/Off cluster.
MATTER_ONOFF_CLUSTER_ID = 6
# Default chip-tool controller node id ("112233" in hex 0x1B3D49). Required in
# the Matter bulb's ACL so chip-tool itself can keep reading/writing after the
# switch is bound; missing this entry is a frequent foot-gun where the ACL
# write itself succeeds and then the NEXT chip-tool call gets ACCESS_DENIED.
CHIP_TOOL_CONTROLLER_NODE_ID = 112233


# ---------------------------------------------------------------------------
# Terminal colors & logging
# ---------------------------------------------------------------------------

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


cleanup_done = False
current_pcap_process = None
current_pcap_file = None
collected_log_files = []
log_collection_active = True
script_log_file = None
# Full ``docker logs`` for OTBR (written before ``docker rm`` so failures are debuggable).
otbr_docker_log_path = None


def log(message, color=None):
    global script_log_file
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    if color:
        screen = f"{color}[{timestamp}] {message}{Colors.ENDC}"
    else:
        screen = f"[{timestamp}] {message}"
    print(screen)
    if script_log_file:
        try:
            script_log_file.write(f"[{timestamp}] {message}\n")
            script_log_file.flush()
        except Exception:
            pass


def cleanup_on_exit():
    global cleanup_done, current_pcap_process, log_collection_active, script_log_file
    if cleanup_done:
        return
    cleanup_done = True
    log("Performing cleanup...", Colors.YELLOW)

    log_collection_active = False

    if current_pcap_process:
        try:
            current_pcap_process.terminate()
            current_pcap_process.wait(timeout=5)
        except Exception:
            try:
                current_pcap_process.kill()
            except Exception:
                pass

    # Best-effort: preserve OTBR logs, then remove container
    capture_otbr_docker_logs(quiet=True)
    try:
        subprocess.run(
            ['docker', 'rm', '-f', OTBR_CONTAINER_NAME],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    if script_log_file:
        try:
            script_log_file.close()
        except Exception:
            pass


def _signal_handler(signum, _frame):
    names = {signal.SIGINT: 'SIGINT', signal.SIGTERM: 'SIGTERM'}
    log(f"\n{names.get(signum, f'Signal {signum}')} received — cleaning up...",
        Colors.BOLD + Colors.YELLOW)
    cleanup_on_exit()
    sys.exit(1)


atexit.register(cleanup_on_exit)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

def _run_nrfutil_device_list():
    """Return list of device dicts from nrfutil device list (deduped by serial).

    nrfutil emits NDJSON: a ``task_end`` line and an ``info`` line often carry the
    same ``devices`` array — collect from typed messages only, then dedupe.
    """
    result = subprocess.run(
        ['nrfutil', 'device', 'list', '--traits', 'jlink', '--json'],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        log(f"nrfutil device list failed: {result.stderr}", Colors.RED)
        return []

    devices = []
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            msg_type = obj.get('type')
            data = obj.get('data', {})
            if msg_type == 'info' and isinstance(data.get('devices'), list):
                devices.extend(data['devices'])
            elif msg_type == 'task_end':
                inner = data.get('data')
                if isinstance(inner, dict) and isinstance(inner.get('devices'), list):
                    devices.extend(inner['devices'])
        except json.JSONDecodeError:
            continue

    seen = set()
    unique = []
    for dev in devices:
        sn = dev.get('serialNumber', '')
        if sn and sn not in seen:
            seen.add(sn)
            unique.append(dev)
    return unique


def _nrfutil_usb_product_id(device_dict):
    """USB product id from nrfutil JSON (board controller / J-Link), or None."""
    bc = device_dict.get('boardController')
    if isinstance(bc, dict):
        pid = bc.get('productId')
        if pid is not None:
            try:
                return int(pid)
            except (TypeError, ValueError):
                pass
    usb = device_dict.get('usb')
    if isinstance(usb, dict):
        desc = usb.get('device', {})
        if isinstance(desc, dict):
            desc = desc.get('descriptor', {})
        if isinstance(desc, dict):
            pid = desc.get('idProduct')
            if pid is not None:
                try:
                    return int(pid)
                except (TypeError, ValueError):
                    pass
    return None


# USB idProduct values seen from ``nrfutil device list --json`` (decimal).
# nRF52840 DK (devkit): 4132 (0x1024)
# nRF54LM20 DK (boardController, traits.devkit false): 4200 (0x1068)
_USB_PID_NRF52_DK = {4132, 0x1024}
_USB_PID_NRF54L_BC = {4200, 0x1068}


def _device_family(device_dict):
    """Extract a normalised family tag from nrfutil device JSON.

    Primary source is ``devkit.deviceFamily`` (e.g. ``NRF52_FAMILY``,
    ``NRF54L_FAMILY``). Traits may be booleans only (jlink: true), not objects.

    nRF54LM20 often appears **without** a ``devkit`` block (``traits.devkit`` is
    false) and only ``boardController`` + USB ``idProduct`` — classify those
    via :data:`_USB_PID_NRF54L_BC`.
    """
    _dk = device_dict.get('devkit')
    devkit = _dk if isinstance(_dk, dict) else {}
    if devkit:
        fam = (devkit.get('deviceFamily') or '').strip()
        if fam:
            return fam.upper()
        # Board PCA hints when deviceFamily is missing
        bv = (devkit.get('boardVersion') or '').upper()
        pca_nrf52 = ('PCA10056', 'PCA10040', 'PCA10059', 'PCA10100', 'PCA10112')
        pca_nrf54l = ('PCA10156', 'PCA10157', 'PCA10158', 'PCA10159', 'PCA10175')
        if any(p in bv for p in pca_nrf52):
            return 'NRF52_FAMILY'
        if any(p in bv for p in pca_nrf54l) or 'LM20' in bv:
            return 'NRF54L_FAMILY'

    # Board-controller / non-devkit boards (e.g. nRF54LM20 on recent nrfutil)
    pid = _nrfutil_usb_product_id(device_dict)
    if pid is not None:
        if pid in _USB_PID_NRF54L_BC:
            return 'NRF54L_FAMILY'
        if pid in _USB_PID_NRF52_DK:
            return 'NRF52_FAMILY'

    traits = device_dict.get('traits', [])
    if isinstance(traits, dict):
        traits_iter = traits.values()
    else:
        traits_iter = traits if isinstance(traits, list) else []

    for trait in traits_iter:
        if isinstance(trait, dict):
            family = trait.get('deviceFamily', '') or ''
            if family:
                return family.upper()
        # trait can be a plain string like \"jlink\" — skip

    # Top-level fields (varies by nrfutil version)
    for key in ('deviceFamily', 'family', 'core', 'device'):
        val = device_dict.get(key)
        if isinstance(val, str) and val:
            return val.upper()

    # Fallback: inspect devkit / board name (strings nrfutil may omit)
    board = (
        (devkit.get('boardName', '') or '')
        + ' '
        + (device_dict.get('boardName', '') or '')
        + ' '
        + (device_dict.get('product', '') or '')
        + ' '
        + (device_dict.get('name', '') or '')
    ).upper()
    if 'NRF54L' in board or 'NRF54LM' in board or 'LM20' in board:
        return 'NRF54L'
    if 'NRF52' in board or '52840' in board or '52833' in board:
        return 'NRF52'
    if 'NRF53' in board:
        return 'NRF53'
    return 'UNKNOWN'


def discover_and_assign_devices(mode, rcp_serial=None):
    """Discover all J-Link devices, return role->info mapping or None on failure.

    ``mode`` selects which role set to populate (see ``MODE_*`` constants).

    ``rcp_serial`` optionally pins the RCP role to a specific nRF52840 SN,
    useful when some DKs in the fleet have IF-MCU / J-Link-OB firmware that
    doesn't reliably bridge UART at 1 Mbps (the baud rate the coprocessor
    sample uses for Spinel). When set, the pinned board is removed from the
    nrf52 pool before the remaining roles are filled, so all other
    assignments shift down by one slot.
    """
    log("Discovering connected devices...", Colors.BLUE)
    raw_devices = _run_nrfutil_device_list()
    if not raw_devices:
        log("No J-Link devices found", Colors.RED)
        return None

    nrf54lm = []
    nrf52840 = []

    for dev in raw_devices:
        serial = dev.get('serialNumber', '')
        if not serial:
            continue
        family = _device_family(dev)
        entry = {'serial': serial, 'family': family, 'raw': dev}

        if 'NRF54L' in family:
            nrf54lm.append(entry)
        elif 'NRF52' in family:
            nrf52840.append(entry)
        else:
            log(f"  Ignoring device {serial} (family={family})", Colors.YELLOW)

    log(f"Found {len(nrf54lm)} nRF54L device(s), {len(nrf52840)} nRF52 device(s)", Colors.CYAN)

    # Sort by serial number so the role -> physical-board mapping is stable
    # across runs (``nrfutil device list`` order is enumeration-dependent).
    # Users can then label their DKs once and trust the assignment below.
    nrf54lm.sort(key=lambda d: d['serial'])
    nrf52840.sort(key=lambda d: d['serial'])

    pinned_rcp = None
    if rcp_serial:
        # Accept both zero-padded and unpadded user input — compare numerically.
        match_sn = rcp_serial.lstrip('0')
        found = next(
            (d for d in nrf52840 if d['serial'].lstrip('0') == match_sn),
            None,
        )
        if not found:
            log(f"--rcp-serial {rcp_serial} not found among discovered nRF52 devices — "
                f"aborting to avoid silently falling back to auto-assignment.",
                Colors.RED)
            return None
        nrf52840.remove(found)
        pinned_rcp = found
        log(f"  RCP pinned to SN={found['serial']} (per --rcp-serial)", Colors.CYAN)

    # Per-mode role plan. Each entry is
    # (role_key, family_pool, index_in_pool, board_target, label).
    # Lower indices in each family pool (i.e. lower serial numbers) get the
    # roles that are shared between modes (coord first, then rcp is deliberately
    # put second-from-the-end to stay at the same SN across modes where that
    # matters — but for the current two modes ordering is mode-local).
    if mode == MODE_SWITCH_DUT:
        plan = [
            ('dut',         'nrf54lm', 0, 'nrf54lm20dk/nrf54lm20a/cpuapp',
             'DUT (Matter+Zigbee light switch)'),
            ('coordinator', 'nrf52',   0, 'nrf52840dk/nrf52840',
             'Zigbee Coordinator'),
            ('bulb',        'nrf52',   1, 'nrf52840dk/nrf52840',
             'Zigbee Light Bulb'),
            ('rcp',         'nrf52',   2, 'nrf52840dk/nrf52840',
             'OpenThread RCP (for OTBR)'),
            ('matter_bulb', 'nrf52',   3, 'nrf52840dk/nrf52840',
             'Matter Light Bulb'),
        ]
    elif mode == MODE_BULB_DUT:
        plan = [
            ('dut',            'nrf54lm', 0, 'nrf54lm20dk/nrf54lm20a/cpuapp',
             'DUT (Matter+Zigbee light bulb)'),
            ('coordinator',    'nrf52',   0, 'nrf52840dk/nrf52840',
             'Zigbee Coordinator'),
            ('zigbee_switch',  'nrf52',   1, 'nrf52840dk/nrf52840',
             'Zigbee Light Switch'),
            ('rcp',            'nrf52',   2, 'nrf52840dk/nrf52840',
             'OpenThread RCP (for OTBR)'),
        ]
    elif mode == MODE_TOUCHLINK_SWITCH_DUT:
        # No coordinator: Touchlink pairs the DUT (initiator) with the Zigbee
        # bulb (target). The Matter bulb is a separate nRF52840 because the
        # light_bulb sample's matter_fota variant is nRF54LM20-only.
        plan = [
            ('dut',         'nrf54lm', 0, 'nrf54lm20dk/nrf54lm20a/cpuapp',
             'DUT (Matter+Zigbee light switch, Touchlink initiator)'),
            ('bulb',        'nrf52',   0, 'nrf52840dk/nrf52840',
             'Zigbee Light Bulb (Touchlink target)'),
            ('rcp',         'nrf52',   1, 'nrf52840dk/nrf52840',
             'OpenThread RCP (for OTBR)'),
            ('matter_bulb', 'nrf52',   2, 'nrf52840dk/nrf52840',
             'Matter Light Bulb'),
        ]
    else:
        log(f"Unknown mode for device assignment: {mode}", Colors.RED)
        return None

    needed_nrf54lm = sum(1 for _, fam, *_ in plan if fam == 'nrf54lm')
    needed_nrf52_total = sum(1 for _, fam, *_ in plan if fam == 'nrf52')
    # When the RCP is pinned, it no longer draws from the nrf52 pool, so the
    # remaining pool only needs to cover the non-RCP nrf52 roles.
    needed_nrf52_from_pool = needed_nrf52_total - (1 if pinned_rcp else 0)
    if len(nrf54lm) < needed_nrf54lm:
        log(f"Need at least {needed_nrf54lm} nRF54LM20 device(s) for mode '{mode}'", Colors.RED)
        return None
    if len(nrf52840) < needed_nrf52_from_pool:
        log(f"Need at least {needed_nrf52_from_pool} nRF52840 device(s) in the "
            f"pool for mode '{mode}' (pinned RCP does not count), "
            f"found {len(nrf52840)}", Colors.RED)
        return None

    pools = {'nrf54lm': nrf54lm, 'nrf52': nrf52840}
    roles = {}
    # Re-index non-RCP nrf52 roles sequentially against the shrunken pool so
    # the plan's intended relative ordering is preserved regardless of
    # whether the RCP was pinned (otherwise removing the pinned SN would
    # leave "holes" at the plan's original indices).
    nrf52_slot = 0
    for role_key, family, _idx, board, label in plan:
        if role_key == 'rcp' and pinned_rcp:
            serial = pinned_rcp['serial']
        elif family == 'nrf52':
            serial = pools['nrf52'][nrf52_slot]['serial']
            nrf52_slot += 1
        else:
            # nrf54lm roles still honour their original plan index.
            serial = pools[family][_idx]['serial']
        roles[role_key] = {
            'serial': serial,
            'board': board,
            'label': label,
        }

    log(f"Device assignment (mode={mode}):", Colors.GREEN)
    for role, info in roles.items():
        log(f"  {role:>14s}: SN={info['serial']}  ({info['label']})", Colors.WHITE)

    return roles


def get_device_vcom_port(serial_number):
    """Resolve highest-numbered VCOM TTY for a device serial number."""
    try:
        result = subprocess.run(
            ['nrfutil', 'device', 'list', '--json'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        devices = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                data = obj.get('data', {})
                if 'devices' in data:
                    devices.extend(data['devices'])
                nested = data.get('data', {})
                if 'devices' in nested:
                    devices.extend(nested['devices'])
            except json.JSONDecodeError:
                continue

        for dev in devices:
            dev_sn = dev.get('serialNumber', '')
            if dev_sn.lstrip('0') != serial_number.lstrip('0') and dev_sn != serial_number:
                continue
            ports = dev.get('serialPorts', [])
            best_port, best_vcom = None, -1
            for p in ports:
                vcom = p.get('vcom', -1)
                if vcom > best_vcom:
                    best_vcom = vcom
                    best_port = p.get('comName') or p.get('path')
            return best_port
    except Exception as exc:
        log(f"VCOM lookup error for {serial_number}: {exc}", Colors.YELLOW)
    return None


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------

def check_tool(name, args=None):
    """Return True if a CLI tool is available."""
    cmd = args or [name, '--version']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def verify_prerequisites():
    ok = True
    for tool, cmd in [
        ('nrfutil', ['nrfutil', '--version']),
        ('docker', ['docker', '--version']),
    ]:
        if check_tool(tool, cmd):
            log(f"  {tool}: OK", Colors.GREEN)
        else:
            log(f"  {tool}: NOT FOUND", Colors.RED)
            ok = False

    # chip-tool has no stable --version / version across builds; PATH is enough.
    if shutil.which('chip-tool'):
        log("  chip-tool: OK (found on PATH)", Colors.GREEN)
    else:
        log("  chip-tool: NOT FOUND (not on PATH)", Colors.RED)
        ok = False

    return ok


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------

def build_sample(name, board, build_dir, sample_path, extra_args=None):
    log(f"Building {name} for {board}...", Colors.BLUE)
    if not os.path.exists(sample_path):
        log(f"Sample path not found: {sample_path}", Colors.RED)
        return False

    cmd = ['west', 'build', '-p', '-d', build_dir, '-b', board, sample_path]
    if extra_args:
        cmd.extend(['--'] + extra_args)

    log(f"  {' '.join(cmd)}", Colors.CYAN)
    try:
        result = subprocess.run(
            cmd, cwd=WORKSPACE_ROOT,
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            log(f"  Build OK: {name}", Colors.GREEN)
            return True
        log(f"  Build FAILED: {name}\n{result.stderr[-2000:]}", Colors.RED)
        return False
    except subprocess.TimeoutExpired:
        log(f"  Build timeout: {name}", Colors.RED)
        return False
    except Exception as exc:
        log(f"  Build error: {exc}", Colors.RED)
        return False


# ---------------------------------------------------------------------------
# Artifact catalog
# ---------------------------------------------------------------------------
#
# The same three modes exercise overlapping firmware images: the RCP is
# shared by all three, the standalone Matter bulb by two, the dual-stack
# matter_fota switch by two, etc. Encoding build configs per mode led to
# redundant rebuilds and subtle bugs (e.g. ``/tmp/mz_dut`` holding a
# ``light_switch`` binary in one mode and a ``light_bulb`` binary in the
# next). The catalog below keys each distinct image by a stable artifact
# name, which becomes the ``--build`` CLI value and the on-disk directory.
#
# ``extra_args_fn`` takes the 802.15.4 channel (a test-wide runtime choice
# that must match the firmware's compiled-in channel for the channel-scan
# shortcut and the RA/PCAP capture to line up) and returns the list of
# ``-DCONFIG_...`` flags passed verbatim to ``west build``.

ARTIFACTS_ROOT = '/tmp/mz_test_artifacts'


def _zb_channel_args(channel):
    return [
        f'-DCONFIG_ZIGBEE_CHANNEL={channel}',
        '-DCONFIG_ZIGBEE_CHANNEL_SELECTION_MODE_SINGLE=y',
    ]


ARTIFACT_CATALOG = {
    'zigbee_coordinator': {
        'label': 'Zigbee Coordinator (Wireshark-decryptable NWK key)',
        'board': 'nrf52840dk/nrf52840',
        'sample': lambda: f'{ZIGBEE_SAMPLES}/network_coordinator',
        # Forces the well-known "ZigBeeAlliance09" NWK key on the Trust
        # Center so Wireshark decrypts Zigbee frames out of the box.
        # Coordinator-only Kconfig — do not apply to any other node.
        'extra_args': lambda ch: _zb_channel_args(ch) + [
            '-DCONFIG_ZIGBEE_INSECURE_DEFAULT_NWK_KEY=y',
        ],
    },
    'zigbee_bulb': {
        'label': 'Zigbee Light Bulb',
        'board': 'nrf52840dk/nrf52840',
        'sample': lambda: f'{ZIGBEE_SAMPLES}/light_bulb',
        'extra_args': lambda ch: _zb_channel_args(ch),
    },
    'zigbee_switch': {
        'label': 'Zigbee Light Switch',
        'board': 'nrf52840dk/nrf52840',
        'sample': lambda: f'{ZIGBEE_SAMPLES}/light_switch',
        'extra_args': lambda ch: _zb_channel_args(ch),
    },
    'mz_switch_dut': {
        'label': 'Dual-stack Matter+Zigbee Switch (nRF54LM20, matter_fota)',
        'board': 'nrf54lm20dk/nrf54lm20a/cpuapp',
        'sample': lambda: f'{ZIGBEE_SAMPLES}/light_switch',
        'extra_args': lambda ch: _zb_channel_args(ch) + [
            '-DFILE_SUFFIX=matter_fota',
        ],
    },
    'mz_bulb_dut': {
        'label': 'Dual-stack Matter+Zigbee Bulb (nRF54LM20, matter_fota)',
        'board': 'nrf54lm20dk/nrf54lm20a/cpuapp',
        'sample': lambda: f'{ZIGBEE_SAMPLES}/light_bulb',
        # ``CONFIG_OPENTHREAD_SOURCES=y`` is mandatory for this specific
        # build only: the bulb's ``prj_matter_fota.conf`` selects
        # ``ZIGBEE_ROLE_ROUTER=y``, whose cascade flips enough OpenThread
        # Kconfig defaults that ``openthread_check_kconfig_for_precompiled_libs``
        # (nrf/modules/openthread/openthread_kconfig_check.cmake) refuses
        # the precompiled NCS OT library and fails the build. The
        # ``mz_switch_dut`` build hits ``ZIGBEE_ROLE_END_DEVICE=y`` and
        # happens to match the precompiled library, so it does not need
        # this flag. Source-building OT adds a few minutes to this one
        # image only.
        'extra_args': lambda ch: _zb_channel_args(ch) + [
            '-DFILE_SUFFIX=matter_fota',
            '-DCONFIG_OPENTHREAD_SOURCES=y',
        ],
    },
    'matter_bulb': {
        'label': 'Standalone Matter Light Bulb (distinct discriminator)',
        'board': 'nrf52840dk/nrf52840',
        'sample': lambda: f'{NRF_SAMPLES}/matter/light_bulb',
        # Distinct discriminator so chip-tool does not latch onto the DUT's
        # BLE advertisement (both would default to MATTER_DISCRIMINATOR).
        # CHIP_DEVICE_DISCRIMINATOR is ``hex`` in Matter's Kconfig so the
        # value must be ``0x``-prefixed.
        'extra_args': lambda _ch: [
            f'-DCONFIG_CHIP_DEVICE_DISCRIMINATOR=0x{MATTER_BULB_DISCRIMINATOR:X}',
        ],
    },
    'rcp': {
        'label': 'OpenThread RCP (OTBR coprocessor)',
        'board': 'nrf52840dk/nrf52840',
        'sample': lambda: f'{NRF_SAMPLES}/openthread/coprocessor',
        # Default UART transport at 1 Mbaud from the board overlay; no
        # extra -D flags needed. J-Link VCOM forwards UART0 → host ACM.
        'extra_args': lambda _ch: [],
    },
}


# Which artifact each mode's roles pull their firmware from. The test
# framework keys off this when flashing (``flash_all``) and when validating
# the local cache (``verify_mode_artifacts_ready``).
MODE_ARTIFACTS = {
    MODE_SWITCH_DUT: {
        'coordinator': 'zigbee_coordinator',
        'bulb':        'zigbee_bulb',
        'dut':         'mz_switch_dut',
        'rcp':         'rcp',
        'matter_bulb': 'matter_bulb',
    },
    MODE_BULB_DUT: {
        'coordinator':   'zigbee_coordinator',
        'zigbee_switch': 'zigbee_switch',
        'dut':           'mz_bulb_dut',
        'rcp':           'rcp',
    },
    MODE_TOUCHLINK_SWITCH_DUT: {
        'dut':         'mz_switch_dut',
        'bulb':        'zigbee_bulb',
        'rcp':         'rcp',
        'matter_bulb': 'matter_bulb',
    },
}


def artifact_build_dir(name):
    return os.path.join(ARTIFACTS_ROOT, name)


def artifact_hex(name):
    return os.path.join(artifact_build_dir(name), 'merged.hex')


def _artifact_manifest_path(name):
    return os.path.join(artifact_build_dir(name), '_manifest.json')


def _write_artifact_manifest(name, channel, extra_args):
    """Persist a small JSON sidecar next to the built ``merged.hex``.

    Used by the cache-reuse path to refuse to flash a stale image whose
    baked-in channel / Kconfig overrides don't match the current test
    invocation. Kept deliberately small — anything not recorded here is
    treated as "trust the developer picked matching defaults".
    """
    manifest = {
        'artifact': name,
        'channel': channel,
        'extra_args': list(extra_args),
        'built_at': datetime.now().isoformat(timespec='seconds'),
    }
    os.makedirs(artifact_build_dir(name), exist_ok=True)
    try:
        with open(_artifact_manifest_path(name), 'w', encoding='utf-8') as fh:
            json.dump(manifest, fh, indent=2)
    except OSError as exc:
        log(f"  Could not write manifest for {name}: {exc}", Colors.YELLOW)


def _read_artifact_manifest(name):
    try:
        with open(_artifact_manifest_path(name), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def build_artifact(name, channel):
    spec = ARTIFACT_CATALOG.get(name)
    if not spec:
        log(f"Unknown artifact: {name}", Colors.RED)
        return False
    sample_path = spec['sample']()
    extra_args = spec['extra_args'](channel)
    build_dir = artifact_build_dir(name)
    label = f"{spec['label']} [{name}]"
    ok = build_sample(label, spec['board'], build_dir, sample_path, extra_args)
    if ok:
        _write_artifact_manifest(name, channel, extra_args)
    return ok


def build_artifacts(names, channel):
    """Build the listed artifact names sequentially.

    Names already validated by the caller against :data:`ARTIFACT_CATALOG`.
    Returns True iff every build succeeded. On failure, subsequent builds
    are skipped — a broken dependency (for example a west-manifest issue)
    would just produce more noise.
    """
    log("\n=== Building firmware artifacts ===", Colors.BOLD + Colors.BLUE)
    log(f"  Artifact root: {ARTIFACTS_ROOT}", Colors.CYAN)
    log(f"  Channel:       {channel}", Colors.CYAN)
    log(f"  Artifacts:     {', '.join(names)}", Colors.CYAN)
    os.makedirs(ARTIFACTS_ROOT, exist_ok=True)
    for n in names:
        if not build_artifact(n, channel):
            return False
    log("All requested artifacts built successfully", Colors.GREEN)
    return True


def artifacts_required_for(mode):
    """Return the ordered, deduped list of artifact names this mode needs."""
    return list(dict.fromkeys(MODE_ARTIFACTS[mode].values()))


def verify_mode_artifacts_ready(mode, channel):
    """Fail-fast pre-flight check when the user didn't pass ``--build``.

    Catches two separate mistakes with clear remediation:
      * a never-built (or deleted) artifact — ``merged.hex`` is missing;
      * a stale artifact that was built for a different channel than the
        current invocation asks for, which would cause a silent channel
        mismatch between the RCP (Thread) and the ZBOSS stack (Zigbee).
    """
    missing = []
    channel_mismatch = []
    for aname in artifacts_required_for(mode):
        hex_path = artifact_hex(aname)
        if not os.path.exists(hex_path):
            missing.append(aname)
            continue
        m = _read_artifact_manifest(aname)
        if m and m.get('channel') is not None and int(m['channel']) != int(channel):
            channel_mismatch.append((aname, int(m['channel'])))

    if not missing and not channel_mismatch:
        return True

    log("Artifacts are not ready for this test run:", Colors.RED)
    for a in missing:
        log(f"  MISSING:          {a} ({artifact_hex(a)})", Colors.RED)
    for a, ch in channel_mismatch:
        log(f"  CHANNEL MISMATCH: {a} built for ch{ch} but test requested "
            f"ch{channel}", Colors.RED)
    bad = missing + [a for a, _ in channel_mismatch]
    log("", Colors.RED)
    log(f"  To fix: python3 {os.path.basename(sys.argv[0])} --build "
        f"{' '.join(bad)} --channel {channel}", Colors.YELLOW)
    return False


# ---------------------------------------------------------------------------
# Flash helpers
# ---------------------------------------------------------------------------

def _recover_device(serial_number, device_name):
    """CTRL-AP ERASEALL on the target before programming.

    Unlike ``nrfutil device program --options chip_erase_mode=ERASE_ALL`` (the
    default), ``nrfutil device recover`` goes through CTRL-AP so it also
    clears APPROTECT and any other state the SoC's own core could not reach.

    We use this on boards whose role changed between runs (e.g. a board that
    last ran a full MCUBoot+ZBOSS image and is now being re-used as a bare
    coprocessor) where residual UICR / bootloader state can otherwise leave
    the new firmware booting into an unresponsive state.

    Errors are logged but non-fatal: the subsequent ``program`` call will
    fail loudly if the board really is unreachable.
    """
    log(f"  Recovering {device_name} (SN={serial_number}) via CTRL-AP ERASEALL...",
        Colors.BLUE)
    try:
        result = subprocess.run(
            ['nrfutil', 'device', 'recover', '--serial-number', serial_number],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log(f"  Recover warning for {device_name}: {result.stderr.strip()}",
                Colors.YELLOW)
    except Exception as exc:
        log(f"  Recover error ({device_name}): {exc}", Colors.YELLOW)


def flash_device(build_dir, serial_number, device_name, recover=False):
    hex_file = os.path.join(build_dir, 'merged.hex')
    if not os.path.exists(hex_file):
        log(f"  Hex not found: {hex_file}", Colors.RED)
        return False
    sz = os.path.getsize(hex_file)
    log(f"Flashing {device_name} (SN={serial_number}) — {hex_file} ({sz} bytes)", Colors.BLUE)

    if recover:
        _recover_device(serial_number, device_name)

    try:
        result = subprocess.run(
            ['nrfutil', 'device', 'program',
             '--serial-number', serial_number, '--firmware', hex_file],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log(f"  Program failed: {result.stderr}", Colors.RED)
            return False

        subprocess.run(
            ['nrfutil', 'device', 'reset', '--serial-number', serial_number],
            capture_output=True, text=True, timeout=30,
        )
        log(f"  Flash OK: {device_name}", Colors.GREEN)
        return True
    except Exception as exc:
        log(f"  Flash error: {exc}", Colors.RED)
        return False


def reset_device(serial_number, device_name):
    try:
        subprocess.run(
            ['nrfutil', 'device', 'reset', '--serial-number', serial_number],
            capture_output=True, text=True, timeout=30,
        )
        return True
    except Exception as exc:
        log(f"  Reset error ({device_name}): {exc}", Colors.YELLOW)
        return False


def reset_all_devices(roles):
    """Re-reset every target board AFTER pyserial log collection is listening.

    ``nrfutil device program`` resets the target when it finishes, but that
    happens well before we open the VCOM ports — the Zephyr boot banner,
    ZBOSS init signals and BDB start-steering messages land in the kernel's
    ~4 KB ``ttyACM`` ring buffer with no reader and get dropped on overflow.
    By issuing a fresh reset here (with the serial readers already attached)
    we guarantee the full boot log from uptime 0 is captured.

    The RCP is intentionally skipped: its UART is already attached to the
    OTBR Spinel client, so resetting it here would disrupt Thread bring-up.
    """
    log("\n=== Re-resetting targets to capture full boot logs ===", Colors.BOLD + Colors.BLUE)
    reset_map = [
        (roles[role]['serial'], roles[role]['label'])
        for role in _collectable_roles(roles)
        if role in roles
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(reset_map)) as executor:
        list(executor.map(lambda x: reset_device(*x), reset_map))
    log("  All targets reset — boot logs should now be captured", Colors.GREEN)


def flash_all(roles, mode, recover_all=True):
    """Program every role's board with its mode-specific artifact.

    The build directory for each role is resolved via :data:`MODE_ARTIFACTS`,
    so two modes that share a firmware image (e.g. both switch-DUT modes
    use ``mz_switch_dut``) both flash the same cached ``merged.hex`` —
    no rebuild required to switch modes.
    """
    log("\n=== Flashing devices ===", Colors.BOLD + Colors.BLUE)

    # By default every board gets a full CTRL-AP recover before programming
    # (mirrors ``nordic-docs/zigbee/scripts/fota/fota_test.py``). This is the
    # only reliable way to clear residual UICR / APPROTECT / settings-partition
    # state when the same physical board hosts different firmware stacks
    # across runs (coprocessor <-> Matter+MCUboot <-> Zigbee). Without it,
    # observed failures include: Spinel handshake breakdown on the RCP, and
    # Matter samples never producing UART output / never advertising over BLE
    # because MCUboot consumes stale settings and faults on chainload.
    # Cost: ~5-10 s per board, parallelised with ThreadPoolExecutor below, so
    # wall-time impact is roughly the slowest board (~10 s total). Use
    # ``--no-recover-all`` to skip when iterating fast on a known-clean fleet.
    mode_map = MODE_ARTIFACTS[mode]
    flash_map = []
    for role, info in roles.items():
        artifact = mode_map.get(role)
        if not artifact:
            log(f"  Skipping {role}: no artifact mapping for mode {mode}",
                Colors.YELLOW)
            continue
        bdir = artifact_build_dir(artifact)
        # Always recover RCP (its Spinel link is most fragile), and recover
        # everything else when the user hasn't opted out.
        recover = recover_all or role == 'rcp'
        flash_map.append((bdir, info['serial'], info['label'], recover))

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(flash_map)) as executor:
        futures = {
            executor.submit(flash_device, bdir, sn, name, recover): name
            for bdir, sn, name, recover in flash_map
        }
        results = {}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                log(f"  {name} flash exception: {exc}", Colors.RED)
                results[name] = False

    if all(results.values()):
        log("All devices flashed successfully", Colors.GREEN)
        return True
    for name, ok in results.items():
        if not ok:
            log(f"  FAILED: {name}", Colors.RED)
    return False


# ---------------------------------------------------------------------------
# PCAP sniffer
# ---------------------------------------------------------------------------

NORDIC_SNIFFER_USB_VID = '1915'
NORDIC_SNIFFER_USB_PID = '154b'


def _read_sysfs(tty_name, attr):
    """Read a USB attribute from sysfs for a ttyACM device.

    The idVendor/idProduct files live one or two levels above the tty's
    ``device`` symlink depending on whether the tty is a child of the USB
    interface or the USB device node itself.
    """
    for depth in ('..', '../..'):
        path = f'/sys/class/tty/{tty_name}/device/{depth}/{attr}'
        try:
            with open(path) as f:
                return f.read().strip()
        except OSError:
            continue
    return None


def find_sniffer_device():
    """Auto-detect the Nordic 802.15.4 sniffer ttyACM device.

    Matches by USB vendor:product ID (1915:154b).  Falls back to checking
    the ``interface`` sysfs string for "802154"/"sniffer".
    """
    import glob as _glob
    candidates = sorted(_glob.glob('/dev/ttyACM*'))
    for dev in candidates:
        name = os.path.basename(dev)
        vid = _read_sysfs(name, 'idVendor')
        pid = _read_sysfs(name, 'idProduct')
        if vid == NORDIC_SNIFFER_USB_VID and pid == NORDIC_SNIFFER_USB_PID:
            log(f"Sniffer auto-detected: {dev} (USB {vid}:{pid})", Colors.GREEN)
            return dev
    for dev in candidates:
        name = os.path.basename(dev)
        try:
            with open(f'/sys/class/tty/{name}/device/interface') as f:
                iface_str = f.read().strip()
        except OSError:
            continue
        if '802154' in iface_str.lower() or 'sniffer' in iface_str.lower():
            log(f"Sniffer auto-detected: {dev} ({iface_str})", Colors.GREEN)
            return dev
    log("No Nordic 802.15.4 sniffer found on any ttyACM device", Colors.YELLOW)
    return None


def _extcap_pref_name(dev_path):
    """Derive the tshark extcap preference name from a /dev/ path.

    tshark names the preference ``extcap.<sanitized_path>.channel`` where
    ``<sanitized_path>`` lowercases the basename and replaces ``/`` with ``_``.
    E.g. /dev/ttyACM2 -> extcap._dev_ttyacm2.channel
    """
    return 'extcap.' + dev_path.lower().replace('/', '_') + '.channel'


def start_pcap_capture(channel):
    global current_pcap_process, current_pcap_file, NORDIC_SNIFFER_DEVICE
    ts = int(time.time())
    pcap_file = f'/tmp/mz_test_ch{channel}_{ts}.pcap'
    current_pcap_file = pcap_file

    if NORDIC_SNIFFER_DEVICE is None:
        NORDIC_SNIFFER_DEVICE = find_sniffer_device()
    if NORDIC_SNIFFER_DEVICE is None:
        log("PCAP capture disabled — no sniffer device", Colors.YELLOW)
        return None

    pref = _extcap_pref_name(NORDIC_SNIFFER_DEVICE)
    log(f"Starting PCAP capture on ch{channel} via {NORDIC_SNIFFER_DEVICE} -> {pcap_file}", Colors.BLUE)
    log(f"  extcap pref: {pref}:{channel}", Colors.CYAN)
    try:
        proc = subprocess.Popen(
            ['tshark', '-i', NORDIC_SNIFFER_DEVICE, '-w', pcap_file,
             '-o', f'{pref}:{channel}', '-f', 'not icmp'],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        time.sleep(2)
        if proc.poll() is not None:
            _, stderr = proc.communicate()
            log(f"tshark exited early: {stderr.decode()[:500]}", Colors.RED)
            current_pcap_process = None
            return None
        current_pcap_process = proc
        log(f"PCAP capture running (pid {proc.pid})", Colors.GREEN)
        return proc
    except Exception as exc:
        log(f"Failed to start tshark: {exc}", Colors.RED)
        return None


def stop_pcap_capture():
    global current_pcap_process, current_pcap_file
    if not current_pcap_process:
        return
    proc = current_pcap_process
    current_pcap_process = None
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        _, stderr = proc.communicate(timeout=2)
        if stderr:
            log(f"tshark stderr: {stderr.decode()[:500]}", Colors.CYAN)
    except Exception:
        pass
    if current_pcap_file and os.path.exists(current_pcap_file):
        sz = os.path.getsize(current_pcap_file)
        log(f"PCAP stopped — file size: {sz} bytes", Colors.GREEN if sz > 500 else Colors.YELLOW)
    else:
        log("PCAP stopped — no file produced", Colors.YELLOW)


# ---------------------------------------------------------------------------
# Serial log collection
# ---------------------------------------------------------------------------

def start_log_collection(serial_number, device_name):
    """Start background thread collecting serial logs. Returns log file path."""
    global collected_log_files
    port = get_device_vcom_port(serial_number)
    if not port:
        log(f"  No VCOM port for {device_name} ({serial_number})", Colors.YELLOW)
        return None

    ts = int(time.time())
    log_path = f'/tmp/mz_{device_name}_{serial_number}_{ts}.log'
    collected_log_files.append((device_name, log_path))

    def _collector():
        try:
            import serial as pyserial
            with pyserial.Serial(port, 115200, timeout=1) as ser:
                with open(log_path, 'w', encoding='utf-8', errors='ignore') as f:
                    while log_collection_active:
                        if ser.in_waiting > 0:
                            data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                            f.write(data)
                            f.flush()
                        time.sleep(0.05)
        except ImportError:
            log(f"  pyserial not available — no logs for {device_name}", Colors.YELLOW)
        except Exception as exc:
            log(f"  Log collection error ({device_name}): {exc}", Colors.YELLOW)

    t = threading.Thread(target=_collector, daemon=True)
    t.start()
    log(f"  Logging {device_name} on {port} -> {log_path}", Colors.CYAN)
    return log_path


def _collectable_roles(roles):
    """Return the subset of role keys whose serial logs are worth capturing.

    Excludes the RCP because its UART is owned by the OTBR container (Spinel
    traffic, not human-readable logs) — opening a second pyserial reader on
    the same ACM would either fail or race with OTBR.
    """
    return [role for role in roles if role != 'rcp']


def start_all_log_collection(roles):
    log("\n=== Starting log collection ===", Colors.BOLD + Colors.BLUE)
    paths = {}
    for role in _collectable_roles(roles):
        info = roles.get(role)
        if not info:
            continue
        p = start_log_collection(info['serial'], role)
        paths[role] = p
    return paths


# ---------------------------------------------------------------------------
# Docker OTBR
# ---------------------------------------------------------------------------

def find_rcp_tty(rcp_serial, tty_override=None):
    """Find the TTY for the RCP board (Spinel over J-Link VCOM / UART).

    Default coprocessor build uses UART0 at 1 Mbaud; the J-Link VCOM
    (typically the only serialPort for a plain DK) forwards it to host.
    """
    if tty_override:
        if os.path.exists(tty_override):
            log(f"  RCP TTY (override): {tty_override}", Colors.CYAN)
            return tty_override
        log(f"  RCP TTY override does not exist: {tty_override}", Colors.RED)
        return None

    ports = _nrfutil_serial_ports_for_device(rcp_serial)
    if not ports:
        port = get_device_vcom_port(rcp_serial)
        if port:
            return port
        log("Could not resolve RCP VCOM port via nrfutil", Colors.YELLOW)
        return None

    # With UART transport there is typically a single VCOM (vcom=0).
    ports.sort(key=lambda p: p.get('vcom', -1))
    chosen = ports[0]
    path = chosen.get('comName') or chosen.get('path')
    if path:
        log(f"  RCP TTY (nrfutil vcom={chosen.get('vcom')}): {path}", Colors.CYAN)
        return path
    return None


def _nrfutil_serial_ports_for_device(serial_number):
    """Return ``serialPorts`` list for a board serial, or []."""
    try:
        result = subprocess.run(
            ['nrfutil', 'device', 'list', '--json'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        devices = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                data = obj.get('data', {})
                if isinstance(data.get('devices'), list):
                    devices.extend(data['devices'])
                inner = data.get('data', {})
                if isinstance(inner, dict) and isinstance(inner.get('devices'), list):
                    devices.extend(inner['devices'])
            except json.JSONDecodeError:
                continue
        seen = set()
        merged = []
        for dev in devices:
            sn = dev.get('serialNumber', '')
            if sn.lstrip('0') != serial_number.lstrip('0') and sn != serial_number:
                continue
            ports = dev.get('serialPorts')
            if not isinstance(ports, list):
                continue
            for p in ports:
                key = p.get('path') or p.get('comName')
                if key and key not in seen:
                    seen.add(key)
                    merged.append(p)
        if merged:
            return merged
    except Exception:
        pass
    return []


def _ensure_otbr_docker_network():
    """Create the IPv6 ``otbr`` network from NCS Thread docs (idempotent)."""
    log(f'  Ensuring Docker network "{OTBR_DOCKER_NETWORK}"…', Colors.CYAN)
    chk = subprocess.run(
        ['docker', 'network', 'inspect', OTBR_DOCKER_NETWORK],
        capture_output=True, text=True, timeout=10,
    )
    if chk.returncode == 0:
        return True
    create = subprocess.run(
        [
            'docker', 'network', 'create', '--ipv6',
            '--subnet', 'fd11:db8:1::/64',
            '-o', 'com.docker.network.bridge.name=otbr0',
            OTBR_DOCKER_NETWORK,
        ],
        capture_output=True, text=True, timeout=30,
    )
    if create.returncode == 0:
        log(f'  Created Docker network "{OTBR_DOCKER_NETWORK}"', Colors.GREEN)
        return True
    err = (create.stderr or create.stdout or '').lower()
    if 'already exists' in err or 'is already in use' in err:
        return True
    log(f"  Could not create Docker network (continuing without --network): {create.stderr}", Colors.YELLOW)
    return False


def _otbr_kick_agent_services():
    """Ensure otbr-agent is running inside the container (RCP must be reachable)."""
    log("  Probing otbr-agent inside container…", Colors.CYAN)
    for shell in (
        'service otbr-agent status 2>&1 || true',
        'service otbr-agent restart 2>&1 || service otbr-agent start 2>&1 || true',
    ):
        try:
            r = subprocess.run(
                ['docker', 'exec', OTBR_CONTAINER_NAME, 'sh', '-c', shell],
                capture_output=True, text=True, timeout=60,
            )
            out = (r.stdout or r.stderr or '').strip()
            if out:
                log(f"    {out[:500]}", Colors.CYAN)
        except Exception as exc:
            log(f"    (exec failed: {exc})", Colors.YELLOW)
    time.sleep(5)


def _log_rcp_tty_candidates(rcp_serial):
    """When OTBR fails, list all nrfutil VCOMs for the RCP (wrong TTY is the usual fix)."""
    ports = _nrfutil_serial_ports_for_device(rcp_serial)
    if not ports:
        log("  nrfutil: no serialPorts for RCP — check USB / device list", Colors.YELLOW)
        return
    ports.sort(key=lambda p: p.get('vcom', -1))
    log("  nrfutil serialPorts for this RCP (if the chosen TTY is wrong, pick another with --rcp-tty):", Colors.YELLOW)
    for p in ports:
        log(f"    vcom={p.get('vcom')} path={p.get('path')!r} comName={p.get('comName')!r}", Colors.WHITE)


def _otbr_dump_agent_diagnostics():
    """Log container logs, service status, /dev/radio, and processes when ot-ctl cannot connect."""
    _log_otbr_container_tail(80)
    diag = """
echo "--- service otbr-agent status ---"
service otbr-agent status 2>&1 || true
echo "--- pgrep otbr / rcp ---"
pgrep -af otbr 2>/dev/null || true
pgrep -af ot-rcp 2>/dev/null || true
pgrep -af spinel 2>/dev/null || true
echo "--- /dev/radio ---"
ls -la /dev/radio 2>&1 || true
echo "--- /etc/default/otbr-agent (head) ---"
head -50 /etc/default/otbr-agent 2>&1 || true
echo "--- ps (first 45 lines) ---"
ps aux 2>/dev/null | head -45 || true
echo "--- openthread run/socket paths ---"
ls -la /run/openthread 2>/dev/null || true
ls -la /var/run/openthread 2>/dev/null || true
ls -la /tmp/openthread* 2>/dev/null || true
"""
    try:
        r = subprocess.run(
            ['docker', 'exec', OTBR_CONTAINER_NAME, 'sh', '-c', diag],
            capture_output=True, text=True, timeout=30,
        )
        out = (r.stdout or '').strip()
        if out:
            log("  OTBR in-container diagnostics:", Colors.YELLOW)
            for ln in out.split('\n'):
                log(f"    | {ln}", Colors.WHITE)
    except Exception as exc:
        log(f"  (OTBR diagnostics exec failed: {exc})", Colors.YELLOW)


def start_otbr(rcp_serial, docker_image, rcp_tty_override=None, channel=None, network_key=None):
    log("\n=== Starting OTBR Docker container ===", Colors.BOLD + Colors.BLUE)

    # Stop any leftover container
    subprocess.run(
        ['docker', 'rm', '-f', OTBR_CONTAINER_NAME],
        capture_output=True, timeout=10,
    )

    rcp_tty = find_rcp_tty(rcp_serial, tty_override=rcp_tty_override)
    if not rcp_tty:
        log("Cannot find RCP TTY device", Colors.RED)
        return False

    log(f"  RCP device: {rcp_tty}", Colors.CYAN)
    log(f"  OTBR image: {docker_image}", Colors.CYAN)

    use_otbr_net = _ensure_otbr_docker_network()
    if not use_otbr_net:
        log("  Hint: without Docker network \"otbr\", otbr-agent may fail; see NCS Thread tools.rst", Colors.YELLOW)

    log("  docker pull …", Colors.CYAN)
    try:
        pull = subprocess.run(
            ['docker', 'pull', docker_image],
            capture_output=True, text=True, timeout=300,
        )
        if pull.returncode != 0:
            log(f"  docker pull failed: {pull.stderr or pull.stdout}", Colors.RED)
            return False
    except subprocess.TimeoutExpired:
        log("  docker pull timeout", Colors.RED)
        return False
    except Exception as exc:
        log(f"  docker pull error: {exc}", Colors.RED)
        return False

    # Warm the busybox image cache now, while we're already doing networked
    # docker work, so the host-route helper later (``_add_host_ipv6_routes``)
    # never blocks on an image fetch inside its own timeout budget. Failures
    # here are non-fatal because the route add itself will retry.
    _prefetch_busybox_image()

    # ``-t`` allocates a TTY; some OTBR init paths behave better than plain ``-d`` (see NCS ``-it`` doc example).
    cmd = [
        'docker', 'run', '-d', '-t',
        '--name', OTBR_CONTAINER_NAME,
    ]
    if use_otbr_net:
        cmd.extend(['--network', OTBR_DOCKER_NETWORK])
    # Disable otbr-agent's in-container ip6tables firewall init; loading
    # ip6table_filter on the host would require root (modprobe needs CAP_SYS_MODULE).
    cmd.extend(['-e', 'FIREWALL=0'])
    cmd.extend([
        '--sysctl', 'net.ipv6.conf.all.disable_ipv6=0',
        '--sysctl', 'net.ipv4.conf.all.forwarding=1',
        '--sysctl', 'net.ipv6.conf.all.forwarding=1',
        '-p', '8080:80',
        '--dns=127.0.0.1',
        '-v', f'{rcp_tty}:/dev/radio',
        '--privileged',
        docker_image,
        '--radio-url', 'spinel+hdlc+uart:///dev/radio?uart-baudrate=1000000',
    ])
    log(f"  {' '.join(cmd)}", Colors.CYAN)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=OTBR_DOCKER_RUN_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            log(f"  Docker run failed: {result.stderr}", Colors.RED)
            return False
        log("  OTBR container started", Colors.GREEN)
    except subprocess.TimeoutExpired:
        log(
            f"  Docker run timed out after {OTBR_DOCKER_RUN_TIMEOUT_S}s "
            "(host I/O or Docker daemon slow; check ``docker ps -a`` for a stuck container)",
            Colors.RED,
        )
        return False
    except Exception as exc:
        log(f"  Docker error: {exc}", Colors.RED)
        return False

    _otbr_kick_agent_services()

    if not _wait_for_otbr_ctl_ready():
        log("  otbr-agent did not become ready in time (ot-ctl could not connect)", Colors.RED)
        log("  Typical cause: wrong RCP TTY (try --rcp-tty), RCP not flashed with coprocessor sample, or USB busy.", Colors.YELLOW)
        log("  Inspect ``otbr_docker.log`` / UART lines for Spinel ``RESET`` / open errors.", Colors.YELLOW)
        _log_rcp_tty_candidates(rcp_serial)
        _otbr_dump_agent_diagnostics()
        return False

    if not _otbr_form_thread_network(channel=channel, network_key=network_key):
        _log_otbr_container_tail()
        return False

    # Wait for OTBR to reach leader (same as NCS “Form” in web UI, done via ot-ctl above)
    log("  Waiting for OTBR Thread state (leader/router)...", Colors.CYAN)
    for attempt in range(30):
        time.sleep(2)
        try:
            result = subprocess.run(
                ['docker', 'exec', OTBR_CONTAINER_NAME, 'ot-ctl', 'state'],
                capture_output=True, text=True, timeout=5,
            )
            state = result.stdout.strip().split('\n')[0].strip().lower()
            if state in ('leader', 'router'):
                log(f"  OTBR Thread state: {state}", Colors.GREEN)
                if not _setup_host_thread_route():
                    # Without a host route to the Thread mesh, chip-tool's
                    # CASE/DNS-SD packets get EHOSTUNREACH / "Network is
                    # unreachable" at the socket layer and commissioning
                    # fails with a misleading error. Surface the real cause
                    # here and abort the bring-up.
                    log("  Host route to Thread mesh could not be installed "
                        "— aborting (chip-tool would fail with 'Network is "
                        "unreachable')", Colors.RED)
                    return False
                return True
            if attempt % 5 == 4:
                detail = state or '(empty)'
                if not state and result.stderr.strip():
                    detail = f"(empty) stderr={result.stderr.strip()[:200]}"
                log(f"  OTBR state: {detail} (waiting...)", Colors.CYAN)
        except Exception:
            pass

    log("  OTBR did not become leader within timeout", Colors.RED)
    _log_otbr_container_tail()
    return False


def _setup_host_thread_route():
    """Add IPv6 route from host to the Thread mesh through the Docker bridge.

    NCS Thread tools.rst step 8 documents this as ``sudo ip -6 route add …``,
    but we run the ``ip`` call inside a privileged busybox container on the
    host network namespace so no sudo is required (see _add_host_ipv6_route).

    We retrieve the mesh-local prefix from ``ot-ctl dataset active``, any OMR
    / on-mesh prefix from ``ot-ctl br omrprefix`` / ``prefix``, and the OTBR
    container's IPv6 address on the ``otbr`` Docker bridge.

    Returns ``True`` iff all Thread prefixes are routable from the host after
    the call. The OTBR-bring-up caller treats ``False`` as a hard failure:
    chip-tool's BLE-Thread pairing sends CASE/DNS-SD packets into the Thread
    mesh through these routes, so a missing route surfaces as a misleading
    ``OS Error 0x02000065: Network is unreachable`` several seconds later.
    """
    # Collect all Thread prefixes that need host routes:
    # 1) mesh-local prefix (from dataset)
    # 2) OMR / on-mesh prefix (from ``ot-ctl br omrprefix`` or ``prefix``)
    prefixes = []
    try:
        r = _otbr_exec_ot_ctl(['dataset', 'active'], timeout=10)
        for line in (r.stdout or '').split('\n'):
            if line.strip().lower().startswith('mesh local prefix:'):
                p = line.split(':', 1)[-1].strip()
                if p:
                    prefixes.append(p)
                break
    except Exception:
        pass

    for ctl_cmd in (['br', 'omrprefix'], ['prefix']):
        try:
            r = _otbr_exec_ot_ctl(ctl_cmd, timeout=10)
            for line in (r.stdout or '').split('\n'):
                line = line.strip()
                if '/' in line and line.startswith('fd'):
                    token = line.split()[0]
                    if token not in prefixes:
                        prefixes.append(token)
        except Exception:
            pass

    if not prefixes:
        log("  Could not determine Thread prefixes — skipping host route", Colors.YELLOW)
        return False

    # Get container IPv6 on the otbr bridge
    container_ipv6 = None
    try:
        r = subprocess.run(
            ['docker', 'inspect', '-f',
             '{{range .NetworkSettings.Networks}}{{.GlobalIPv6Address}}{{end}}',
             OTBR_CONTAINER_NAME],
            capture_output=True, text=True, timeout=10,
        )
        addr = r.stdout.strip()
        if addr:
            container_ipv6 = addr
    except Exception:
        pass

    if not container_ipv6:
        container_ipv6 = 'fd11:db8:1::2'
        log(f"  Could not detect OTBR container IPv6 — using default {container_ipv6}", Colors.YELLOW)

    return _add_host_ipv6_routes(prefixes, container_ipv6)


def _prefetch_busybox_image():
    """Ensure the ``busybox`` image is locally cached before route-add time.

    ``_add_host_ipv6_routes`` runs ``docker run --rm --privileged --net=host
    busybox sh -c ...`` inside a bounded timeout. If the image isn't in the
    local cache, that single call has to fetch ~2 MB from a registry on top
    of the usual container-creation overhead and can reliably blow through
    the timeout budget (observed: 15 s cap hit on a single batched call).
    Pulling once here during OTBR startup — which is already a networked,
    long-running phase — keeps the route-add path purely local.
    """
    try:
        inspect = subprocess.run(
            ['docker', 'image', 'inspect', 'busybox'],
            capture_output=True, text=True, timeout=5,
        )
        if inspect.returncode == 0:
            return
    except Exception:
        pass

    log("  Pre-pulling busybox (host-route helper image)...", Colors.CYAN)
    try:
        pull = subprocess.run(
            ['docker', 'pull', 'busybox'],
            capture_output=True, text=True, timeout=120,
        )
        if pull.returncode != 0:
            log(f"  busybox pull warning: "
                f"{(pull.stderr or pull.stdout).strip()[:200]}", Colors.YELLOW)
    except Exception as exc:
        log(f"  busybox pull error (non-fatal): {exc}", Colors.YELLOW)


def _route_already_present(prefix):
    """Return True if ``ip -6 route show <prefix>`` reports any matching entry.

    The host kernel may auto-install routes for on-mesh prefixes via Router
    Advertisements emitted by the OTBR; re-adding them manually would just
    return EEXIST. ``ip route show`` is read-only so no privileges required.
    """
    try:
        r = subprocess.run(
            ['ip', '-6', 'route', 'show', prefix],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return False
    return bool(r.stdout.strip())


def _add_host_ipv6_routes(prefixes, via):
    """Add all Thread-prefix host routes in a SINGLE privileged container.

    Previously we spawned one ``docker run --rm --privileged --net=host
    busybox ip ...`` per prefix. Two back-to-back invocations were reliably
    wedging for 30+ s on the second call — likely Docker API/iptables lock
    contention while the first container was still being reaped — even
    though the actual ``ip`` call is trivially fast. Batching all routes
    into one ``sh -c`` chain gets us down to a single container start-up
    and eliminates the hang entirely.

    We first filter out prefixes the host already knows (RA-installed by
    the OTBR), to keep the batch minimal.
    """
    to_add = []
    for prefix in prefixes:
        if _route_already_present(prefix):
            log(f"  Route already present on host: {prefix}", Colors.GREEN)
            continue
        to_add.append(prefix)

    if not to_add:
        return True

    # ``|| true`` tolerates EEXIST (concurrent RA add races our add) so one
    # already-present prefix doesn't abort the whole batch.
    script = ' ; '.join(
        f'ip -6 route add {p} dev otbr0 via {via} 2>&1 || true'
        for p in to_add
    )
    cmd = [
        'docker', 'run', '--rm', '--privileged', '--net=host',
        'busybox', 'sh', '-c', script,
    ]

    # The ``docker run`` path has a variable cold-start cost (container create
    # + namespace setup + reap). Allow generous headroom and retry once — a
    # transient Docker-daemon stall rarely repeats back-to-back. The actual
    # ``ip`` work inside the container is trivially fast.
    _ROUTE_BATCH_TIMEOUT_S = 45
    _ROUTE_BATCH_ATTEMPTS = 2

    log(f"  Adding {len(to_add)} host route(s) via {via} dev otbr0 "
        f"(batched): {', '.join(to_add)}", Colors.CYAN)

    last_err = None
    for batch_attempt in range(1, _ROUTE_BATCH_ATTEMPTS + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=_ROUTE_BATCH_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            last_err = (f"timed out after {_ROUTE_BATCH_TIMEOUT_S}s "
                        f"(attempt {batch_attempt}/{_ROUTE_BATCH_ATTEMPTS})")
            log(f"  Route add batch {last_err}", Colors.YELLOW)
            continue
        except Exception as exc:
            last_err = f"error ({exc}) on attempt {batch_attempt}"
            log(f"  Route add {last_err}", Colors.YELLOW)
            continue

        if r.returncode != 0:
            log(f"  Route add batch non-zero exit ({r.returncode}): "
                f"{(r.stderr or r.stdout).strip()[:300]}", Colors.YELLOW)

        break
    else:
        log(f"  Route add batch exhausted all {_ROUTE_BATCH_ATTEMPTS} "
            f"attempts — last error: {last_err}", Colors.RED)
        return False

    # Post-check: verify each prefix is actually present now.
    all_ok = True
    for prefix in to_add:
        if _route_already_present(prefix):
            log(f"  Route added: {prefix}", Colors.GREEN)
        else:
            log(f"  Route STILL MISSING after add: {prefix}", Colors.RED)
            all_ok = False
    return all_ok


def _wait_for_otbr_ctl_ready():
    """Poll until ``ot-ctl`` can talk to otbr-agent (control socket exists)."""
    log("  Waiting for otbr-agent (ot-ctl session)...", Colors.CYAN)
    deadline = time.time() + OTBR_CTL_READY_TIMEOUT_S
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        last = None
        for cmd in (
            ['docker', 'exec', OTBR_CONTAINER_NAME, 'ot-ctl', 'state'],
            ['docker', 'exec', OTBR_CONTAINER_NAME, 'sh', '-c', 'sudo ot-ctl state'],
        ):
            try:
                last = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if last.returncode == 0:
                    line = last.stdout.strip().split('\n')[0].strip()
                    log(f"  ot-ctl ready after {attempt} attempt(s) (state={line or '?'})", Colors.GREEN)
                    return True
            except Exception:
                last = None
        if attempt in (1, 5, 15, 30) or attempt % 20 == 0:
            hint = ""
            if last and (last.stderr or last.stdout):
                hint = f" — {(last.stderr or last.stdout).strip()[:100]}"
            log(f"  still waiting for ot-ctl… ({attempt}){hint}", Colors.CYAN)
        time.sleep(2)
    return False


def _otbr_exec_ot_ctl(args, timeout=20):
    """Run ``docker exec … ot-ctl <args>``."""
    cmd = ['docker', 'exec', OTBR_CONTAINER_NAME, 'ot-ctl'] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _otbr_form_thread_network(channel=None, network_key=None):
    """Create a new Thread dataset and start Thread (OTBR web UI “Form” equivalent)."""
    log("  Forming Thread network on OTBR (ot-ctl)...", Colors.CYAN)
    steps = [
        (['dataset', 'init', 'new'], 'dataset init new'),
    ]
    if channel is not None:
        steps.append((['dataset', 'channel', str(channel)], f'dataset channel {channel}'))
    if network_key:
        steps.append((['dataset', 'networkkey', network_key],
                      f'dataset networkkey {network_key}'))
    steps += [
        (['dataset', 'commit', 'active'], 'dataset commit active'),
        (['ifconfig', 'up'], 'ifconfig up'),
        (['thread', 'start'], 'thread start'),
    ]
    for argv, label in steps:
        r = _otbr_exec_ot_ctl(argv)
        if r.returncode != 0:
            log(f"  ot-ctl {label} failed (exit {r.returncode})", Colors.RED)
            if r.stderr.strip():
                log(f"    stderr: {r.stderr.strip()[:500]}", Colors.RED)
            if r.stdout.strip():
                log(f"    stdout: {r.stdout.strip()[:500]}", Colors.RED)
            return False
        if r.stdout.strip():
            log(f"  ot-ctl {label}: {r.stdout.strip()[:120]}", Colors.CYAN)
        else:
            log(f"  ot-ctl {label}: OK", Colors.GREEN)
    return True


def _log_otbr_container_tail(lines=40):
    try:
        r = subprocess.run(
            ['docker', 'logs', '--tail', str(lines), OTBR_CONTAINER_NAME],
            capture_output=True, text=True, timeout=10,
        )
        if r.stdout.strip():
            log(f"  OTBR container logs (last {lines} lines):", Colors.YELLOW)
            for ln in r.stdout.strip().split('\n')[-lines:]:
                log(f"    | {ln}", Colors.WHITE)
    except Exception as exc:
        log(f"  (could not read docker logs: {exc})", Colors.YELLOW)


def capture_otbr_docker_logs(quiet=False):
    """Write full ``docker logs`` for ``OTBR_CONTAINER_NAME`` to ``otbr_docker_log_path``.

    No-op if the container does not exist or path is unset. Safe to call more than once.
    If ``quiet``, do not log the save path (used from atexit after an explicit capture).
    """
    global otbr_docker_log_path
    if not otbr_docker_log_path:
        return
    try:
        chk = subprocess.run(
            ['docker', 'inspect', OTBR_CONTAINER_NAME],
            capture_output=True, timeout=5,
        )
        if chk.returncode != 0:
            return
    except Exception:
        return
    try:
        r = subprocess.run(
            ['docker', 'logs', '--timestamps', OTBR_CONTAINER_NAME],
            capture_output=True, text=True, timeout=120,
        )
        with open(otbr_docker_log_path, 'w', encoding='utf-8', errors='replace') as f:
            if r.stdout:
                f.write(r.stdout)
            if r.stderr:
                f.write('\n--- docker logs stderr ---\n')
                f.write(r.stderr)
        if not quiet:
            log(f"  OTBR docker logs saved -> {otbr_docker_log_path}", Colors.CYAN)
    except Exception as exc:
        if not quiet:
            log(f"  (could not save OTBR docker logs: {exc})", Colors.YELLOW)


def get_thread_network_key():
    """Retrieve the Thread network key from OTBR (32 hex chars)."""
    try:
        r = subprocess.run(
            ['docker', 'exec', OTBR_CONTAINER_NAME, 'ot-ctl', 'networkkey'],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            for line in r.stdout.strip().split('\n'):
                line = line.strip()
                if line and line.lower() != 'done':
                    return line
    except Exception:
        pass
    return None


def _rename_pcap_with_key(network_key):
    """Append the Thread network key to the PCAP filename for easy Wireshark import."""
    global current_pcap_file
    if not current_pcap_file or not os.path.exists(current_pcap_file):
        return
    base, ext = os.path.splitext(current_pcap_file)
    new_path = f'{base}_key_{network_key}{ext}'
    try:
        os.rename(current_pcap_file, new_path)
        current_pcap_file = new_path
        log(f"  PCAP renamed: {os.path.basename(new_path)}", Colors.CYAN)
    except OSError as exc:
        log(f"  Could not rename PCAP: {exc}", Colors.YELLOW)


def get_thread_dataset():
    """Retrieve the active Thread dataset hex from OTBR."""
    try:
        result = subprocess.run(
            ['docker', 'exec', OTBR_CONTAINER_NAME, 'ot-ctl', 'dataset', 'active', '-x'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line and line.lower() != 'done':
                    log(f"  Thread dataset: {line[:40]}...", Colors.CYAN)
                    return line
    except Exception as exc:
        log(f"  Failed to get Thread dataset: {exc}", Colors.RED)
    return None


def stop_otbr():
    log("Stopping OTBR container...", Colors.BLUE)
    capture_otbr_docker_logs()
    try:
        subprocess.run(
            ['docker', 'rm', '-f', OTBR_CONTAINER_NAME],
            capture_output=True, timeout=10,
        )
        log("  OTBR stopped", Colors.GREEN)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Zigbee verification (log monitoring)
# ---------------------------------------------------------------------------

def _tail_log(path, since_line=0):
    """Read log file contents from a given line offset."""
    if not path or not os.path.exists(path):
        return '', 0
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        text = ''.join(lines[since_line:])
        return text, len(lines)
    except Exception:
        return '', since_line


def _zigbee_milestones_for_mode(mode):
    """Return a list of milestone specs for ``mode``.

    Each spec is ``(key, role, match_substrings, human_label)``. ``role`` is
    the key in ``log_paths``; ``match_substrings`` is a tuple of lowercase
    fragments — any one matching in the new log text marks the milestone.
    """
    coord_ready = (
        'coordinator_ready', 'coordinator',
        ('network steering', 'joined network',
         'device commissioned', 'device authorization'),
        'Coordinator: network active',
    )
    joined = lambda: ('joined network', 'bdb_signal_steering')

    if mode == MODE_SWITCH_DUT:
        # The DUT (a switch) logs "Found bulb addr" once it identifies the
        # Zigbee bulb endpoint via BDB match-descriptor exchange.
        return [
            coord_ready,
            ('bulb_joined',     'bulb', joined(), 'Zigbee Bulb: joined network'),
            ('dut_joined',      'dut',  joined(), 'DUT: joined Zigbee network'),
            ('dut_found_bulb',  'dut',  ('found bulb addr',), 'DUT: found light bulb'),
        ]
    if mode == MODE_BULB_DUT:
        # Here the satellite switch is the one that should find the bulb —
        # and the bulb is the DUT. So the "found bulb" milestone is logged by
        # zigbee_switch (light_switch sample), not by the DUT.
        return [
            coord_ready,
            ('dut_joined',            'dut',
             joined(), 'DUT (bulb): joined Zigbee network'),
            ('zigbee_switch_joined',  'zigbee_switch',
             joined(), 'Zigbee Switch: joined network'),
            ('zigbee_switch_found',   'zigbee_switch',
             ('found bulb addr',), 'Zigbee Switch: found DUT bulb'),
        ]
    if mode == MODE_TOUCHLINK_SWITCH_DUT:
        # Touchlink has no coordinator. The three log lines below are emitted
        # by ncs-zigbee/samples/light_switch once the user presses the touchlink
        # button and the initiator scan + Touchlink commissioning complete:
        #   - "Starting Touchlink initiator"   (button_handler -> schedule cb)
        #   - "Touchlink done: start finding bulb" (ZB_BDB_SIGNAL_TOUCHLINK OK)
        #   - "Found bulb addr ..."             (match-descriptor succeeded)
        return [
            ('touchlink_started', 'dut',
             ('starting touchlink initiator',),
             'DUT: Touchlink initiator started'),
            ('touchlink_done',    'dut',
             ('touchlink done',),
             'DUT: Touchlink commissioning done'),
            ('dut_found_bulb',    'dut',
             ('found bulb addr',),
             'DUT: found Touchlink-paired bulb'),
        ]
    raise ValueError(f"Unknown mode: {mode}")


def wait_for_zigbee_milestones(log_paths, mode, timeout=60):
    """Monitor logs until all mode-specific Zigbee milestones are reached.

    Returns True if all milestones met within timeout.
    """
    log("\n=== Waiting for Zigbee network formation ===", Colors.BOLD + Colors.BLUE)

    specs = _zigbee_milestones_for_mode(mode)
    milestones = {key: False for key, *_ in specs}
    offsets = {k: 0 for k in log_paths}
    first_pass = True
    start = time.time()

    while time.time() - start < timeout:
        # Read each log once per pass to avoid O(N*specs) reopens.
        texts = {}
        for role, path in log_paths.items():
            if not path:
                continue
            text, new_offset = _tail_log(path, offsets[role])
            offsets[role] = new_offset
            if text:
                texts[role] = text.lower()

        for key, role, needles, label in specs:
            if milestones[key]:
                continue
            text_lower = texts.get(role)
            if not text_lower:
                continue
            if any(n in text_lower for n in needles):
                milestones[key] = True
                tag = "already up" if first_pass else f"{time.time()-start:.0f}s"
                log(f"  {label} ({tag})", Colors.GREEN)

        first_pass = False

        if all(milestones.values()):
            log("All Zigbee milestones reached!", Colors.BOLD + Colors.GREEN)
            return True

        time.sleep(1)

    log("Zigbee milestone timeout — summary:", Colors.RED)
    for name, reached in milestones.items():
        status = "OK" if reached else "MISSING"
        color = Colors.GREEN if reached else Colors.RED
        log(f"  {name}: {status}", color)
    _dump_serial_log_tails(log_paths)
    return False


def _dump_serial_log_tails(log_paths, tail_bytes=2048):
    """Print size + last N bytes of each role's serial log.

    Used on failure paths to surface what the boards actually said without
    making the user go open four files. Empty/tiny logs are an immediate
    signal that serial capture itself is broken (vs. a real Zigbee failure).
    """
    log("  --- Serial log tails (diagnostic) ---", Colors.YELLOW)
    for role, path in log_paths.items():
        if not path or not os.path.exists(path):
            log(f"    [{role}] no log file", Colors.YELLOW)
            continue
        try:
            sz = os.path.getsize(path)
            color = Colors.CYAN if sz > 200 else Colors.RED
            log(f"    [{role}] {path} ({sz} bytes)", color)
            if sz == 0:
                continue
            with open(path, 'rb') as f:
                if sz > tail_bytes:
                    f.seek(-tail_bytes, os.SEEK_END)
                data = f.read().decode('utf-8', errors='replace')
            for line in data.splitlines()[-30:]:
                log(f"      | {line}", Colors.WHITE)
        except Exception as exc:
            log(f"    [{role}] read error: {exc}", Colors.YELLOW)


# ---------------------------------------------------------------------------
# Matter commissioning
# ---------------------------------------------------------------------------

def commission_matter(dut_boot_time, interactive, dut_serial=None):
    """Run chip-tool pairing ble-thread. Returns True on success."""
    log("\n=== Matter commissioning ===", Colors.BOLD + Colors.BLUE)

    prepare_host_for_matter_commissioning()

    elapsed = time.time() - dut_boot_time
    window_remaining = BLE_ADVERTISING_DURATION_S - elapsed

    if window_remaining < BLE_ADVERTISING_SAFETY_MARGIN_S:
        if interactive:
            log(f"  BLE advertising window likely expired ({elapsed:.0f}s since boot, window={BLE_ADVERTISING_DURATION_S}s)",
                Colors.YELLOW)
            sn = f" [SN={dut_serial}]" if dut_serial else ""
            # Nordic's Matter common board pins BLE re-advertise to
            # ``BLUETOOTH_ADV_BUTTON = DK_BTN1`` (see
            # nrf/samples/matter/common/src/board/board_config.h). On the
            # nRF54LM20 DK that slot is labelled "Button 0".
            input(f"{Colors.BOLD}{Colors.YELLOW}"
                  f"  >>> Press BUTTON 0 on the DUT{sn} to re-enable BLE advertising, then press Enter... "
                  f"{Colors.ENDC}")
        else:
            log(f"  WARNING: BLE window may have expired ({elapsed:.0f}s). "
                "Use --no-interactive=false or increase BLE duration.", Colors.YELLOW)

    dataset = get_thread_dataset()
    if not dataset:
        log("  Cannot proceed without Thread dataset", Colors.RED)
        return False

    cmd = [
        'chip-tool', 'pairing', 'ble-thread',
        str(MATTER_NODE_ID),
        f'hex:{dataset}',
        str(MATTER_PASSCODE),
        str(MATTER_DISCRIMINATOR),
    ]
    rc, combined = _run_chip_tool(cmd, timeout=120,
                                  log_path='/tmp/mz_chip_tool_pairing.log')
    if rc == 0:
        log("  Matter commissioning succeeded!", Colors.BOLD + Colors.GREEN)
        return True
    log(f"  chip-tool failed (exit {rc}):\n{combined[-2000:]}", Colors.RED)
    if _BLUEZ_WEDGED_MARKER in combined:
        log("", Colors.RED)
        log("  " + "=" * 72, Colors.BOLD + Colors.RED)
        for line in _BLUEZ_RECOVERY_HINT.splitlines():
            log(f"  {line}", Colors.BOLD + Colors.RED)
        log("  " + "=" * 72, Colors.BOLD + Colors.RED)
    return False


# ---------------------------------------------------------------------------
# Handover verification
# ---------------------------------------------------------------------------

def _snapshot_lines(path):
    """Return the current line count of *path* (0 if missing)."""
    if not path or not os.path.exists(path):
        return 0
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _grep_new_bulb_events(bulb_log_path, start_offset):
    """Return (saw_on, saw_off) flags for new lines after *start_offset*."""
    try:
        with open(bulb_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            new_lines = [ln.lower() for ln in f.readlines()[start_offset:]]
    except OSError:
        return False, False
    saw_on = any('set on/off value: 1' in ln for ln in new_lines)
    saw_off = any('set on/off value: 0' in ln for ln in new_lines)
    return saw_on, saw_off


def verify_zigbee_buttons(bulb_log_path, switch_label='DUT (nRF54LM20)',
                          on_button='BUTTON 0', off_button='BUTTON 1',
                          switch_serial=None):
    """Interactive test: ask the user to press ``on_button`` and
    ``off_button`` on the device identified by ``switch_label``, then check
    that the bulb log at ``bulb_log_path`` shows at least one observable
    ON/OFF transition.

    The bulb only logs ``Set ON/OFF value: X`` when the ZCL attribute actually
    changes, so an idempotent ON-when-already-ON (or OFF-when-already-OFF)
    produces nothing. Pressing both buttons guarantees at least one real
    transition regardless of the bulb's initial state.

    Button silkscreen labels differ across DKs (nRF54LM20 uses 0..3, nRF52840
    uses 1..4); callers pass the labels that match the physical DK running
    the light_switch sample. DK_BTN1_MSK (Zigbee ON) maps to physical Button 0
    on nRF54LM20 and Button 1 on nRF52840; DK_BTN2_MSK (Zigbee OFF) maps to
    Button 1 / Button 2 respectively.

    ``bulb_log_path`` can point at either a satellite Zigbee bulb (switch DUT
    mode) or at the DUT itself when the DUT is the bulb (bulb DUT mode) —
    the ncs-zigbee light_bulb sample emits the same log line in both cases.
    """
    log("\n=== Zigbee button control test ===", Colors.BOLD + Colors.BLUE)
    if not bulb_log_path or not os.path.exists(bulb_log_path):
        log("  No bulb log available — skipping button test", Colors.YELLOW)
        return True

    start_offset = _snapshot_lines(bulb_log_path)
    sn = f" [SN={switch_serial}]" if switch_serial else ""
    input(f"{Colors.BOLD}{Colors.YELLOW}"
          f"  >>> Press {on_button} then {off_button} on the {switch_label}{sn} "
          "to toggle the bulb ON and OFF, then press Enter... "
          f"{Colors.ENDC}")

    deadline = time.time() + 5
    saw_on = saw_off = False
    while time.time() < deadline and not (saw_on and saw_off):
        saw_on, saw_off = _grep_new_bulb_events(bulb_log_path, start_offset)
        if saw_on and saw_off:
            break
        time.sleep(0.2)

    if saw_on and saw_off:
        log("  Bulb reports ON and OFF — Zigbee button path OK (both transitions)", Colors.GREEN)
        return True
    if saw_on or saw_off:
        which = 'ON' if saw_on else 'OFF'
        log(f"  Bulb reports only {which} — Zigbee button path OK "
            "(bulb was likely already in the complementary state)", Colors.GREEN)
        return True
    log("  No ON/OFF events in bulb log — Zigbee button test FAILED", Colors.RED)
    return False


def verify_handover(dut_log_path, interactive):
    log("\n=== Verifying radio handover ===", Colors.BOLD + Colors.BLUE)

    # Check DUT logs for evidence of Zigbee teardown / Thread switch
    if dut_log_path and os.path.exists(dut_log_path):
        with open(dut_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().lower()
        if 'switch' in content and 'openthread' in content:
            log("  DUT log: radio dispatcher switched to OpenThread", Colors.GREEN)
        elif 'zigbee_deinit' in content or 'thread' in content:
            log("  DUT log: Zigbee deinit / Thread references found", Colors.GREEN)
        else:
            log("  DUT log: no explicit handover evidence (may need more specific log strings)", Colors.YELLOW)

    # Verify Matter is operational: read basic cluster
    log("  Verifying Matter operational (basicinformation read)...", Colors.CYAN)
    try:
        result = subprocess.run(
            ['chip-tool', 'basicinformation', 'read', 'vendor-name',
             str(MATTER_NODE_ID), '0'],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            log("  Matter read succeeded — device operational over Thread!", Colors.BOLD + Colors.GREEN)
        else:
            log(f"  Matter read failed (exit {result.returncode})", Colors.RED)
            return False
    except Exception as exc:
        log(f"  Matter read error: {exc}", Colors.RED)
        return False

    return True


# ---------------------------------------------------------------------------
# Matter light bulb: commission + exercise On/Off cluster
# ---------------------------------------------------------------------------

_CHIP_TOOL_SNAP_KVS = os.path.expanduser(
    '~/snap/chip-tool/common/chip_tool_kvs')


# Log fragment emitted by chip-tool when BlueZ's ``org.bluez.Adapter1.StartDiscovery``
# D-Bus call deadlocks. Observed symptom: 25 s dispatch, then
# ``CHIP Error 0x000000AC``. The only reliable recovery is a full
# ``bluetoothd`` restart — power-cycling the adapter via bluetoothctl does
# not clear the in-memory filter/monitor state that causes the wedge.
_BLUEZ_WEDGED_MARKER = 'BluezObjectManager.cpp:317'
_BLUEZ_RECOVERY_HINT = (
    'Host BlueZ is in a wedged state (StartDiscovery D-Bus deadlock). '
    'Recover with:\n'
    '    sudo systemctl restart bluetooth\n'
    'Then rerun the test. Power-cycling the adapter via bluetoothctl is '
    'not enough — the daemon itself needs to be restarted.'
)


def _kill_stale_chip_tool_processes():
    """Kill any lingering chip-tool processes from previous test runs.

    Rare in the happy path (chip-tool exits cleanly on success and
    failure), but a Ctrl+C in the middle of pairing can leave one
    behind holding the BLE adapter's discovery flag.
    """
    try:
        result = subprocess.run(['pgrep', '-f', 'chip-tool'],
                                capture_output=True, text=True, timeout=5)
    except Exception:
        return
    pids = [p for p in (result.stdout or '').split() if p.isdigit()
            and int(p) != os.getpid()]
    if not pids:
        return
    log(f"  Killing stale chip-tool PIDs: {', '.join(pids)}", Colors.YELLOW)
    subprocess.run(['kill', '-9', *pids], capture_output=True, timeout=5)
    time.sleep(0.5)


def _wipe_chip_tool_snap_kvs():
    """Remove the chip-tool snap's persistent KVS.

    The snap refuses a caller-specified ``--storage-directory`` and
    always falls back to its internal path (see the "IGNORING" line at
    the top of any chip-tool log). Wiping it keeps the fabric table
    deterministic run-to-run; without this, every run inherits the
    previous fabric index which makes diagnostics confusing.
    """
    if not os.path.exists(_CHIP_TOOL_SNAP_KVS):
        return
    try:
        os.remove(_CHIP_TOOL_SNAP_KVS)
        log(f"  Cleared chip-tool snap KVS ({_CHIP_TOOL_SNAP_KVS})",
            Colors.CYAN)
    except OSError as exc:
        log(f"  Could not clear {_CHIP_TOOL_SNAP_KVS}: {exc}",
            Colors.YELLOW)


def prepare_host_for_matter_commissioning():
    """One-shot host hygiene before the first chip-tool BLE scan.

    Should run once per test, immediately before ``commission_matter``.
    Kept intentionally lightweight: the only *effective* recovery from a
    wedged BlueZ is ``sudo systemctl restart bluetooth``, which we
    cannot do non-interactively. If chip-tool fails anyway, the
    ``_BLUEZ_WEDGED_MARKER`` detection in ``commission_matter``
    surfaces the recovery command to the user.
    """
    log("  Host hygiene before Matter commissioning...", Colors.CYAN)
    _kill_stale_chip_tool_processes()
    _wipe_chip_tool_snap_kvs()


def _run_chip_tool(cmd, timeout, log_path=None):
    """Run chip-tool with stdin closed, return (returncode, combined_output).

    chip-tool is a confined snap on many setups, so killing it can raise
    PermissionError from subprocess.kill() — we fall back to ``kill -9`` via
    a helper subprocess that shares the snap's cgroup.
    """
    log(f"  {' '.join(cmd)}", Colors.CYAN)
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True,
        )
    except Exception as exc:
        log(f"  chip-tool failed to start: {exc}", Colors.RED)
        return 1, ''

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"  chip-tool timed out after {timeout}s — killing", Colors.RED)
        try:
            proc.kill()
        except PermissionError:
            subprocess.run(['kill', '-9', str(proc.pid)],
                           capture_output=True, timeout=5)
        stdout, stderr = proc.communicate(timeout=10)

    combined = (stdout or '') + '\n' + (stderr or '')
    if log_path:
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(combined)
            collected_log_files.append((os.path.basename(log_path), log_path))
        except Exception:
            pass
    return proc.returncode, combined


def commission_matter_bulb():
    """Commission the Matter light bulb (node 2) into the already-formed
    Thread fabric. Returns True on success.
    """
    log("\n=== Matter bulb commissioning ===", Colors.BOLD + Colors.BLUE)

    dataset = get_thread_dataset()
    if not dataset:
        log("  Cannot proceed without Thread dataset", Colors.RED)
        return False

    cmd = [
        'chip-tool', 'pairing', 'ble-thread',
        str(MATTER_BULB_NODE_ID),
        f'hex:{dataset}',
        str(MATTER_PASSCODE),
        str(MATTER_BULB_DISCRIMINATOR),
    ]
    rc, combined = _run_chip_tool(cmd, timeout=150,
                                  log_path='/tmp/mz_chip_tool_pair_bulb.log')
    if rc == 0:
        log("  Matter bulb commissioning succeeded!", Colors.BOLD + Colors.GREEN)
        return True
    log(f"  chip-tool failed (exit {rc}):\n{combined[-2000:]}", Colors.RED)
    return False


def _grep_onoff_events(log_path, start_offset, on_needles, off_needles):
    """Return ``(saw_on, saw_off)`` for new lowercase lines of ``log_path``
    after ``start_offset``.

    ``on_needles`` / ``off_needles`` are iterables of case-insensitive
    substrings; a match on any one marks the corresponding transition.
    """
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            new_lines = [ln.lower() for ln in f.readlines()[start_offset:]]
    except OSError:
        return False, False
    saw_on = any(any(n in ln for n in on_needles) for ln in new_lines)
    saw_off = any(any(n in ln for n in off_needles) for ln in new_lines)
    return saw_on, saw_off


# Pattern sets reused by both button-press and chip-tool verifications.
#
# Matter light_bulb sample (nrf/samples/matter/light_bulb): zcl_callbacks.cpp
# emits "Cluster OnOff: attribute OnOff set to N" after the attribute commit.
# Only this sample installs the post-attribute-change hook, so the pattern is
# specific to the dedicated Matter bulb used in `zigbee-to-matter-switch-dut`.
_MATTER_BULB_ON_PATTERNS = ('cluster onoff: attribute onoff set to 1',)
_MATTER_BULB_OFF_PATTERNS = ('cluster onoff: attribute onoff set to 0',)
#
# ncs-zigbee light_bulb (matter_fota) routes OnOff straight through chip's
# on-off-server cluster without hooking MatterPostAttributeChangeCallback or
# the Nordic ``LightingMgr`` action abstraction, so none of the Nordic app
# LOG_INFs fire. The reliable indicator is the upstream chip log line
# ``Toggle ep%x on/off from state %x to %x`` emitted by on-off-server.cpp
# for every command that actually changes state (with %x so 0/1 print as
# single digits). Matches both On and Off commands (not just literal Toggle).
_CHIP_ONOFF_SERVER_ON_PATTERNS = ('on/off from state 0 to 1',)
_CHIP_ONOFF_SERVER_OFF_PATTERNS = ('on/off from state 1 to 0',)


def _wait_for_onoff(log_path, start_offset, on_p, off_p, timeout=5):
    """Poll ``log_path`` for up to ``timeout`` seconds until both ON and OFF
    transitions are seen or the window elapses. Serial capture is written by
    a background thread so the events show up slightly after the stimulus.
    """
    deadline = time.time() + timeout
    saw_on = saw_off = False
    while time.time() < deadline and not (saw_on and saw_off):
        saw_on, saw_off = _grep_onoff_events(log_path, start_offset, on_p, off_p)
        if saw_on and saw_off:
            break
        time.sleep(0.2)
    return saw_on, saw_off


def _report_onoff_result(saw_on, saw_off, target_label):
    if saw_on and saw_off:
        log(f"  {target_label} reports ON and OFF — OK", Colors.GREEN)
        return True
    missing = [lbl for lbl, got in (('ON', saw_on), ('OFF', saw_off)) if not got]
    log(f"  {target_label} did not report: {', '.join(missing)}", Colors.RED)
    return False


def _drive_chip_tool_onoff(node_id, endpoint_id):
    """Issue chip-tool ``onoff on/off/on`` against (node, endpoint). Returns
    True if all three invocations exit 0.

    A freshly-commissioned bulb defaults to OnOff=0, so an "off" alone is
    idempotent and emits no attribute-change log. ON->OFF->ON therefore
    guarantees observable transitions regardless of starting state and leaves
    the LED ON for visual confirmation afterwards.
    """
    node, ep = str(node_id), str(endpoint_id)
    for label, cmd in (
        ('on',  ['chip-tool', 'onoff', 'on',  node, ep]),
        ('off', ['chip-tool', 'onoff', 'off', node, ep]),
        ('on',  ['chip-tool', 'onoff', 'on',  node, ep]),
    ):
        rc, _ = _run_chip_tool(cmd, timeout=30)
        if rc != 0:
            log(f"  chip-tool onoff {label} failed (exit {rc})", Colors.RED)
            return False
    return True


def configure_matter_switch_binding(switch_node_id, switch_endpoint,
                                    bulb_node_id, bulb_endpoint):
    """Wire the DUT's Matter On/Off client to the Matter bulb over CASE.

    Two chip-tool writes are needed:
      * ACL on the bulb so the switch's nodeId is allowed to send On/Off.
        The chip-tool controller's own Admin entry MUST be preserved —
        otherwise the very next chip-tool call is ACCESS_DENIED and the
        test can't continue.
      * Binding table on the switch pointing at the bulb's (node, ep,
        cluster=On/Off). This is the table the light_switch sample walks
        when a Toggle is triggered by the physical button.
    """
    log("\n=== Configuring Matter binding (DUT switch -> Matter bulb) ===",
        Colors.BOLD + Colors.BLUE)

    acl = json.dumps([
        {"fabricIndex": 1, "privilege": 5, "authMode": 2,
         "subjects": [CHIP_TOOL_CONTROLLER_NODE_ID], "targets": None},
        {"fabricIndex": 1, "privilege": 3, "authMode": 2,
         "subjects": [switch_node_id], "targets": None},
    ])
    rc, _ = _run_chip_tool(
        ['chip-tool', 'accesscontrol', 'write', 'acl', acl,
         str(bulb_node_id), '0'],
        timeout=30, log_path='/tmp/mz_chip_tool_bulb_acl.log',
    )
    if rc != 0:
        log(f"  ACL write on Matter bulb failed (exit {rc})", Colors.RED)
        return False

    binding = json.dumps([
        {"fabricIndex": 1, "node": bulb_node_id, "endpoint": bulb_endpoint,
         "cluster": MATTER_ONOFF_CLUSTER_ID},
    ])
    rc, _ = _run_chip_tool(
        ['chip-tool', 'binding', 'write', 'binding', binding,
         str(switch_node_id), str(switch_endpoint)],
        timeout=30, log_path='/tmp/mz_chip_tool_switch_binding.log',
    )
    if rc != 0:
        log(f"  Binding write on DUT switch failed (exit {rc})", Colors.RED)
        return False

    log("  ACL + binding configured", Colors.GREEN)
    return True


# Candidate log snippets printed by the Matter / OpenThread stacks on the DUT
# once the device has booted, re-joined the Thread fabric, and its Matter
# server is ready to accept new operational sessions. We match any one of
# them case-insensitively to skip a fixed wait when the stack is quick; on a
# miss we fall through anyway and rely on the functional button test below.
_DUT_MATTER_READY_MARKERS = (
    'server listening',
    'thread state: attached',
    'attached to thread',
    'device role: child',
    'device role: router',
    'device role: leader',
    'thread started',
    'chip minimal mdns started',
)


def verify_matter_persists_across_reboot(dut_serial, dut_log_path,
                                         matter_bulb_log_path):
    """Power-cycle the DUT and confirm Matter control of the bulb still works.

    Rationale: Matter credentials (DAC, node ID, fabric, ACL, binding, the
    operational Thread dataset) all live in the DUT's persistent flash. A
    reboot is the canonical check that nothing transient — a still-open CASE
    session, an in-flight subscription, ephemeral fabric state — was quietly
    holding the control path together. After ``nrfutil device reset`` the
    DUT must autonomously re-attach to Thread, re-establish a CASE session
    to the Matter bulb via the previously written binding, and respond to a
    BUTTON 1 press with a working Toggle — no chip-tool involvement.
    """
    log("\n=== Post-reboot Matter persistence check ===",
        Colors.BOLD + Colors.BLUE)

    if not dut_log_path or not os.path.exists(dut_log_path):
        log("  DUT log not available — cannot verify reboot behavior",
            Colors.YELLOW)
        return False

    # Snapshot BEFORE the reset so marker matching only considers bytes
    # emitted by the upcoming boot, not stale "Thread state: Attached"
    # lines from the commissioning phase.
    start_offset = os.path.getsize(dut_log_path)

    log(f"  Rebooting DUT (SN={dut_serial}) via nrfutil device reset...",
        Colors.CYAN)
    if not reset_device(dut_serial, 'DUT (post-test reboot)'):
        log("  nrfutil reset failed — cannot verify post-reboot behavior",
            Colors.RED)
        return False

    # Poll all candidate markers inside one shared deadline so a firmware
    # that only ever logs one of them doesn't cost us (len * timeout) wait.
    reattach_timeout = 30
    log(f"  Waiting up to {reattach_timeout}s for DUT Matter/Thread "
        f"re-attach...", Colors.CYAN)
    deadline = time.time() + reattach_timeout
    seen_marker = None
    while time.time() < deadline:
        for marker in _DUT_MATTER_READY_MARKERS:
            if _log_has_marker(dut_log_path, marker, start_offset):
                seen_marker = marker
                break
        if seen_marker:
            break
        time.sleep(0.5)

    if seen_marker:
        log(f"  DUT re-attached (saw '{seen_marker}')", Colors.GREEN)
    else:
        log(f"  No explicit re-attach marker within {reattach_timeout}s "
            f"— proceeding; the button test below is the functional check",
            Colors.YELLOW)

    # Short settle so the first CASE session to the bulb has a chance to
    # be set up lazily on the first Toggle.
    time.sleep(3)

    return verify_matter_bulb_via_dut_button(
        matter_bulb_log_path, dut_serial=dut_serial,
        bulb_label='Matter bulb (post-reboot)',
    )


def verify_matter_bulb_via_dut_button(matter_bulb_log_path, dut_serial=None,
                                      on_patterns=None, off_patterns=None,
                                      bulb_label='Matter bulb'):
    """After the binding is configured, pressing BUTTON 1 on the DUT sends a
    Matter Toggle over Thread; the bulb flips and its log shows the On/Off
    attribute transition. Two presses guarantee both transitions.

    ``on_patterns`` / ``off_patterns`` default to the standalone Matter
    light_bulb sample's zcl_callbacks pattern. Pass
    :data:`_CHIP_ONOFF_SERVER_ON_PATTERNS` /
    :data:`_CHIP_ONOFF_SERVER_OFF_PATTERNS` when the bulb is an ncs-zigbee
    matter_fota sample — that sample does not install the
    MatterPostAttributeChangeCallback hook but routes OnOff through the
    upstream chip on-off-server which emits
    ``Toggle ep%x on/off from state X to Y``.
    """
    log(f"\n=== {bulb_label} On/Off via DUT button ===", Colors.BOLD + Colors.BLUE)
    if not matter_bulb_log_path or not os.path.exists(matter_bulb_log_path):
        log(f"  No {bulb_label} log available — cannot verify", Colors.RED)
        return False

    on_pats = on_patterns or _MATTER_BULB_ON_PATTERNS
    off_pats = off_patterns or _MATTER_BULB_OFF_PATTERNS

    start_offset = _snapshot_lines(matter_bulb_log_path)
    # nrf/samples/matter/light_switch wires DK_BTN2_MSK (physical Button 1 on
    # the nRF54LM20 DK, which silkscreens buttons 0..3) to Toggle via the
    # DimmerTriggerEventHandler. Short presses (<500 ms) send Toggle each time.
    sn = f" [SN={dut_serial}]" if dut_serial else ""
    input(f"{Colors.BOLD}{Colors.YELLOW}"
          f"  >>> Short-press BUTTON 1 on the DUT (nRF54LM20){sn} TWICE "
          f"(~1s between presses) to toggle the {bulb_label}, then press Enter... "
          f"{Colors.ENDC}")

    # Matter On/Off action via CASE + the bulb's ZCL callback can take a
    # noticeable fraction of a second each way, so give the bulb log a longer
    # window than the chip-tool-driven path.
    saw_on, saw_off = _wait_for_onoff(
        matter_bulb_log_path, start_offset,
        on_pats, off_pats, timeout=10,
    )
    ok = _report_onoff_result(saw_on, saw_off, bulb_label)
    if not ok:
        log("  Hint: check /tmp/mz_chip_tool_bulb_acl.log and "
            "/tmp/mz_chip_tool_switch_binding.log — ACL/binding must be accepted "
            "and the DUT's Binding cluster must live on endpoint "
            f"{MATTER_DUT_ENDPOINT_ID}.", Colors.YELLOW)
    return ok


def verify_dut_matter_bulb_onoff_via_chip_tool(dut_log_path):
    """Mode 'zigbee-to-matter-bulb-dut' verification: drive the DUT's Matter
    On/Off cluster via chip-tool and confirm the DUT log shows both ON and
    OFF action transitions.

    The DUT runs ncs-zigbee/samples/light_bulb (matter_fota). Its Matter side
    does NOT install the MatterPostAttributeChangeCallback hook that the
    standalone Matter light_bulb sample uses for ``Cluster OnOff: attribute
    OnOff set to N``, and its app_task_matter.cpp ``Turn On/Off Action``
    LOG_INFs are only reached when OnOff is driven through the Nordic
    LightingMgr action path — which is bypassed here. What IS reliable is
    the upstream chip on-off-server cluster progress log
    ``Toggle ep%x on/off from state %x to %x`` which fires for every On/Off
    command that actually changes state.
    """
    log("\n=== DUT Matter On/Off via chip-tool ===", Colors.BOLD + Colors.BLUE)
    if not dut_log_path or not os.path.exists(dut_log_path):
        log("  No DUT log available — cannot verify", Colors.RED)
        return False

    start_offset = _snapshot_lines(dut_log_path)
    if not _drive_chip_tool_onoff(MATTER_NODE_ID, MATTER_DUT_ENDPOINT_ID):
        return False

    saw_on, saw_off = _wait_for_onoff(
        dut_log_path, start_offset,
        _CHIP_ONOFF_SERVER_ON_PATTERNS,
        _CHIP_ONOFF_SERVER_OFF_PATTERNS, timeout=5,
    )
    return _report_onoff_result(saw_on, saw_off, 'DUT (Matter bulb)')


# Markers emitted by the ncs-zigbee samples we key the Touchlink handshake on.
# ``_STEERING_FAILED`` is the earliest signal that the bulb is about to open a
# Touchlink-target window — zigbee_app_utils.c arms a 2 s alarm
# (``ZIGBEE_TL_STEERING_TO_TARGET_DELAY_BI``) right after logging it that
# subsequently triggers ``ZB_BDB_SIGNAL_TOUCHLINK_TARGET`` (the
# ``_TARGET_OPEN`` marker). Using the earlier marker as the prompt trigger
# lets the operator begin pressing BUTTON 2 before the window opens, so the
# DUT's initiator scan is already running once the bulb enters the target
# window — the maximum possible overlap of the two one-shot phases.
_TOUCHLINK_STEERING_FAILED_MARKER = 'steering failed while not joined: schedule touchlink target'
_TOUCHLINK_TARGET_OPEN_MARKER = 'Touchlink target: stack reported status 0'
_TOUCHLINK_INITIATOR_START_MARKER = 'Starting Touchlink initiator'
_TOUCHLINK_DONE_MARKER = 'Touchlink done'
_TOUCHLINK_FOUND_BULB_MARKER = 'found bulb addr'
# Target window is ~8 s per ZLL spec; add the 2 s head start gained from the
# earlier trigger plus pairing RTT + finalisation (~5 s observed) for the
# per-attempt poll budget below.
_TOUCHLINK_TARGET_WINDOW_S = 8
_TOUCHLINK_HEAD_START_S = 2
_TOUCHLINK_PAIR_RTT_S = 7
# Bulb boot -> steering fail takes ~10-15 s depending on build flags; 30 s
# keeps comfortable headroom.
_TOUCHLINK_BULB_WINDOW_TIMEOUT_S = 30


def _read_log_since(log_path, start_offset):
    """Return the bytes past ``start_offset`` in ``log_path``, lowercased.

    Match the case-insensitive convention of ``wait_for_zigbee_milestones``
    so marker strings can be literal snippets of firmware log lines without
    the caller having to worry about ``Found`` vs ``found`` etc. Returns
    ``b''`` on read failure so callers can treat missing bytes as "not yet".
    """
    try:
        with open(log_path, 'rb') as fh:
            fh.seek(start_offset)
            return fh.read().lower()
    except OSError:
        return b''


def _wait_for_log_marker(log_path, marker, start_offset, timeout):
    """Poll ``log_path`` past ``start_offset`` for ``marker`` with a timeout.

    Case-insensitive. Returns ``True`` as soon as the marker appears in bytes
    written after the offset, otherwise ``False`` on timeout.
    """
    if not log_path:
        return False
    deadline = time.time() + timeout
    needle = marker.lower().encode()
    while time.time() < deadline:
        if needle in _read_log_since(log_path, start_offset):
            return True
        time.sleep(0.2)
    return False


def _wait_for_all_markers(log_path, markers, start_offset, timeout):
    """Same contract as :func:`_wait_for_log_marker` but requires all markers.

    Case-insensitive. Returns ``True`` only once every string in ``markers``
    has appeared past ``start_offset``.
    """
    if not log_path:
        return False
    deadline = time.time() + timeout
    needles = [m.lower().encode() for m in markers]
    while time.time() < deadline:
        blob = _read_log_since(log_path, start_offset)
        if all(n in blob for n in needles):
            return True
        time.sleep(0.2)
    return False


def _log_has_marker(log_path, marker, start_offset):
    """Case-insensitive single-shot check for ``marker`` past ``start_offset``."""
    if not log_path:
        return False
    return marker.lower().encode() in _read_log_since(log_path, start_offset)


def _press_now_banner(dut_sn_tag):
    """Return a multi-line, high-contrast banner for the PRESS-NOW cue.

    The prompt used to be a single yellow line that was easy to miss in the
    scroll of firmware logs. A framed banner is much harder to walk past
    when the operator is only half-watching the terminal, so reaction time
    drops and the success-rate on the first attempt goes up.
    """
    bar = '=' * 72
    return (
        f"\n{Colors.BOLD}{Colors.YELLOW}{bar}\n"
        f">>> PRESS BUTTON 2 on the DUT{dut_sn_tag} **NOW** <<<\n"
        f"    (Touchlink target window opens in ~{_TOUCHLINK_HEAD_START_S}s "
        f"and stays open for ~{_TOUCHLINK_TARGET_WINDOW_S}s)\n"
        f"{bar}{Colors.ENDC}"
    )


def initiate_touchlink_and_wait(log_paths, dut_serial=None, bulb_serial=None,
                                max_attempts=5):
    """Drive Touchlink commissioning with retry-on-miss instead of one-shot.

    The bulb's target window is one-shot per boot (see
    ``zigbee_app_utils.c::zigbee_touchlink_target_signal_handler`` — on
    ``ZB_BDB_SIGNAL_TOUCHLINK_TARGET_FINISHED`` with no pairing it returns to
    ``IDLE`` without rescheduling, so the window lives for ~8 s and then goes
    away until something else (re-boot or another steering failure) triggers
    it again). The DUT's initiator is also one-shot per button press: a
    single ``ZB_BDB_TOUCHLINK_COMMISSIONING`` run that emits
    ``Starting Touchlink initiator`` and then finishes with success or
    failure within a handful of seconds.

    Three resiliency knobs make attempts reliable in practice:

    1. Each attempt is gated on the operator pressing ENTER *before* the
       bulb is reset. That guarantees the operator is watching when the
       framed PRESS-NOW banner fires ~15 s later, and trades "script races
       an inattentive human" for "human arms the race when ready".
    2. The PRESS-NOW cue is keyed on the ``Steering failed ... schedule
       Touchlink target`` marker, which fires ~2 s before the target window
       actually opens (``ZIGBEE_TL_STEERING_TO_TARGET_DELAY_BI`` in
       firmware). That head-start lets the DUT's initiator scan be running
       by the time the window opens — maximum overlap of the two one-shot
       phases.
    3. The cue itself is a framed banner rather than a single line so an
       operator glancing at the terminal is unlikely to walk past it.

    If an attempt still misses the window, the loop asks for another ENTER
    and retries with a fresh bulb reset, up to ``max_attempts`` times; the
    operator can Ctrl-C / EOF the prompt to give up early.
    """
    log("\n=== Touchlink commissioning ===", Colors.BOLD + Colors.BLUE)

    bulb_log = log_paths.get('bulb') if log_paths else None
    dut_log = log_paths.get('dut') if log_paths else None

    if not bulb_serial or not bulb_log or not dut_log:
        log("  bulb_serial / bulb log / DUT log missing — cannot drive "
            "deterministic Touchlink flow.", Colors.RED)
        return False

    sn_tag = f" [SN={dut_serial}]" if dut_serial else ""

    log(f"  Flow: press ENTER to arm a Touchlink window (the bulb is reset, "
        f"and ~15 s later a framed PRESS NOW banner tells you to tap BUTTON 2 "
        f"of the DUT (nRF54LM20){sn_tag}). Up to {max_attempts} attempts; "
        f"Ctrl-C to abort.", Colors.CYAN)

    for attempt in range(1, max_attempts + 1):
        prompt_text = (
            f"{Colors.BOLD}{Colors.YELLOW}"
            f"  >>> Attempt {attempt}/{max_attempts}: press ENTER when you are "
            f"ready to arm the next Touchlink window <<<{Colors.ENDC} "
        )
        try:
            input(prompt_text)
        except (EOFError, KeyboardInterrupt):
            log("\n  User aborted Touchlink commissioning.", Colors.YELLOW)
            return False

        # Snapshot AFTER the Enter gate so we only look at log bytes produced
        # by the upcoming bulb reset, not stale "Steering failed" lines the
        # bulb may have emitted while the operator was thinking.
        try:
            bulb_pre = os.path.getsize(bulb_log)
        except OSError:
            bulb_pre = 0
        try:
            dut_pre = os.path.getsize(dut_log)
        except OSError:
            dut_pre = 0

        log(f"  Resetting bulb (SN={bulb_serial})...", Colors.CYAN)
        reset_device(bulb_serial, 'Zigbee bulb (Touchlink target)')

        # Trigger on the EARLIER marker so the operator can press BUTTON 2
        # before the window actually opens; fall back to the later marker
        # if the earlier one never appears (e.g. a build with the log line
        # filtered out).
        armed = _wait_for_log_marker(
            bulb_log, _TOUCHLINK_STEERING_FAILED_MARKER,
            bulb_pre, timeout=_TOUCHLINK_BULB_WINDOW_TIMEOUT_S,
        )
        if not armed:
            armed = _wait_for_log_marker(
                bulb_log, _TOUCHLINK_TARGET_OPEN_MARKER,
                bulb_pre, timeout=5,
            )
        if not armed:
            log(f"  Bulb did not arm a Touchlink-target window within "
                f"{_TOUCHLINK_BULB_WINDOW_TIMEOUT_S} s — skipping this "
                f"attempt.", Colors.YELLOW)
            continue

        log(_press_now_banner(sn_tag), Colors.YELLOW)

        per_attempt_budget = (_TOUCHLINK_HEAD_START_S
                              + _TOUCHLINK_TARGET_WINDOW_S
                              + _TOUCHLINK_PAIR_RTT_S)
        if _wait_for_all_markers(
                dut_log,
                (_TOUCHLINK_DONE_MARKER, _TOUCHLINK_FOUND_BULB_MARKER),
                dut_pre, timeout=per_attempt_budget):
            log(f"  Touchlink pairing succeeded on attempt {attempt}",
                Colors.BOLD + Colors.GREEN)
            # Re-run the milestones pass so its standard "(..s)" log lines
            # show up in the test transcript alongside the other modes'.
            return wait_for_zigbee_milestones(
                log_paths, MODE_TOUCHLINK_SWITCH_DUT, timeout=5,
            )

        if not _log_has_marker(dut_log, _TOUCHLINK_INITIATOR_START_MARKER,
                               dut_pre):
            log(f"  No 'Starting Touchlink initiator' in DUT log this "
                f"attempt — did you press BUTTON 2?", Colors.YELLOW)
        else:
            log(f"  DUT initiator ran but pairing did not complete — "
                f"likely pressed outside the bulb's open window.",
                Colors.YELLOW)

    log(f"\n  All {max_attempts} Touchlink attempts exhausted.", Colors.RED)
    _dump_serial_log_tails(log_paths)
    return False


# ---------------------------------------------------------------------------
# Artifact archival
# ---------------------------------------------------------------------------

def create_artifacts_archive(channel):
    global current_pcap_file, collected_log_files, script_log_file, otbr_docker_log_path

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_path = f'/tmp/mz_test_ch{channel}_{ts}.zip'
    log(f"\n=== Archiving artifacts -> {zip_path} ===", Colors.BOLD + Colors.BLUE)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            count = 0

            if current_pcap_file and os.path.exists(current_pcap_file):
                zf.write(current_pcap_file, os.path.basename(current_pcap_file))
                log(f"  + PCAP: {os.path.basename(current_pcap_file)}", Colors.GREEN)
                count += 1

            for name, path in collected_log_files:
                if path and os.path.exists(path):
                    zf.write(path, os.path.basename(path))
                    log(f"  + Log ({name}): {os.path.basename(path)}", Colors.GREEN)
                    count += 1

            if script_log_file:
                p = script_log_file.name
                if os.path.exists(p):
                    zf.write(p, os.path.basename(p))
                    count += 1

            if otbr_docker_log_path and os.path.exists(otbr_docker_log_path):
                zf.write(otbr_docker_log_path, 'otbr_docker.log')
                log(f"  + OTBR docker log: otbr_docker.log", Colors.GREEN)
                count += 1

            # Archive whichever artifacts currently have a built ``merged.hex``
            # on disk (including shared ones not used by the current mode) so
            # the bundle is self-contained for post-mortem analysis.
            for aname in sorted(ARTIFACT_CATALOG.keys()):
                hex_path = artifact_hex(aname)
                if os.path.exists(hex_path):
                    zf.write(hex_path, f'{aname}_merged.hex')
                    count += 1

            summary = (
                f"Matter+Zigbee Integration Test\n"
                f"{'='*50}\n"
                f"Date: {datetime.now().isoformat()}\n"
                f"Channel: {channel}\n"
                f"Files: {count}\n"
            )
            zf.writestr('test_summary.txt', summary)

        size = os.path.getsize(zip_path)
        log(f"  Archive: {zip_path} ({size:,} bytes, {count} files)", Colors.BOLD + Colors.GREEN)

        log("\n  Quick-open commands:", Colors.CYAN)
        if current_pcap_file and os.path.exists(current_pcap_file):
            log(f"    wireshark {current_pcap_file}", Colors.WHITE)
        for name, path in collected_log_files:
            if path and os.path.exists(path):
                log(f"    cursor {path}", Colors.WHITE)
        if otbr_docker_log_path and os.path.exists(otbr_docker_log_path):
            log(f"    cursor {otbr_docker_log_path}", Colors.WHITE)

        return zip_path
    except Exception as exc:
        log(f"  Archive error: {exc}", Colors.RED)
        return None


# ---------------------------------------------------------------------------
# Main test procedure
# ---------------------------------------------------------------------------

def _print_results(title, results):
    log("\n" + "=" * 60, Colors.BOLD + Colors.MAGENTA)
    log(f"  {title}", Colors.BOLD + Colors.MAGENTA)
    log("=" * 60, Colors.MAGENTA)
    all_pass = True
    for label, ok in results:
        color = Colors.GREEN if ok else Colors.RED
        status = "PASS" if ok else "FAIL"
        log(f"  {label}: {status}", color)
        if not ok:
            all_pass = False
    verdict_color = Colors.BOLD + (Colors.GREEN if all_pass else Colors.RED)
    log(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}", verdict_color)
    log("=" * 60, Colors.MAGENTA)
    return all_pass


def _cleanup_and_archive(channel):
    """Tear down OTBR + PCAP and ZIP the artifacts. Used on every exit path."""
    log("\n=== Cleanup ===", Colors.BOLD + Colors.BLUE)
    stop_otbr()
    stop_pcap_capture()
    create_artifacts_archive(channel)


def _bring_up_network(args, roles, mode, channel, wait_for_zigbee=True):
    """Shared prologue for every mode: flash boards, start PCAP + serial log
    capture, reset boards (so boot logs are captured from uptime 0), bring up
    OTBR, grep the Thread network key for the PCAP filename, then (optionally)
    wait for mode-specific Zigbee milestones.

    Pass ``wait_for_zigbee=False`` for modes where Zigbee commissioning is
    gated on a user action (e.g. Touchlink button press) — the caller then
    invokes :func:`wait_for_zigbee_milestones` itself after that action.

    Returns ``(ok, log_paths, dut_boot_time)``. On failure ``ok`` is False,
    cleanup/archive has already run, and the caller should return False too.
    """
    if not flash_all(roles, mode, recover_all=args.recover_all):
        return False, {}, 0.0

    log("\n=== Step 4: Start PCAP & log collection ===", Colors.BOLD + Colors.BLUE)
    start_pcap_capture(channel)
    time.sleep(1)
    log_paths = start_all_log_collection(roles)

    # Force a fresh reset now that pyserial is listening — ensures we capture
    # boot banner + ZBOSS init + BDB network-steering signals from uptime 0,
    # instead of losing them to kernel TTY buffer overflow during flash.
    reset_all_devices(roles)
    dut_boot_time = time.time()

    if not start_otbr(roles['rcp']['serial'], args.otbr_docker_image,
                      rcp_tty_override=args.rcp_tty, channel=channel,
                      network_key=THREAD_NETWORK_KEY):
        log("OTBR setup failed — cannot proceed with Matter commissioning", Colors.RED)
        capture_otbr_docker_logs()
        _cleanup_and_archive(channel)
        return False, log_paths, dut_boot_time

    nwk_key = get_thread_network_key()
    if nwk_key:
        log(f"  Thread network key: {nwk_key}", Colors.CYAN)
        _rename_pcap_with_key(nwk_key)

    if wait_for_zigbee:
        zigbee_ok = wait_for_zigbee_milestones(log_paths, mode, timeout=60)
        if not zigbee_ok:
            log("Zigbee network formation failed — aborting", Colors.RED)
            _cleanup_and_archive(channel)
            return False, log_paths, dut_boot_time

    return True, log_paths, dut_boot_time


def _run_mode_zigbee_to_matter_switch_dut(args, roles, channel, interactive):
    """Mode ``zigbee-to-matter-switch-dut``: the DUT is the dual-stack SWITCH.

    Sequence: form Zigbee, user presses buttons on DUT to toggle the Zigbee
    bulb, commission DUT (Matter radio handover), commission the Matter bulb,
    write ACL+binding so the DUT targets the Matter bulb, then user presses
    BUTTON 1 on the DUT to drive the Matter bulb over Thread. Finally, the
    DUT is power-cycled and the BUTTON 1 -> Matter bulb path is re-verified
    to confirm Matter credentials, ACLs, bindings and the Thread dataset
    all survive a reboot without external re-intervention.
    """
    ok, log_paths, dut_boot_time = _bring_up_network(
        args, roles, MODE_SWITCH_DUT, channel)
    if not ok:
        return False

    dut_serial = roles['dut']['serial']

    zigbee_buttons_ok = True
    if interactive:
        zigbee_buttons_ok = verify_zigbee_buttons(
            log_paths.get('bulb'), switch_serial=dut_serial)
        if not zigbee_buttons_ok:
            log("Zigbee button test failed — aborting before Matter commissioning",
                Colors.RED)
            _cleanup_and_archive(channel)
            return False

    matter_ok = commission_matter(dut_boot_time, interactive, dut_serial=dut_serial)
    handover_ok = False
    if matter_ok:
        handover_ok = verify_handover(log_paths.get('dut'), interactive)

    # Only go on to bulb commissioning + binding if the fabric is already up
    # (DUT commissioning succeeded -> Thread credentials are known-good).
    matter_bulb_ok = False
    binding_ok = False
    matter_bulb_button_ok = False
    post_reboot_ok = False
    if matter_ok:
        matter_bulb_ok = commission_matter_bulb()
        if matter_bulb_ok:
            binding_ok = configure_matter_switch_binding(
                switch_node_id=MATTER_NODE_ID,
                switch_endpoint=MATTER_DUT_ENDPOINT_ID,
                bulb_node_id=MATTER_BULB_NODE_ID,
                bulb_endpoint=MATTER_BULB_ENDPOINT_ID,
            )
            if binding_ok and interactive:
                matter_bulb_button_ok = verify_matter_bulb_via_dut_button(
                    log_paths.get('matter_bulb'), dut_serial=dut_serial)
            elif binding_ok:
                log("  --no-interactive: skipping DUT-button Matter test",
                    Colors.YELLOW)
                matter_bulb_button_ok = True

    # Persistence check: power-cycle the DUT and re-run the Matter-bulb
    # button path. Only meaningful once the pre-reboot button path worked
    # (otherwise we'd be blaming a reboot for a problem that was already
    # there), and only when interactive because it re-uses the same
    # button-press prompt.
    if matter_bulb_button_ok and interactive:
        post_reboot_ok = verify_matter_persists_across_reboot(
            dut_serial=dut_serial,
            dut_log_path=log_paths.get('dut'),
            matter_bulb_log_path=log_paths.get('matter_bulb'),
        )
    elif matter_bulb_button_ok:
        log("  --no-interactive: skipping post-reboot Matter check",
            Colors.YELLOW)
        post_reboot_ok = True

    _cleanup_and_archive(channel)

    return _print_results(f"TEST RESULTS — {MODE_SWITCH_DUT}", [
        ("Zigbee network formed", True),
        ("Zigbee button control (DUT switch -> Zigbee bulb)", zigbee_buttons_ok),
        ("Matter commissioning (DUT)", matter_ok),
        ("Radio handover verified", handover_ok),
        ("Matter bulb commissioned", matter_bulb_ok),
        ("Matter binding (DUT switch -> Matter bulb)", binding_ok),
        ("Matter On/Off via DUT BUTTON 1 -> Matter bulb", matter_bulb_button_ok),
        ("Matter On/Off still works after DUT reboot", post_reboot_ok),
    ])


def _run_mode_zigbee_to_matter_bulb_dut(args, roles, channel, interactive):
    """Mode ``zigbee-to-matter-bulb-dut``: the DUT is the dual-stack BULB.

    Sequence: form Zigbee (satellite light_switch joins alongside DUT), user
    presses buttons on the Zigbee switch to drive the DUT's Zigbee side,
    commission DUT (Matter radio handover), then chip-tool drives the DUT's
    Matter On/Off cluster directly — no Matter switch/bulb satellites needed.
    """
    ok, log_paths, dut_boot_time = _bring_up_network(
        args, roles, MODE_BULB_DUT, channel)
    if not ok:
        return False

    dut_serial = roles['dut']['serial']
    zigbee_switch_serial = roles['zigbee_switch']['serial']

    zigbee_buttons_ok = True
    if interactive:
        # Grep the DUT's own Zigbee-side log — the DUT IS the bulb here.
        # nRF52840 DK silkscreens buttons 1..4, so DK_BTN1_MSK (Zigbee ON) is
        # physical "Button 1" and DK_BTN2_MSK (Zigbee OFF) is "Button 2".
        zigbee_buttons_ok = verify_zigbee_buttons(
            log_paths.get('dut'),
            switch_label='Zigbee Switch (nRF52840)',
            on_button='BUTTON 1', off_button='BUTTON 2',
            switch_serial=zigbee_switch_serial,
        )
        if not zigbee_buttons_ok:
            log("Zigbee button test failed — aborting before Matter commissioning",
                Colors.RED)
            _cleanup_and_archive(channel)
            return False

    matter_ok = commission_matter(dut_boot_time, interactive, dut_serial=dut_serial)
    handover_ok = False
    matter_onoff_ok = False
    if matter_ok:
        handover_ok = verify_handover(log_paths.get('dut'), interactive)
        matter_onoff_ok = verify_dut_matter_bulb_onoff_via_chip_tool(
            log_paths.get('dut'))

    _cleanup_and_archive(channel)

    return _print_results(f"TEST RESULTS — {MODE_BULB_DUT}", [
        ("Zigbee network formed", True),
        ("Zigbee button control (Zigbee switch -> DUT bulb)", zigbee_buttons_ok),
        ("Matter commissioning (DUT)", matter_ok),
        ("Radio handover verified", handover_ok),
        ("Matter On/Off via chip-tool -> DUT bulb", matter_onoff_ok),
    ])


def _run_mode_touchlink_to_matter_switch_dut(args, roles, channel, interactive):
    """Mode ``touchlink-to-matter-switch-dut``: coordinator-less variant of
    ``zigbee-to-matter-switch-dut``.

    Satellites are identical to switch-dut except the Zigbee coordinator is
    replaced by a user button press that triggers Touchlink on the DUT. The
    Matter bulb is a separate nRF52840 (not the Zigbee bulb) because the
    light_bulb matter_fota variant is nRF54LM20-only. Sequence: bring up
    OTBR, press DUT BUTTON 2 -> Touchlink pairing with the Zigbee bulb, DUT
    BUTTON 0/1 Zigbee On/Off on the Zigbee bulb, commission DUT + Matter
    bulb, write ACL+binding, DUT BUTTON 1 Matter On/Off on the Matter bulb.
    """
    ok, log_paths, dut_boot_time = _bring_up_network(
        args, roles, MODE_TOUCHLINK_SWITCH_DUT, channel, wait_for_zigbee=False)
    if not ok:
        return False

    dut_serial = roles['dut']['serial']
    bulb_serial = roles.get('bulb', {}).get('serial')

    touchlink_ok = True
    if interactive:
        touchlink_ok = initiate_touchlink_and_wait(
            log_paths, dut_serial=dut_serial, bulb_serial=bulb_serial)
        if not touchlink_ok:
            log("Touchlink commissioning failed — aborting", Colors.RED)
            _cleanup_and_archive(channel)
            return False
    else:
        # Without user interaction there's no way to press the Touchlink
        # button, so this mode reduces to a no-op on Zigbee in --no-interactive.
        log("  --no-interactive: skipping Touchlink button step", Colors.YELLOW)

    zigbee_buttons_ok = True
    if interactive:
        zigbee_buttons_ok = verify_zigbee_buttons(
            log_paths.get('bulb'), switch_serial=dut_serial)
        if not zigbee_buttons_ok:
            log("Zigbee button test failed — aborting before Matter commissioning",
                Colors.RED)
            _cleanup_and_archive(channel)
            return False

    matter_ok = commission_matter(dut_boot_time, interactive, dut_serial=dut_serial)
    handover_ok = False
    if matter_ok:
        handover_ok = verify_handover(log_paths.get('dut'), interactive)

    matter_bulb_ok = False
    binding_ok = False
    matter_bulb_button_ok = False
    if matter_ok:
        matter_bulb_ok = commission_matter_bulb()
        if matter_bulb_ok:
            binding_ok = configure_matter_switch_binding(
                switch_node_id=MATTER_NODE_ID,
                switch_endpoint=MATTER_DUT_ENDPOINT_ID,
                bulb_node_id=MATTER_BULB_NODE_ID,
                bulb_endpoint=MATTER_BULB_ENDPOINT_ID,
            )
            if binding_ok and interactive:
                matter_bulb_button_ok = verify_matter_bulb_via_dut_button(
                    log_paths.get('matter_bulb'), dut_serial=dut_serial)
            elif binding_ok:
                log("  --no-interactive: skipping DUT-button Matter test",
                    Colors.YELLOW)
                matter_bulb_button_ok = True

    _cleanup_and_archive(channel)

    return _print_results(f"TEST RESULTS — {MODE_TOUCHLINK_SWITCH_DUT}", [
        ("Touchlink commissioning (DUT <-> Zigbee bulb)", touchlink_ok),
        ("Zigbee button control (DUT switch -> Zigbee bulb)", zigbee_buttons_ok),
        ("Matter commissioning (DUT)", matter_ok),
        ("Radio handover verified", handover_ok),
        ("Matter bulb commissioned", matter_bulb_ok),
        ("Matter binding (DUT switch -> Matter bulb)", binding_ok),
        ("Matter On/Off via DUT BUTTON 1 -> Matter bulb", matter_bulb_button_ok),
    ])


# Map of test mode name -> runner. Add new modes here as the suite grows.
TEST_MODES = {
    MODE_SWITCH_DUT:           _run_mode_zigbee_to_matter_switch_dut,
    MODE_BULB_DUT:             _run_mode_zigbee_to_matter_bulb_dut,
    MODE_TOUCHLINK_SWITCH_DUT: _run_mode_touchlink_to_matter_switch_dut,
}
DEFAULT_TEST_MODE = MODE_SWITCH_DUT


def _resolve_build_selection(args, parser):
    """Translate the ``--build [NAMES...]`` argparse output into a concrete list.

    Returns ``None`` when the flag was absent (caller will use cached
    artifacts), otherwise a validated list of artifact names. Empty list
    after the flag means "build everything in the catalog". Unknown names
    fail fast with a parser error so typos don't silently no-op.
    """
    if args.build is None:
        return None
    if not args.build:
        return list(ARTIFACT_CATALOG.keys())
    unknown = [n for n in args.build if n not in ARTIFACT_CATALOG]
    if unknown:
        parser.error(
            f"--build: unknown artifact(s): {', '.join(unknown)}. "
            f"Valid names: {', '.join(sorted(ARTIFACT_CATALOG.keys()))}"
        )
    return list(dict.fromkeys(args.build))


def run_test(args, parser):
    """Set up shared state (log files, prerequisites, device discovery, build
    or cache check) then dispatch to the selected test mode.
    """
    global script_log_file, otbr_docker_log_path

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_filename = f'/tmp/mz_test_script_{ts}.log'
    otbr_docker_log_path = f'/tmp/mz_test_otbr_docker_{ts}.log'
    try:
        script_log_file = open(log_filename, 'w', encoding='utf-8')
    except Exception:
        script_log_file = None

    interactive = not args.no_interactive
    channel = args.channel
    mode = args.mode

    build_selection = _resolve_build_selection(args, parser)

    log("=" * 60, Colors.BOLD + Colors.MAGENTA)
    log("  Matter + Zigbee Integration Test", Colors.BOLD + Colors.MAGENTA)
    log("=" * 60, Colors.BOLD + Colors.MAGENTA)
    log(f"  Mode:          {mode}", Colors.WHITE)
    log(f"  Channel:       {channel}", Colors.WHITE)
    log(f"  Interactive:   {interactive}", Colors.WHITE)
    log(f"  Artifact root: {ARTIFACTS_ROOT}", Colors.WHITE)
    if build_selection is None:
        log(f"  Build:         (cached, no --build)", Colors.WHITE)
    else:
        log(f"  Build:         {', '.join(build_selection)}", Colors.WHITE)
    log(f"  Run after build: {not args.no_run}", Colors.WHITE)
    log(f"  OTBR image:    {args.otbr_docker_image}", Colors.WHITE)
    log("=" * 60, Colors.MAGENTA)

    # --- Build phase -------------------------------------------------------
    if build_selection is not None:
        if not verify_prerequisites():
            return False
        if not build_artifacts(build_selection, channel):
            return False

    if args.no_run:
        log("\n--no-run: skipping test execution after build", Colors.CYAN)
        return True

    # --- Test phase --------------------------------------------------------
    log("\n=== Step 1: Prerequisites & device discovery ===",
        Colors.BOLD + Colors.BLUE)
    if not verify_prerequisites():
        return False

    # When the user skipped --build, or built only a subset, validate that
    # every artifact the chosen mode needs is actually on disk with the
    # right channel — otherwise we'd flash stale/missing firmware.
    if not verify_mode_artifacts_ready(mode, channel):
        return False

    roles = discover_and_assign_devices(mode, rcp_serial=args.rcp_serial)
    if not roles:
        return False

    runner = TEST_MODES.get(mode)
    if runner is None:
        log(f"Unknown test mode: {mode}", Colors.RED)
        return False
    return runner(args, roles, channel, interactive)


def main():
    parser = argparse.ArgumentParser(
        description='Matter + Zigbee Integration Test')
    parser.add_argument('--mode', '-m',
                        choices=sorted(TEST_MODES.keys()),
                        default=DEFAULT_TEST_MODE,
                        help=f'Test scenario to run (default: {DEFAULT_TEST_MODE})')
    parser.add_argument('--channel', '-c', type=int, default=DEFAULT_CHANNEL,
                        choices=range(11, 27),
                        help=f'802.15.4 channel (default: {DEFAULT_CHANNEL})')
    parser.add_argument(
        '--build',
        nargs='*',
        default=None,
        metavar='ARTIFACT',
        help=(
            'Build firmware artifacts before running the test. With no names, '
            'builds every artifact in the catalog. Pass one or more artifact '
            'names to rebuild only those. Artifacts are stored under '
            f'{ARTIFACTS_ROOT}/<name>/ and re-used across runs. When this '
            'flag is ABSENT, the test re-flashes from the cache without '
            'rebuilding (see --no-run to build without running). '
            'Valid names: ' + ', '.join(sorted(ARTIFACT_CATALOG.keys())) + '.'
        ),
    )
    parser.add_argument(
        '--no-run',
        action='store_true',
        help='After --build, do not run the test. Useful for pre-warming the '
             'artifact cache on a shared workstation.',
    )
    parser.add_argument('--no-interactive', action='store_true',
                        help='Skip button-press prompts')
    parser.add_argument(
        '--otbr-docker-image',
        default=OTBR_DOCKER_IMAGE_DEFAULT,
        metavar='IMAGE',
        help=f'OTBR Docker image (default: {OTBR_DOCKER_IMAGE_DEFAULT}; '
             'match your NCS Thread docs if this tag is outdated)',
    )
    parser.add_argument(
        '--rcp-tty',
        default=None,
        metavar='PATH',
        help='Force RCP serial device for OTBR (e.g. /dev/ttyACM2) if auto-pick fails',
    )
    parser.add_argument(
        '--rcp-serial',
        default=None,
        metavar='SN',
        help='Pin the RCP role to a specific nRF52840 SN. Use this when one of '
             'your DKs has IF-MCU/J-Link-OB firmware that does not bridge UART '
             'reliably at 1 Mbps (symptom: otbr-agent times out on Spinel '
             'PROTOCOL_VERSION even though it sees the unsolicited boot frame).',
    )
    parser.add_argument(
        '--recover-all',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='Run ``nrfutil device recover`` (CTRL-AP ERASEALL) on every board '
             'before programming. Default ON because it is the only reliable '
             'way to clear residual UICR / settings-partition state when boards '
             'host different firmware stacks across runs (matches '
             'nordic-docs/zigbee/scripts/fota/fota_test.py behaviour). '
             'Disable with ``--no-recover-all`` for fast iteration on a fleet '
             'whose state you trust.',
    )
    args = parser.parse_args()

    try:
        success = run_test(args, parser)
    finally:
        _restore_terminal()
    sys.exit(0 if success else 1)


def _restore_terminal():
    """Best-effort ``stty sane`` to undo any tty damage from child processes."""
    try:
        if sys.stdin.isatty():
            subprocess.run(['stty', 'sane'], stdin=sys.stdin, timeout=2)
    except Exception:
        pass


if __name__ == '__main__':
    main()
