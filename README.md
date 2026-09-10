# eMotion Air Home Assistant Integration

## What you get after installing the quirk

1. `zha_event` with textual commands:
   - `single`
   - `double`
   - `triple`
   - `hold`
2. A visible sensor entity for the last button action (`last_action`)

Blueprint is **optional**. Most users only need the quirk.

## Install quirk

1. Copy `emotion_air_quirk.py` to Home Assistant:
   - `/config/zha_quirks/emotion_air.py`
2. Add to `configuration.yaml`:

```yaml
zha:
  custom_quirks_path: /config/zha_quirks/
```

3. Restart Home Assistant
4. Re-interview (or re-pair) the eMotion Air device
5. Confirm firmware is **V1.2.7+** (0xFC00 Button Action)

## Verify

### Event
Developer Tools → Events → listen to `zha_event`

Expected:
```yaml
command: single   # or double / triple / hold
args:
  action_id: 1
  action: single
```

### Entity
Device page should show a sensor/attribute like **last_action** / button action text.

## Optional blueprint

`blueprint_eMotionAir_v2.yaml` can still be used as a helper automation template.
With the quirk installed, native Device Triggers / Event triggers are usually enough.
