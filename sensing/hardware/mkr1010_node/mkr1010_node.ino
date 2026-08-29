/*
 * mkr1010_node.ino — IEQ-Ops hardware sensor node
 *
 * Arduino MKR WiFi 1010 reads SCD-30 (CO2 / temperature / humidity over I2C)
 * plus two Grove analog sensors (light + sound, relative values) and publishes
 * one JSON reading every PUBLISH_INTERVAL_MS to the Raspberry Pi's MQTT broker.
 *
 * Payload contract — the JSON keys are the bridge to the rest of the system.
 * The Pi-side ingest maps this onto sensing/history.py::SENSOR_COLUMNS
 * (co2, temperature, humidity, lux, noise_db). light_raw/sound_raw are raw 0..1023
 * ADC counts on purpose: calibration to pseudo lux / dB lives on the Pi so it can
 * be re-tuned without re-flashing this board.
 *   {"co2":812.3,"temperature":22.61,"humidity":44.1,"light_raw":540,"sound_raw":120}
 *
 * Libraries (Arduino IDE → Library Manager):
 *   - WiFiNINA                         (Arduino)
 *   - ArduinoMqttClient                (Arduino)
 *   - SparkFun SCD30 Arduino Library   (SparkFun)
 * Board: Tools → Board → Arduino SAMD Boards → Arduino MKR WiFi 1010
 *
 * 3.3 V WARNING: the SAMD21 analog pins are NOT 5 V tolerant. Power the Grove
 * sensors from the board's 3.3 V (VCC) rail only — at 5 V their analog output can
 * swing above 3.3 V and damage the input. The MKR Connector Carrier already runs
 * Grove at 3.3 V, so it is safe by default.
 */

#include <WiFiNINA.h>
#include <ArduinoMqttClient.h>
#include <Wire.h>
#include <SparkFun_SCD30_Arduino_Library.h>
#include "arduino_secrets.h"

// ---- pins / config (set PIN_LIGHT/PIN_SOUND to whichever analog pins you wired) ----
static const int           PIN_LIGHT            = A0;     // Grove Light Sensor v1.1
static const int           PIN_SOUND            = A1;     // Grove Sound Sensor v1.6
static const char*         MQTT_TOPIC           = "ieq/readings";
static const int           MQTT_PORT            = 1883;
static const unsigned long PUBLISH_INTERVAL_MS  = 5000;   // one reading every 5 s
static const unsigned long SOUND_WINDOW_MS      = 50;     // sound peak-detect window

WiFiClient wifiClient;
MqttClient mqttClient(wifiClient);
SCD30      airSensor;

float         lastCo2 = 0, lastTemp = 0, lastHum = 0;  // cache last good SCD30 sample
unsigned long lastPublish = 0;

void connectWiFi() {
  Serial.print("WiFi: connecting to ");
  Serial.println(SECRET_SSID);
  while (WiFi.begin(SECRET_SSID, SECRET_PASS) != WL_CONNECTED) {
    Serial.println("WiFi: retry in 3s...");
    delay(3000);
  }
  Serial.print("WiFi: connected, IP = ");
  Serial.println(WiFi.localIP());
}

void connectBroker() {
  Serial.print("MQTT: connecting to ");
  Serial.print(SECRET_BROKER);
  Serial.print(":");
  Serial.println(MQTT_PORT);
  mqttClient.setId("mkr1010-node");
  while (!mqttClient.connect(SECRET_BROKER, MQTT_PORT)) {
    Serial.print("MQTT: failed (err ");
    Serial.print(mqttClient.connectError());
    Serial.println("), retry in 3s...");
    delay(3000);
  }
  Serial.println("MQTT: connected");
}

int readLight() {
  long sum = 0;
  for (int i = 0; i < 8; i++) { sum += analogRead(PIN_LIGHT); delay(2); }
  return (int)(sum / 8);
}

int readSoundPeak() {
  unsigned long start = millis();
  int peak = 0;
  while (millis() - start < SOUND_WINDOW_MS) {
    int v = analogRead(PIN_SOUND);
    if (v > peak) peak = v;
  }
  return peak;
}

void setup() {
  Serial.begin(115200);
  delay(1500);                  // brief grace for the Serial Monitor — never block forever (runs headless)
  pinMode(LED_BUILTIN, OUTPUT);
  analogReadResolution(10);     // 0..1023, matches the Pi-side raw→unit mapping

  Wire.begin();
  if (!airSensor.begin()) {
    Serial.println("SCD30: not found — check I2C wiring (SDA=11, SCL=12, VCC=3.3V). Halting.");
    while (true) { digitalWrite(LED_BUILTIN, HIGH); delay(200); digitalWrite(LED_BUILTIN, LOW); delay(200); }
  }
  airSensor.setMeasurementInterval(2);   // seconds
  Serial.println("SCD30: ready");

  connectWiFi();
  connectBroker();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqttClient.connected())       connectBroker();
  mqttClient.poll();                 // MQTT keepalive

  // refresh the cached SCD30 values whenever a fresh sample is ready (~every 2 s)
  if (airSensor.dataAvailable()) {
    lastCo2  = airSensor.getCO2();
    lastTemp = airSensor.getTemperature();
    lastHum  = airSensor.getHumidity();
  }

  if (millis() - lastPublish < PUBLISH_INTERVAL_MS) return;
  lastPublish = millis();

  int light = readLight();
  int sound = readSoundPeak();

  char co2Str[12], tStr[12], hStr[12];
  dtostrf(lastCo2,  0, 1, co2Str);
  dtostrf(lastTemp, 0, 2, tStr);
  dtostrf(lastHum,  0, 1, hStr);

  char payload[160];
  snprintf(payload, sizeof(payload),
    "{\"co2\":%s,\"temperature\":%s,\"humidity\":%s,\"light_raw\":%d,\"sound_raw\":%d}",
    co2Str, tStr, hStr, light, sound);

  mqttClient.beginMessage(MQTT_TOPIC);
  mqttClient.print(payload);
  mqttClient.endMessage();

  digitalWrite(LED_BUILTIN, HIGH); delay(20); digitalWrite(LED_BUILTIN, LOW);  // blink = published
  Serial.print("published ");
  Serial.print(MQTT_TOPIC);
  Serial.print("  ");
  Serial.println(payload);
}
