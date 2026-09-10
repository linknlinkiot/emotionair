"""ZHA quirk for the LinknLink eMotion Air multi-sensor / smart button.

Install into your Home Assistant config under:
    <config>/zha_quirks/emotion_air.py

and make sure configuration.yaml contains:
    zha:
      custom_quirks_path: /config/zha_quirks/

Then restart HA and re-interview (or re-pair) the device.

Firmware >= V1.2.7 emits a cluster-specific BUTTON_ACTION command on the
proprietary 0xFC01 cluster instead of OnOff/LevelControl or Analog/Multistate
attribute reports.

Wire payload of cluster 0xFC01, command 0x00 (server -> client):
    [0]    uint8            action_id  1=single 2=double 3=triple 4=hold
    [1..]  CharacterString  action_str "single"/"double"/"triple"/"hold"

e.g. b"\x01\x06single"

This quirk provides BOTH:
  1) zha_event with command = single/double/triple/hold
  2) a visible sensor entity (last_action) showing the same text

There is no "release" event, and "hold" fires once the button has been held
for 2 s (it does not wait for the release edge).
"""

from __future__ import annotations

import logging

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

_LOGGER = logging.getLogger(__name__)

BUTTON_ACTION_CLUSTER_ID = 0xFC01
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


class ButtonAction(t.enum8):
    """Button action values exposed by the last_action sensor entity."""

    single = 1
    double = 2
    triple = 3
    hold = 4


ACTION_ENUM_BY_ID = {
    1: ButtonAction.single,
    2: ButtonAction.double,
    3: ButtonAction.triple,
    4: ButtonAction.hold,
}


class ButtonActionCluster(CustomCluster):
    """Proprietary LinknLink button action cluster (0xFC01)."""

    cluster_id = BUTTON_ACTION_CLUSTER_ID
    name = "LinknLink Button Action"
    ep_attribute = "linknlink_button_action"

    ATTR_LAST_ACTION = 0x0000

    class AttributeDefs(BaseAttributeDefs):
        """Quirk-local attribute, used to expose a readable HA sensor entity."""

        last_action = ZCLAttributeDef(
            id=0x0000,
            type=ButtonAction,
            access="rp",
            is_manufacturer_specific=True,
        )
        cluster_revision = foundation.ZCL_CLUSTER_REVISION_ATTR

    # The device sends this as a server -> client cluster command, so on the
    # server cluster representation it belongs in client_commands.
    class ClientCommandDefs(foundation.BaseCommandDefs):
        button_action = foundation.ZCLCommandDef(
            id=0x00,
            schema={"action_id": t.uint8_t, "action_str": t.CharacterString},
            direction=foundation.Direction.Server_to_Client,
            is_manufacturer_specific=True,
        )

    def _emit(self, action: str, action_id: int) -> None:
        _LOGGER.debug("eMotion Air button action: %s (id=%s)", action, action_id)
        enum_value = ACTION_ENUM_BY_ID.get(action_id)
        if enum_value is not None:
            self._update_attribute(self.ATTR_LAST_ACTION, enum_value)
        self.listener_event(
            ZHA_SEND_EVENT,
            action,
            {"action_id": action_id, "action": action},
        )

    def handle_cluster_request(self, hdr, args, *, dst_addressing=None):
        """Handle the decoded BUTTON_ACTION command."""
        if hdr.command_id != 0x00:
            return

        action_id = 0
        action_str = None
        try:
            action_id = int(args[0])
            if len(args) > 1:
                action_str = args[1]
        except (IndexError, TypeError, ValueError):
            # fall back to attribute style access
            action_id = int(getattr(args, "action_id", 0) or 0)
            action_str = getattr(args, "action_str", None)

        if isinstance(action_str, (bytes, bytearray)):
            action_str = bytes(action_str).decode("utf-8", errors="ignore")

        action = ACTION_BY_ID.get(action_id) or (
            str(action_str) if action_str else None
        )
        if not action:
            return

        self._emit(action, action_id)

    def handle_message(self, hdr, args, *, dst_addressing=None):
        """Fallback for firmwares/stacks where the schema fails to decode."""
        try:
            super().handle_message(hdr, args, dst_addressing=dst_addressing)
        except TypeError:
            super().handle_message(hdr, args)


