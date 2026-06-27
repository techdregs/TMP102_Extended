#include "tmp102_extended.h"
#include "esphome/core/log.h"
#include "esphome/core/hal.h"

namespace esphome {
namespace tmp102_extended {

static const char *const TAG = "tmp102_extended";

static const uint8_t TMP102_REGISTER_TEMPERATURE   = 0x00;
static const uint8_t TMP102_REGISTER_CONFIGURATION = 0x01;
static const uint8_t TMP102_REGISTER_LOW_LIMIT     = 0x02;
static const uint8_t TMP102_REGISTER_HIGH_LIMIT    = 0x03;

static const float TMP102_CONVERSION_FACTOR = 0.0625f;

// Configuration register high byte bit positions
static const uint8_t TMP102_CFG_OS_BIT  = 7;  // One-shot trigger
static const uint8_t TMP102_CFG_F0_BIT  = 3;  // Fault queue LSB (F1:F0 at bits 4:3)
static const uint8_t TMP102_CFG_POL_BIT = 2;  // Alert polarity
static const uint8_t TMP102_CFG_TM_BIT  = 1;  // Thermostat mode
static const uint8_t TMP102_CFG_SD_BIT  = 0;  // Shutdown / one-shot enable

// Configuration register low byte bit positions
static const uint8_t TMP102_CFG_CR0_BIT = 6;  // Conversion rate LSB (CR1:CR0 at bits 7:6)
static const uint8_t TMP102_CFG_AL_BIT  = 5;  // Alert status (read-only)
static const uint8_t TMP102_CFG_EM_BIT  = 4;  // Extended mode

static const uint32_t TMP102_ONESHOT_DELAY_MS    = 40;  // datasheet max 35 ms + 5 ms margin
static const uint32_t TMP102_CONTINUOUS_DELAY_MS = 50;

void TMP102Component::setup() {
  ESP_LOGCONFIG(TAG, "Setting up TMP102...");
  if (!this->write_config_register_()) {
    this->mark_failed();
    return;
  }
  if (this->temperature_high_.has_value()) {
    if (!this->write_limit_register_(TMP102_REGISTER_HIGH_LIMIT, *this->temperature_high_)) {
      this->mark_failed();
      return;
    }
  }
  if (this->temperature_low_.has_value()) {
    if (!this->write_limit_register_(TMP102_REGISTER_LOW_LIMIT, *this->temperature_low_)) {
      this->mark_failed();
      return;
    }
  }
}

void TMP102Component::dump_config() {
  ESP_LOGCONFIG(TAG, "TMP102:");
  LOG_I2C_DEVICE(this);
  if (this->is_failed()) {
    ESP_LOGE(TAG, ESP_LOG_MSG_COMM_FAIL);
  }
  LOG_UPDATE_INTERVAL(this);
  LOG_SENSOR("  ", "Temperature", this);
  LOG_BINARY_SENSOR("  ", "Alert", this->alert_sensor_);
  ESP_LOGCONFIG(TAG, "  Extended Mode: %s", this->extended_mode_ ? "YES" : "NO");
  ESP_LOGCONFIG(TAG, "  One-Shot Mode: %s", this->one_shot_mode_ ? "YES" : "NO");
  const char *rate_str =
    this->conversion_rate_ == TMP102_CONVERSION_RATE_0_25HZ ? "0.25Hz" :
    this->conversion_rate_ == TMP102_CONVERSION_RATE_1HZ    ? "1Hz"    :
    this->conversion_rate_ == TMP102_CONVERSION_RATE_4HZ    ? "4Hz"    : "8Hz";
  ESP_LOGCONFIG(TAG, "  Conversion Rate: %s", rate_str);
  ESP_LOGCONFIG(TAG, "  Thermostat Mode: %s",
    this->thermostat_mode_ == TMP102_THERMOSTAT_MODE_COMPARATOR ? "Comparator" : "Interrupt");
  ESP_LOGCONFIG(TAG, "  Alert Polarity: %s",
    this->alert_polarity_ == TMP102_ALERT_POLARITY_ACTIVE_LOW ? "Active Low" : "Active High");
  ESP_LOGCONFIG(TAG, "  Fault Queue: %d", this->fault_queue_);
  if (this->temperature_high_.has_value())
    ESP_LOGCONFIG(TAG, "  Temperature High: %.1f°C", *this->temperature_high_);
  if (this->temperature_low_.has_value())
    ESP_LOGCONFIG(TAG, "  Temperature Low: %.1f°C", *this->temperature_low_);
  if (this->alert_sensor_ != nullptr) {
    if (!this->temperature_high_.has_value() && !this->temperature_low_.has_value()) {
      ESP_LOGW(TAG, "  Alert configured but temperature_high/temperature_low not set; "
                    "chip power-up defaults will be used (THIGH=80°C, TLOW=75°C)");
    } else if (!this->temperature_high_.has_value()) {
      ESP_LOGW(TAG, "  Alert configured but temperature_high not set; "
                    "chip power-up default THIGH=80°C will be used");
    } else if (!this->temperature_low_.has_value()) {
      ESP_LOGW(TAG, "  Alert configured but temperature_low not set; "
                    "chip power-up default TLOW=75°C will be used");
    }
    if (this->thermostat_mode_ == TMP102_THERMOSTAT_MODE_INTERRUPT) {
      // The AL bit always reflects comparator state and is unaffected by TM mode.
      // In interrupt mode the ALERT pin is cleared by any register read (including the
      // temperature read that precedes alert state polling), so the binary sensor may
      // show active while the hardware ALERT pin is already deasserted.
      ESP_LOGW(TAG, "  Alert binary sensor in interrupt mode reflects comparator state, "
                    "not the hardware ALERT pin (which is cleared by register reads)");
    }
  }
}

void TMP102Component::update() {
  if (this->one_shot_mode_) {
    // Trigger a single conversion: write config register with SD=1 and OS=1
    uint8_t frame[3] = {
      TMP102_REGISTER_CONFIGURATION,
      static_cast<uint8_t>(this->config_high_byte_ | (1 << TMP102_CFG_OS_BIT)),
      this->config_low_byte_,
    };
    if (this->write(frame, 3) != i2c::ERROR_OK) {
      this->status_set_warning();
      return;
    }
    // Conversion takes up to 35 ms; wait 40 ms then re-point and read
    this->set_timeout("read_temp", TMP102_ONESHOT_DELAY_MS, [this]() {
      this->read_temperature_();
    });
  } else {
    // Point the pointer register at the temperature register
    if (this->write(&TMP102_REGISTER_TEMPERATURE, 1) != i2c::ERROR_OK) {
      this->status_set_warning();
      return;
    }
    this->set_timeout("read_temp", TMP102_CONTINUOUS_DELAY_MS, [this]() {
      this->read_temperature_();
    });
  }
}

bool TMP102Component::write_config_register_() {
  uint8_t high_byte = 0x00;
  uint8_t low_byte  = 0x00;

  // Fault queue: 1→00, 2→01, 4→10, 6→11 (F1:F0 at bits 4:3)
  uint8_t fq_bits;
  switch (this->fault_queue_) {
    case 2:  fq_bits = 0b01; break;
    case 4:  fq_bits = 0b10; break;
    case 6:  fq_bits = 0b11; break;
    default: fq_bits = 0b00; break;
  }
  high_byte |= static_cast<uint8_t>(fq_bits << TMP102_CFG_F0_BIT);

  if (this->alert_polarity_ == TMP102_ALERT_POLARITY_ACTIVE_HIGH)
    high_byte |= static_cast<uint8_t>(1 << TMP102_CFG_POL_BIT);

  if (this->thermostat_mode_ == TMP102_THERMOSTAT_MODE_INTERRUPT)
    high_byte |= static_cast<uint8_t>(1 << TMP102_CFG_TM_BIT);

  if (this->one_shot_mode_)
    high_byte |= static_cast<uint8_t>(1 << TMP102_CFG_SD_BIT);  // SD=1 for shutdown/one-shot

  // CR1:CR0 at bits 7:6
  low_byte |= static_cast<uint8_t>(static_cast<uint8_t>(this->conversion_rate_) << TMP102_CFG_CR0_BIT);

  if (this->extended_mode_)
    low_byte |= static_cast<uint8_t>(1 << TMP102_CFG_EM_BIT);

  // Cache for use in update() one-shot path
  this->config_high_byte_ = high_byte;
  this->config_low_byte_  = low_byte;

  uint8_t frame[3] = {TMP102_REGISTER_CONFIGURATION, high_byte, low_byte};
  if (this->write(frame, 3) != i2c::ERROR_OK) {
    ESP_LOGE(TAG, ESP_LOG_MSG_COMM_FAIL);
    return false;
  }
  return true;
}

bool TMP102Component::write_limit_register_(uint8_t reg, float temperature) {
  int16_t raw = static_cast<int16_t>(temperature / TMP102_CONVERSION_FACTOR);
  // 13-bit extended mode: value in upper 13 bits (shift left 3)
  // 12-bit normal mode: value in upper 12 bits (shift left 4)
  raw = this->extended_mode_ ? static_cast<int16_t>(raw << 3) : static_cast<int16_t>(raw << 4);
  uint8_t frame[3] = {
    reg,
    static_cast<uint8_t>((raw >> 8) & 0xFF),
    static_cast<uint8_t>(raw & 0xFF),
  };
  if (this->write(frame, 3) != i2c::ERROR_OK) {
    ESP_LOGE(TAG, ESP_LOG_MSG_COMM_FAIL);
    return false;
  }
  return true;
}

void TMP102Component::read_temperature_() {
  // In one-shot mode the pointer register is left at 0x01 (config); re-select temperature register.
  // In continuous mode update() already set the pointer to 0x00 before the timeout.
  if (this->one_shot_mode_) {
    if (this->write(&TMP102_REGISTER_TEMPERATURE, 1) != i2c::ERROR_OK) {
      this->status_set_warning();
      return;
    }
  }

  int16_t raw_temperature;
  if (this->read(reinterpret_cast<uint8_t *>(&raw_temperature), 2) != i2c::ERROR_OK) {
    this->status_set_warning();
    return;
  }
  raw_temperature = i2c::i2ctohs(raw_temperature);
  // Extended mode: 13-bit value in upper 13 bits → right-shift 3
  // Normal mode: 12-bit value in upper 12 bits → right-shift 4
  raw_temperature = this->extended_mode_ ? (raw_temperature >> 3) : (raw_temperature >> 4);
  float temperature = raw_temperature * TMP102_CONVERSION_FACTOR;
  ESP_LOGD(TAG, "Got Temperature=%.2f°C", temperature);
  this->publish_state(temperature);
  this->status_clear_warning();

  if (this->alert_sensor_ != nullptr) {
    this->read_alert_state_();
  }
}

void TMP102Component::read_alert_state_() {
  if (this->write(&TMP102_REGISTER_CONFIGURATION, 1) != i2c::ERROR_OK) {
    ESP_LOGW(TAG, "Failed to select config register for AL bit read");
    return;
  }
  uint8_t cfg[2];
  if (this->read(cfg, 2) != i2c::ERROR_OK) {
    ESP_LOGW(TAG, "Failed to read config register for AL bit");
    return;
  }
  // AL is bit 5 of the low byte (cfg[1]).
  // When POL=0 (active low): chip sets AL=0 when alert is active → alert_active = (AL==0).
  // When POL=1 (active high): chip sets AL=1 when alert is active → alert_active = (AL==1).
  // In both cases: alert_active = (AL_bit == POL_value).
  // Note: in interrupt thermostat mode the preceding temperature register read may already
  // have cleared the AL bit; alert state is most reliable in comparator mode.
  uint8_t al_bit = (cfg[1] >> TMP102_CFG_AL_BIT) & 0x01;
  bool alert_active = (al_bit == static_cast<uint8_t>(this->alert_polarity_));
  ESP_LOGD(TAG, "AL=%d alert_active=%s", al_bit, alert_active ? "YES" : "NO");
  this->alert_sensor_->publish_state(alert_active);
}

}  // namespace tmp102_extended
}  // namespace esphome
