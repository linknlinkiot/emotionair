"""ZHA quirk for the LinknLink eMotion Air multi-sensor / smart button.

Install into your Home Assistant config under:
    <config>/zha_quirks/emotion_air.py

and make sure configuration.yaml contains:
    zha:
      custom_quirks_path: /config/zha_quirks/

Then restart HA and re-interview (or re-pair) the device.

Firmware >= V1.2.7 emits a cluster-specific BUTTON_ACTION command on the
proprietary 0xFC00 cluster instead of OnOff/LevelControl or Analog/Multistate
attribute reports.

Payload:
    [0]    uint8            action_id  1=single 2=double 3=triple 4=hold
    [1..]  CharacterString  action_str "single"/"double"/"triple"/"hold"

This quirk provides BOTH:
  1) zha_event with command = single/double/triple/hold
  2) a visible sensor entity (last_action) showing the same text

There is no "release" event, and "hold" fires once the button has been held
for 2 s (it does not wait for the release edge).
"""

from __future__ import annotations

import zigpy.types as t
from zhaquirks import CustomCluster
from zhaquirks.const import (
    BUTTON,
    COMMAND,
    DEVICE_TYPE,
    DOUBLE_PRESS,
    ENDPOINTS,
    INPUT_CLUSTERS,
    LONG_PRESS,
    MODELS_INFO,
    OUTPUT_CLUSTERS,
    PROFILE_ID,
    SHORT_PRESS,
    TRIPLE_PRESS,
    ZHA_SEND_EVENT,
)
from zigpy.profiles import zha
from zigpy.quirks import CustomDevice
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import (
    Basic,
    Identify,
    Ota,
    PollControl,
    PowerConfiguration,
)
from zigpy.zcl.clusters.measurement import (
    IlluminanceMeasurement,
    OccupancySensing,
    RelativeHumidity,
    TemperatureMeasurement,
)
from zigpy.zcl.foundation import BaseAttributeDefs, ZCLAttributeDef

BUTTON_ACTION_CLUSTER_ID = 0xFC00
WWAH_CLUSTER_ID = 0xFC57

ACTION_SINGLE = "single"
ACTION_DOUBLE = "double"
ACTION_TRIPLE = "triple"
ACTION_HOLD = "hold"

ACTION_BY_ID = {
    1: ACTION_SINGLE,
    2: ACTION_DOUBLE,
    3: ACTION_TRIPLE,
    4: ACTION_HOLD,
}


class ButtonActionCluster(CustomCluster):
    """Proprietary LinknLink button action cluster (0xFC00)."""

    cluster_id = BUTTON_ACTION_CLUSTER_ID
    name = "LinknLink Button Action"
    ep_attribute = "button_action"

    # Local quirk-only attribute used to expose a readable HA sensor entity.
    # The device itself does not report this attribute over the air.
    ATTR_LAST_ACTION = 0x0000

    class AttributeDefs(BaseAttributeDefs):
        last_action = ZCLAttributeDef(
            id=0x0000,
            type=t.CharacterString,
            access="r",
            is_manufacturer_specific=True,
        )
        cluster_revision = foundation.ZCL_CLUSTER_REVISION_ATTR

    # Device -> coordinator command (server_to_client) is modeled as client_commands
    # on the zigpy server-cluster representation.
    client_commands = {
        0x00: foundation.ZCLCommandDef(
            name="button_action",
            schema={"action_id": t.uint8_t, "action_str": t.CharacterString},
            direction=foundation.Direction.Server_to_Client,
            is_manufacturer_specific=False,
        )
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_cache[self.ATTR_LAST_ACTION] = ""

    def handle_cluster_request(self, hdr, args, *, dst_addressing=None):
        """Emit zha_event and update the last_action sensor entity."""
        if hdr.command_id != 0x00:
            return

        action_id = int(args[0]) if args else 0
        action_str = args[1] if len(args) > 1 else None
        if isinstance(action_str, (bytes, bytearray)):
            action_str = bytes(action_str).decode("utf-8", errors="ignore")

        action = ACTION_BY_ID.get(action_id) or (str(action_str) if action_str else None)
        if not action:
            return

        self._update_attribute(self.ATTR_LAST_ACTION, action)
        self.listener_event(
            ZHA_SEND_EVENT,
            action,
            {
                "action_id": action_id,
                "action": action,
            },
        )


class EmotionAir(CustomDevice):
    """LinknLink eMotion Air."""

    signature = {
        MODELS_INFO: [("LinknLink", "eMotion Air")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,                 # 0x0000
                    PollControl.cluster_id,           # 0x0020
                    TemperatureMeasurement.cluster_id,# 0x0402
                    RelativeHumidity.cluster_id,      # 0x0405
                    IlluminanceMeasurement.cluster_id,# 0x0400
                    OccupancySensing.cluster_id,      # 0x0406
                    PowerConfiguration.cluster_id,    # 0x0001
                    WWAH_CLUSTER_ID,                  # 0xFC57
                    BUTTON_ACTION_CLUSTER_ID,         # 0xFC00
                ],
                OUTPUT_CLUSTERS: [
                    Ota.cluster_id,                   # 0x0019
                    0x1000,                           # Touchlink Commissioning
                ],
            }
        },
    }

    replacement = {
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    Identify.cluster_id,
                    PollControl.cluster_id,
                    TemperatureMeasurement.cluster_id,
                    RelativeHumidity.cluster_id,
                    IlluminanceMeasurement.cluster_id,
                    OccupancySensing.cluster_id,
                    PowerConfiguration.cluster_id,
                    WWAH_CLUSTER_ID,
                    ButtonActionCluster,
                ],
                OUTPUT_CLUSTERS: [
                    Ota.cluster_id,
                    0x1000,
                ],
            }
        }
    }

    device_automation_triggers = {
        (SHORT_PRESS, BUTTON): {COMMAND: ACTION_SINGLE},
        (DOUBLE_PRESS, BUTTON): {COMMAND: ACTION_DOUBLE},
        (TRIPLE_PRESS, BUTTON): {COMMAND: ACTION_TRIPLE},
        (LONG_PRESS, BUTTON): {COMMAND: ACTION_HOLD},
    }
