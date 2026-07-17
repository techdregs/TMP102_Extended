"""
The TMP102 is a two-wire, serial output temperature
sensor available in a tiny SOT563 package. Requiring
no external components, the TMP102 is capable of
reading temperatures to a resolution of 0.0625°C.

This component is based on the basic ESPHome TMP102 component.

"""

import esphome.codegen as cg
from esphome.components import binary_sensor, i2c, number, sensor, text_sensor
import esphome.config_validation as cv
from esphome.const import (
    CONF_ADDRESS,
    CONF_ID,
    CONF_INITIAL_VALUE,
    CONF_RESTORE_VALUE,
    DEVICE_CLASS_TEMPERATURE,
    STATE_CLASS_MEASUREMENT,
    UNIT_CELSIUS,
)

DEPENDENCIES = ["i2c"]
AUTO_LOAD = ["binary_sensor", "number", "text_sensor"]

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
TMP102LimitNumber = tmp102_extended_ns.class_(
    "TMP102LimitNumber", number.Number, cg.Component
)

TMP102ConversionRate = tmp102_extended_ns.enum("TMP102ConversionRate")
TMP102ThermostatMode = tmp102_extended_ns.enum("TMP102ThermostatMode")
TMP102AlertPolarity = tmp102_extended_ns.enum("TMP102AlertPolarity")
TMP102LimitType = tmp102_extended_ns.enum("TMP102LimitType")

CONF_EXTENDED_MODE = "extended_mode"
CONF_CONVERSION_RATE = "conversion_rate"
CONF_ONE_SHOT_MODE = "one_shot_mode"
CONF_ALERT_SENSOR = "alert"
CONF_THRESHOLD_STATUS = "threshold_status"
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

LIMIT_TYPES = {
    CONF_TEMPERATURE_LOW: TMP102LimitType.TMP102_LIMIT_LOW,
    CONF_TEMPERATURE_HIGH: TMP102LimitType.TMP102_LIMIT_HIGH,
}

# Chip power-up defaults used when the user omits one or both limit registers.
_TMP102_DEFAULT_THIGH = 80.0
_TMP102_DEFAULT_TLOW = 75.0


def _validate_temperature_range(key, value, extended):
    t_min = -55.0
    t_max = 150.0 if extended else 127.9375
    mode_str = "extended" if extended else "normal"
    if not (t_min <= value <= t_max):
        raise cv.Invalid(
            f"{key} ({value}°C) out of range for {mode_str} mode "
            f"({t_min}°C to {t_max}°C)",
            [key],
        )


def _is_limit_number_config(value):
    return isinstance(value, dict)


def _limit_initial(config, key, default_value):
    value = config.get(key)
    if value is None:
        return None
    if _is_limit_number_config(value):
        return value.get(CONF_INITIAL_VALUE, default_value)
    return value


def _is_limit_number(config, key):
    return key in config and _is_limit_number_config(config[key])


def validate_tmp102_thresholds(config):
    extended = config.get(CONF_EXTENDED_MODE, False)
    # Normal mode: datasheet format table covers -55°C to +127.9375°C (12-bit signed, 0.0625°C/LSB).
    # Extended mode: datasheet spec is -55°C to +150°C.
    for key in (CONF_TEMPERATURE_HIGH, CONF_TEMPERATURE_LOW):
        if key not in config:
            continue
        value = config[key]
        if _is_limit_number_config(value):
            if CONF_INITIAL_VALUE in value:
                _validate_temperature_range(key, value[CONF_INITIAL_VALUE], extended)
        else:
            _validate_temperature_range(key, value, extended)

    high_initial = _limit_initial(config, CONF_TEMPERATURE_HIGH, _TMP102_DEFAULT_THIGH)
    low_initial = _limit_initial(config, CONF_TEMPERATURE_LOW, _TMP102_DEFAULT_TLOW)

    if high_initial is not None and low_initial is not None and low_initial > high_initial:
        raise cv.Invalid(
            f"initial low limit ({low_initial}°C) must be <= initial high limit ({high_initial}°C)",
            [CONF_TEMPERATURE_LOW],
        )
    if high_initial is not None and low_initial is None and high_initial < _TMP102_DEFAULT_TLOW:
        raise cv.Invalid(
            f"initial high limit ({high_initial}°C) is below the chip power-up "
            f"TLOW default ({_TMP102_DEFAULT_TLOW}°C). Set temperature_low explicitly.",
            [CONF_TEMPERATURE_HIGH],
        )
    if low_initial is not None and high_initial is None and low_initial > _TMP102_DEFAULT_THIGH:
        raise cv.Invalid(
            f"initial low limit ({low_initial}°C) is above the chip power-up "
            f"THIGH default ({_TMP102_DEFAULT_THIGH}°C). Set temperature_high explicitly.",
            [CONF_TEMPERATURE_LOW],
        )

    return config


def limit_number_schema():
    return number.number_schema(
        TMP102LimitNumber,
        unit_of_measurement=UNIT_CELSIUS,
        device_class=DEVICE_CLASS_TEMPERATURE,
    ).extend(
        {
            cv.Optional(CONF_INITIAL_VALUE): cv.temperature,
            cv.Optional(CONF_RESTORE_VALUE, default=True): cv.boolean,
        }
    ).extend(cv.COMPONENT_SCHEMA)


def limit_schema():
    return cv.Any(cv.temperature, limit_number_schema())


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
            cv.Optional(CONF_TEMPERATURE_HIGH): limit_schema(),
            cv.Optional(CONF_TEMPERATURE_LOW): limit_schema(),
            cv.Optional(CONF_ALERT_SENSOR): binary_sensor.binary_sensor_schema(),
            cv.Optional(CONF_THRESHOLD_STATUS): text_sensor.text_sensor_schema(),
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

    if CONF_THRESHOLD_STATUS in config:
        status = await text_sensor.new_text_sensor(config[CONF_THRESHOLD_STATUS])
        cg.add(var.set_threshold_status_text_sensor(status))

    high_initial = _limit_initial(config, CONF_TEMPERATURE_HIGH, _TMP102_DEFAULT_THIGH)
    low_initial = _limit_initial(config, CONF_TEMPERATURE_LOW, _TMP102_DEFAULT_TLOW)

    if high_initial is not None:
        cg.add(var.set_temperature_high(high_initial))

    if low_initial is not None:
        cg.add(var.set_temperature_low(low_initial))

    for key, setter in (
        (CONF_TEMPERATURE_HIGH, var.set_high_limit_control),
        (CONF_TEMPERATURE_LOW, var.set_low_limit_control),
    ):
        if not _is_limit_number(config, key):
            continue
        limit_config = config[key]
        limit_number = cg.new_Pvariable(limit_config[CONF_ID])
        await cg.register_component(limit_number, limit_config)
        await number.register_number(
            limit_number,
            limit_config,
            min_value=-55.0,
            max_value=150.0 if config[CONF_EXTENDED_MODE] else 127.9375,
            step=0.0625,
        )
        initial = _limit_initial(
            config,
            key,
            _TMP102_DEFAULT_THIGH if key == CONF_TEMPERATURE_HIGH else _TMP102_DEFAULT_TLOW,
        )
        cg.add(limit_number.set_parent(var))
        cg.add(limit_number.set_limit_type(LIMIT_TYPES[key]))
        cg.add(limit_number.set_initial_value(initial))
        cg.add(limit_number.set_restore_value(limit_config[CONF_RESTORE_VALUE]))
        cg.add(setter(limit_number))
