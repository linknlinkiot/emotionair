# eMotion Air — Home Assistant (ZHA)

ZHA quirk and an optional automation blueprint for the **LinknLink eMotion Air**
(Zigbee multi-sensor + smart button).

Requires firmware **V1.2.7 or newer**.

## What you get after installing the quirk

1. `zha_event` with textual commands: `single` / `double` / `triple` / `hold`
2. Native **Device Triggers** in the automation UI (no YAML needed)
3. A visible sensor entity **Last action** showing the same text

The blueprint is **optional** — most users only need the quirk.

## Requirements

| Item | Value |
| --- | --- |
| Firmware | V1.2.7+ (`FILE_VERSION 0x10273001`) |
| Integration | ZHA (not Zigbee2MQTT) |
| Manufacturer / Model | `LinknLink` / `eMotion Air` |

## Install the quirk

1. Create the quirks folder in your Home Assistant config directory:

   ```
   /config/zha_quirks/
   ```

   For a Docker install this is the host path you mapped to `/config`,
   e.g. `/root/homeassistant/zha_quirks/`.

2. Copy `emotion_air_quirk.py` into it, renaming it to `emotion_air.py`:

   ```
   /config/zha_quirks/emotion_air.py
   ```

3. Add this to `configuration.yaml`:

   ```yaml
   zha:
     custom_quirks_path: /config/zha_quirks/
   ```

4. **Restart Home Assistant.** The folder must exist before HA starts, and
   quirks are only loaded at startup.

5. **Remove the device from ZHA and pair it again.**

> [!IMPORTANT]
> A plain *Reconfigure* is **not** enough. zigpy caches the cluster schema from
> the original interview, so the new cluster only takes effect after a full
> re-pair.

## Cluster map (V1.2.7+)

| Cluster | Purpose |
| --- | --- |
| `0xFC01` | Button Action — text commands (`single`/`double`/`triple`/`hold`) |
| `0xFC00` | Air config (radar / illuminance / temp-humi parameters) |
| `0xFC57` | WWAH |

Button Action wire format — cluster `0xFC01`, command `0x00`, server to client,
manufacturer code `0x4231`:

```
[0]    uint8            action_id   1=single 2=double 3=triple 4=hold
[1..]  CharacterString  action_str  "single" / "double" / "triple" / "hold"
```

e.g. `01 06 73 69 6E 67 6C 65` = `single`

Notes:

- There is no *release* event.
- `hold` fires once the button has been held for **2 s**; releasing it afterwards
  does not emit anything further.

## Verify

### Device trigger (easiest)

Settings → Automations → Create automation → Add trigger → Device → pick the
eMotion Air. You should see *"single press"*, *"double press"*, *"triple press"*
and *"long press"*.

### Raw event

Developer Tools → Events → listen to `zha_event`, then press the button:

```yaml
event_type: zha_event
data:
  device_id: <your device id>
  command: single
  args:
    action_id: 1
    action: single
```

### Entity

The device page shows a **Last action** sensor holding the most recent
`single` / `double` / `triple` / `hold` value.

## Optional blueprint

`blueprint_eMotionAir_v2.yaml` wires the four actions up for you.

1. Copy it to `/config/blueprints/automation/linknlink/`
2. Settings → Automations & Scenes → Blueprints → reload
3. Create an automation from *LinknLink eMotion Air Smart Button Controller (v2)*

It triggers on the same `zha_event` commands, so the quirk still has to be
installed first.

## Troubleshooting

**No `zha_event` at all** — the quirk did not apply. Enable debug logging:

```yaml
logger:
  logs:
    zigpy: debug
    zhaquirks: debug
```

A working setup logs a line similar to:

```
[0x____:1:0xfc01] Decoded ZCL frame: ButtonActionCluster:button_action(action_id=1, action_str='single')
```

**`Fail because output cluster mismatch on at least one endpoint`** — the v1
signature did not match. This is harmless; the v2 quirk matches on
manufacturer/model only and still applies.

**No "Last action" entity** — re-pair the device. The entity is created during
the interview.

**Still nothing** — confirm the firmware really is V1.2.7+ by checking the
device's `Basic` cluster `sw_build_id`.
