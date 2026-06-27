"""
The TMP102 is a two-wire, serial output temperature
sensor available in a tiny SOT563 package. Requiring
no external components, the TMP102 is capable of
reading temperatures to a resolution of 0.0625°C.

This component is based on the basic ESPHome TMP102 component.

"""

import esphome.codegen as cg
from esphome.components import binary_sensor, i2c, sensor
import esphome.config_validation as cv
from esphome.const import (
    CONF_ADDRESS,
    DEVICE_CLASS_TEMPERATURE,
    STATE_CLASS_MEASUREMENT,
    UNIT_CELSIUS,
)

DEPENDENCIES = ["i2c"]
AUTO_LOAD = ["binary_sensor"]

TMP102_I2C_ADDRESSES = [0x48, 0x49, 0x4A, 0x4B]


def validate_tmp102_address(value):
    value = cv.i2c_address(value)
    if value not in TMP102_I2C_ADDRESSES:
        raise cv.Invalid(
            "Invalid TMP102 address. Valid addresses by ADD0 wiring: "
            "0x48 (ADD0→GND), 0x49 (ADD0→V+), 0x4A (ADD0→SDA), 0x4B (ADD0→SCL)"
        )
    return value

tmp102_extended_ns = cg.esphome_ns.namespace("tmp102_extended")
TMP102Component = tmp102_extended_ns.class_(
    "TMP102Component", cg.PollingComponent, i2c.I2CDevice, sensor.Sensor
)

TMP102ConversionRate = tmp102_extended_ns.enum("TMP102ConversionRate")
TMP102ThermostatMode = tmp102_extended_ns.enum("TMP102ThermostatMode")
TMP102AlertPolarity = tmp102_extended_ns.enum("TMP102AlertPolarity")

CONF_EXTENDED_MODE = "extended_mode"
CONF_CONVERSION_RATE = "conversion_rate"
CONF_ONE_SHOT_MODE = "one_shot_mode"
CONF_ALERT_SENSOR = "alert"
CONF_TEMPERATURE_HIGH = "temperature_high"
CONF_TEMPERATURE_LOW = "temperature_low"
CONF_ALERT_POLARITY = "alert_polarity"
CONF_THERMOSTAT_MODE = "thermostat_mode"
CONF_FAULT_QUEUE = "fault_queue"

CONVERSION_RATES = {
    "0.25Hz": TMP102ConversionRate.TMP102_CONVERSION_RATE_0_25HZ,
    "1Hz": TMP102ConversionRate.TMP102_CONVERSION_RATE_1HZ,
    "4Hz": TMP102ConversionRate.TMP102_CONVERSION_RATE_4HZ,
    "8Hz": TMP102ConversionRate.TMP102_CONVERSION_RATE_8HZ,
}

THERMOSTAT_MODES = {
    "comparator": TMP102ThermostatMode.TMP102_THERMOSTAT_MODE_COMPARATOR,
    "interrupt": TMP102ThermostatMode.TMP102_THERMOSTAT_MODE_INTERRUPT,
}

ALERT_POLARITIES = {
    "active_low": TMP102AlertPolarity.TMP102_ALERT_POLARITY_ACTIVE_LOW,
    "active_high": TMP102AlertPolarity.TMP102_ALERT_POLARITY_ACTIVE_HIGH,
}

# Chip power-up defaults used when the user omits one or both limit registers.
_TMP102_DEFAULT_THIGH = 80.0
_TMP102_DEFAULT_TLOW = 75.0