class EmotionAir(CustomDevice):
    """LinknLink eMotion Air."""

    signature = {
        MODELS_INFO: [("LinknLink", "eMotion Air")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,                   # 0x0000
                    PollControl.cluster_id,             # 0x0020
                    TemperatureMeasurement.cluster_id,  # 0x0402
                    RelativeHumidity.cluster_id,        # 0x0405
                    IlluminanceMeasurement.cluster_id,  # 0x0400
                    OccupancySensing.cluster_id,        # 0x0406
                    PowerConfiguration.cluster_id,      # 0x0001
                    WWAH_CLUSTER_ID,                    # 0xFC57
                    BUTTON_ACTION_CLUSTER_ID,           # 0xFC01 button action
                ],
                OUTPUT_CLUSTERS: [
                    Ota.cluster_id,                     # 0x0019
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


class EmotionAirWithTouchlink(EmotionAir):
    """Same device, but firmware that also advertises Touchlink (0x1000) out."""

    signature = {
        MODELS_INFO: [("LinknLink", "eMotion Air")],
        ENDPOINTS: {
            1: {
                PROFILE_ID: zha.PROFILE_ID,
                DEVICE_TYPE: zha.DeviceType.TEMPERATURE_SENSOR,
                INPUT_CLUSTERS: [
                    Basic.cluster_id,
                    PollControl.cluster_id,
                    TemperatureMeasurement.cluster_id,
                    RelativeHumidity.cluster_id,
                    IlluminanceMeasurement.cluster_id,
                    OccupancySensing.cluster_id,
                    PowerConfiguration.cluster_id,
                    WWAH_CLUSTER_ID,
                    BUTTON_ACTION_CLUSTER_ID,
                ],
                OUTPUT_CLUSTERS: [
                    Ota.cluster_id,
                    0x1000,  # Touchlink Commissioning
                ],
            }
        },
    }


# ---------------------------------------------------------------------------
# Quirks v2 registration.
#
# The v1 signature above must match the endpoint description exactly, which is
# fragile (a single extra/missing output cluster makes it fail with
# "Fail because output cluster mismatch on at least one endpoint").
#
# The v2 entry below matches on manufacturer/model only, replaces cluster
# 0xFC01 with our custom cluster, and exposes last_action as a sensor entity.
# ---------------------------------------------------------------------------
try:
    from zigpy.quirks.v2 import QuirkBuilder
    from zigpy.quirks.v2.homeassistant import EntityPlatform, EntityType
except ImportError:  # pragma: no cover - older zigpy
    QuirkBuilder = None

if QuirkBuilder is not None:
    _builder = (
        QuirkBuilder("LinknLink", "eMotion Air")
        .replaces(ButtonActionCluster, endpoint_id=1)
        .enum(
            ButtonActionCluster.AttributeDefs.last_action.name,
            ButtonAction,
            ButtonActionCluster.cluster_id,
            endpoint_id=1,
            entity_platform=EntityPlatform.SENSOR,
            entity_type=EntityType.STANDARD,
            translation_key="last_action",
            fallback_name="Last action",
        )
        .device_automation_triggers(
            {
                (SHORT_PRESS, BUTTON): {COMMAND: ACTION_SINGLE},
                (DOUBLE_PRESS, BUTTON): {COMMAND: ACTION_DOUBLE},
                (TRIPLE_PRESS, BUTTON): {COMMAND: ACTION_TRIPLE},
                (LONG_PRESS, BUTTON): {COMMAND: ACTION_HOLD},
            }
        )
    )
    _builder.add_to_registry()
