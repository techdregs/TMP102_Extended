# TMP102 Extended ESPHome Component

ESPHome external component for the TMP102 I2C temperature sensor. Based on the original ESPHome TMP102 component... just extended. It publishes the measured temperature and exposes TMP102 features that the stock basic driver usually does not: extended temperature format, one-shot sampling, conversion-rate control, thermostat/alert configuration, alert polarity, fault queue, and optional alert binary sensor.

Datasheet references in this repo:

- `Datasheets/TMP102_TI.pdf`
- `Datasheets/TMP102_UMW.pdf`

## Hardware

TMP102 is an I2C/SMBus temperature sensor with 0.0625 degC register resolution.

Typical wiring:

- `V+`: 1.4 V to 3.6 V.
- `GND`: ground.
- `SDA`, `SCL`: I2C bus, with pullup resistors.
- `ALERT`: optional open-drain alert output, with pullup resistor if used.
- `ADD0`: address select.

Supported I2C addresses:

| Address | ADD0 wiring |
| --- | --- |
| `0x48` | GND |
| `0x49` | V+ |
| `0x4A` | SDA |
| `0x4B` | SCL |

The component validates the address and rejects values outside this list.

## Basic Use

Place this repository where ESPHome can load it as an external component, then enable it in YAML:

```yaml
external_components:
  - source:
      type: local
      path: /config/esphome/components
    components: [tmp102_extended]

i2c:
  sda: GPIO21
  scl: GPIO22
  scan: true

sensor:
  - platform: tmp102_extended
    name: "TMP102 Temperature"
    address: 0x48
    update_interval: 60s
```

Adjust the `external_components` path to the directory that contains the `tmp102_extended` folder.

For a Git source, use ESPHome's `type: git` source. This repo keeps the component folder at the repo root, so set `path: .` unless your fork moves it under `components/` or `esphome/components/`.

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/USER/TMP102.git
      ref: main
      path: .
    components: [tmp102_extended]
```

## Configuration

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Temperature"
    address: 0x48
    update_interval: 60s
    extended_mode: false
    conversion_rate: 4Hz
    one_shot_mode: false
    alert_polarity: active_low
    thermostat_mode: comparator
    fault_queue: 1
    temperature_high: 80
    temperature_low: 75
    alert:
      name: "TMP102 Alert"
```

### Options

| Option | Default | Values | Description |
| --- | --- | --- | --- |
| `name` | required | string | ESPHome sensor name. |
| `address` | `0x48` | `0x48`, `0x49`, `0x4A`, `0x4B` | TMP102 I2C address. Must match `ADD0` wiring. |
| `update_interval` | `60s` | ESPHome duration | How often ESPHome reads the sensor. |
| `extended_mode` | `false` | boolean | Uses TMP102 13-bit extended temperature/register format. Allows high-side values above 127.9375 degC, up to 150 degC. |
| `conversion_rate` | `4Hz` | `0.25Hz`, `1Hz`, `4Hz`, `8Hz` | TMP102 internal conversion rate in continuous mode. |
| `one_shot_mode` | `false` | boolean | Enables shutdown/one-shot operation. Each ESPHome update triggers one conversion, waits 40 ms, then reads temperature. |
| `alert_polarity` | `active_low` | `active_low`, `active_high` | Sets ALERT output polarity and binary-sensor interpretation. |
| `thermostat_mode` | `comparator` | `comparator`, `interrupt` | Selects TMP102 alert behavior. |
| `fault_queue` | `1` | `1`, `2`, `4`, `6` | Consecutive out-of-limit conversions required before alert activates. Helps reject noise. |
| `temperature_high` | chip default `80 C` if omitted | temperature | High alert threshold, written to `THIGH`. |
| `temperature_low` | chip default `75 C` if omitted | temperature | Low alert threshold, written to `TLOW`. |
| `alert` | omitted | binary sensor config | Optional binary sensor published from the TMP102 AL bit. |

Temperature sensor metadata:

- Unit: `C`
- Device class: temperature
- State class: measurement
- Default displayed precision: 1 decimal

## Temperature Range

The component uses TMP102 register limits:

- Normal mode (`extended_mode: false`): `-55 C` to `127.9375 C`.
- Extended mode (`extended_mode: true`): `-55 C` to `150 C`.

Threshold validation uses the selected mode. `temperature_low` must be less than or equal to `temperature_high`.

If only one threshold is configured, the other TMP102 power-up default remains active. The component prevents invalid mixed configurations:

- If only `temperature_high` is set, it must be at least `75 C` because default `TLOW` is `75 C`.
- If only `temperature_low` is set, it must be no more than `80 C` because default `THIGH` is `80 C`.

## Continuous Mode

Default mode. TMP102 keeps converting internally. On each ESPHome update, the component selects the temperature register, waits 50 ms, reads two bytes, converts the signed 12-bit or 13-bit value, then publishes temperature. The 50 ms wait is a conservative bus/read guard; it is not starting a new conversion in continuous mode.