def validate_tmp102_thresholds(config):
    extended = config.get(CONF_EXTENDED_MODE, False)
    # Normal mode: datasheet format table covers -55°C to +127.9375°C (12-bit signed, 0.0625°C/LSB).
    # Extended mode: datasheet spec is -55°C to +150°C.
    t_min = -55.0
    t_max = 150.0 if extended else 127.9375
    mode_str = "extended" if extended else "normal"

    for key in (CONF_TEMPERATURE_HIGH, CONF_TEMPERATURE_LOW):
        if key in config:
            val = config[key]
            if not (t_min <= val <= t_max):
                raise cv.Invalid(
                    f"{key} ({val}°C) out of range for {mode_str} mode "
                    f"({t_min}°C to {t_max}°C)",
                    [key],
                )

    has_high = CONF_TEMPERATURE_HIGH in config
    has_low = CONF_TEMPERATURE_LOW in config

    if has_high and has_low:
        if config[CONF_TEMPERATURE_LOW] > config[CONF_TEMPERATURE_HIGH]:
            raise cv.Invalid(
                f"temperature_low ({config[CONF_TEMPERATURE_LOW]}°C) must be "
                f"<= temperature_high ({config[CONF_TEMPERATURE_HIGH]}°C)",
                [CONF_TEMPERATURE_LOW],
            )
    elif has_high and not has_low:
        # TLOW will remain at chip default; check THIGH is not below it.
        if config[CONF_TEMPERATURE_HIGH] < _TMP102_DEFAULT_TLOW:
            raise cv.Invalid(
                f"temperature_high ({config[CONF_TEMPERATURE_HIGH]}°C) is below the chip "
                f"power-up TLOW default ({_TMP102_DEFAULT_TLOW}°C). Set temperature_low "
                f"explicitly to avoid THIGH < TLOW.",
                [CONF_TEMPERATURE_HIGH],
            )
    elif has_low and not has_high:
        # THIGH will remain at chip default; check TLOW is not above it.
        if config[CONF_TEMPERATURE_LOW] > _TMP102_DEFAULT_THIGH:
            raise cv.Invalid(
                f"temperature_low ({config[CONF_TEMPERATURE_LOW]}°C) is above the chip "
                f"power-up THIGH default ({_TMP102_DEFAULT_THIGH}°C). Set temperature_high "
                f"explicitly to avoid TLOW > THIGH.",
                [CONF_TEMPERATURE_LOW],
            )

    return config


CONFIG_SCHEMA = cv.All(
    sensor.sensor_schema(
        TMP102Component,
        unit_of_measurement=UNIT_CELSIUS,
        accuracy_decimals=1,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
    )
    .extend(cv.polling_component_schema("60s"))
    .extend(i2c.i2c_device_schema(0x48))
    .extend(
        {
            cv.Optional(CONF_ADDRESS, default=0x48): validate_tmp102_address,
            cv.Optional(CONF_EXTENDED_MODE, default=False): cv.boolean,
            cv.Optional(CONF_CONVERSION_RATE, default="4Hz"): cv.enum(
                CONVERSION_RATES, upper=False
            ),
            cv.Optional(CONF_ONE_SHOT_MODE, default=False): cv.boolean,
            cv.Optional(CONF_ALERT_POLARITY, default="active_low"): cv.enum(
                ALERT_POLARITIES, upper=False
            ),
            cv.Optional(CONF_THERMOSTAT_MODE, default="comparator"): cv.enum(
                THERMOSTAT_MODES, upper=False
            ),
            cv.Optional(CONF_FAULT_QUEUE, default=1): cv.one_of(1, 2, 4, 6, int=True),
            cv.Optional(CONF_TEMPERATURE_HIGH): cv.temperature,
            cv.Optional(CONF_TEMPERATURE_LOW): cv.temperature,
            cv.Optional(CONF_ALERT_SENSOR): binary_sensor.binary_sensor_schema(),
        }
    ),
    validate_tmp102_thresholds,
)


async def to_code(config):
    var = await sensor.new_sensor(config)
    await cg.register_component(var, config)
    await i2c.register_i2c_device(var, config)

    cg.add(var.set_extended_mode(config[CONF_EXTENDED_MODE]))
    cg.add(var.set_conversion_rate(config[CONF_CONVERSION_RATE]))
    cg.add(var.set_one_shot_mode(config[CONF_ONE_SHOT_MODE]))
    cg.add(var.set_alert_polarity(config[CONF_ALERT_POLARITY]))
    cg.add(var.set_thermostat_mode(config[CONF_THERMOSTAT_MODE]))
    cg.add(var.set_fault_queue(config[CONF_FAULT_QUEUE]))

    if CONF_ALERT_SENSOR in config:
        alert = await binary_sensor.new_binary_sensor(config[CONF_ALERT_SENSOR])
        cg.add(var.set_alert_binary_sensor(alert))

    if CONF_TEMPERATURE_HIGH in config:
        cg.add(var.set_temperature_high(config[CONF_TEMPERATURE_HIGH]))

    if CONF_TEMPERATURE_LOW in config:
        cg.add(var.set_temperature_low(config[CONF_TEMPERATURE_LOW]))