Use `conversion_rate` to control the sensor's internal conversion cadence:

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Slow Temperature"
    address: 0x48
    update_interval: 30s
    conversion_rate: 0.25Hz
```

Use higher rates when faster alert response matters:

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Fast Temperature"
    address: 0x48
    update_interval: 1s
    conversion_rate: 8Hz
```

## One-Shot Mode

One-shot mode configures TMP102 shutdown mode and triggers one conversion per ESPHome update. This lowers idle sensor current when frequent continuous sampling is not needed. After the 40 ms conversion wait, the component re-selects the temperature register before reading because the trigger write leaves the pointer register on the configuration register.

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Battery Temperature"
    address: 0x48
    update_interval: 5min
    one_shot_mode: true
```

In one-shot mode, `update_interval` controls how often a conversion occurs. `conversion_rate` is still written to the chip configuration register, but continuous conversion is disabled.

## Extended Mode

Enable extended mode for measurements or alert thresholds above the normal 12-bit range.

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 High Range"
    address: 0x48
    extended_mode: true
    temperature_high: 140
    temperature_low: 120
```

Normal mode can represent up to `127.9375 C`. Extended mode uses the TMP102 13-bit format and allows up to `150 C`.

## Alert Output

TMP102 compares measured temperature against `temperature_high` and `temperature_low`. The result can drive the physical `ALERT` pin and, if configured, an ESPHome binary sensor.

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Temperature"
    address: 0x48
    temperature_high: 30
    temperature_low: 28
    alert:
      name: "TMP102 Over Temperature"
```

When `alert` is configured, check the boot log. The component warns if one or both thresholds are omitted because the TMP102 power-up defaults will be used. It also warns when `thermostat_mode: interrupt` is combined with an alert binary sensor because register reads can clear the physical ALERT pin before ESPHome publishes the binary-sensor state.

### Comparator Mode

Default. ALERT activates after temperature is at or above `temperature_high` for the configured `fault_queue` count. ALERT remains active until temperature falls below `temperature_low` for the same fault count.

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Thermostat"
    address: 0x48
    thermostat_mode: comparator
    fault_queue: 4
    temperature_high: 32
    temperature_low: 29
    alert:
      name: "TMP102 Comparator Alert"
```

### Interrupt Mode

Interrupt mode makes the hardware ALERT pin latch on threshold crossings and clear on register reads. The component reads temperature first and then reads the configuration register for the AL bit. Because TMP102 register reads clear the physical ALERT pin in interrupt mode, the ESPHome `alert` binary sensor reflects the AL/comparator status, not necessarily the physical pin level after the read.

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Interrupt Alert"
    address: 0x48
    thermostat_mode: interrupt
    temperature_high: 35
    temperature_low: 25
    alert:
      name: "TMP102 Interrupt State"
```

### Alert Polarity

Default `active_low` matches TMP102 power-up behavior. Use `active_high` when your circuit expects an active-high alert signal.

```yaml
sensor:
  - platform: tmp102_extended
    name: "TMP102 Active High Alert"
    address: 0x48
    alert_polarity: active_high
    temperature_high: 40
    temperature_low: 35
    alert:
      name: "TMP102 Alert"
```

## Multiple Sensors

Up to four TMP102 devices can share one I2C bus when `ADD0` is wired differently on each device.

```yaml
i2c:
  sda: GPIO21
  scl: GPIO22

sensor:
  - platform: tmp102_extended
    name: "TMP102 Board"
    address: 0x48

  - platform: tmp102_extended
    name: "TMP102 Enclosure"
    address: 0x49

  - platform: tmp102_extended
    name: "TMP102 Regulator"
    address: 0x4A
    temperature_high: 70
    temperature_low: 60
    alert:
      name: "Regulator Temperature Alert"
```

## Full Example

```yaml
esphome:
  name: tmp102-demo

esp32:
  board: esp32dev

external_components:
  - source:
      type: local
      path: /config/esphome/components
    components: [tmp102_extended]

i2c:
  sda: GPIO21
  scl: GPIO22
  scan: true

sensor:
  - platform: tmp102_extended
    name: "TMP102 Temperature"
    address: 0x48
    update_interval: 10s
    extended_mode: false
    conversion_rate: 4Hz
    one_shot_mode: false
    thermostat_mode: comparator
    alert_polarity: active_low
    fault_queue: 2
    temperature_high: 30
    temperature_low: 28
    alert:
      name: "TMP102 Alert"
```

## Notes

- ESPHome polling controls publish frequency. TMP102 `conversion_rate` controls internal sensor conversion frequency in continuous mode.
- TMP102 threshold registers use the same format as the temperature register.
- The component writes configured thresholds during setup only.
- If no thresholds are configured, TMP102 chip defaults remain active: `THIGH=80 C`, `TLOW=75 C`.
- The component marks setup failed on I2C write failure and sets a warning on read/update failure.
