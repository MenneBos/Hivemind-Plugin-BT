#include "BluetoothSerial.h"
#include <FastLED.h>
#include "driver/i2s_pdm.h" // to set up the PDM mic
#include "driver/i2s_std.h" // to disable and del the i2s_channel
#include "esp_sleep.h"

// ---------- BT SPP ----------
BluetoothSerial SerialBT;
uint8_t ERASMUS_SERVER[6] = {0x58, 0x02, 0x05, 0xBD, 0xDD, 0xC0};
uint8_t ZeroSleep_SERVER[6] = {0xB8, 0x27, 0xEB, 0x09, 0x4B, 0x88}; // B8:27:EB:09:4B:88

struct BtServer {
  const char* name;
  uint8_t mac[6];
};

BtServer servers[] = {
  {"Erasmus",  {0x58, 0x02, 0x05, 0xBD, 0xDD, 0xC0}},
  {"ZeroSleep",{0xB8, 0x27, 0xEB, 0x09, 0x4B, 0x88}}
};

const int NUM_SERVERS = sizeof(servers) / sizeof(servers[0]);

int rssiValues[NUM_SERVERS];
int bestServerIndex = -1;

// Selected MAC (the one with highest RSSI)
//uint8_t selectedMAC[6];

// Track RSSI during inquiry
//int rssiErasmus   = -999;
//int rssiZeroSleep = -999;

// ---------- Pins / LED ----------
#define BUTTON_PIN 39   // Atom knop zit meestal op GPIO39
#define LED_PIN    27     // WS2812 data pin
#define NUM_LEDS   1      // aantal leds (Atom Lite = 1, Atom Matrix = 25)
#define CLK_PIN    33
#define DIN_PIN    23
CRGB leds[NUM_LEDS];
#define SLEEP_TIMEOUT 10000      // ms
#define DEEP_SLEEP_DELAY   120000    // 60s = auto overgang naar deep sleep

// ---------- States ----------
bool isConnected = false;
bool isRecording = false;
bool isAwake = true;

unsigned long releasedTime = 0;

// ---------- I2S ----------
i2s_chan_handle_t rx_handle;
#define SAMPLE_RATE 16000
#define BUFFER_SIZE 2048
int16_t audio_buffer[BUFFER_SIZE];

bool readButton() {
    return digitalRead(BUTTON_PIN) == LOW;
}

// -------- enter deep sleep ----------------
void enterDeepSleep() {
    Serial.println("🌑 Entering DEEP SLEEP...");
   
    // Stop Bluetooth
    SerialBT.end();

    // Stop i2s mic
    ESP_ERROR_CHECK(i2s_del_channel(rx_handle));

    // Hold button pin during deep sleep
    gpio_hold_en((gpio_num_t)BUTTON_PIN);

    // led down
    leds[0] = CRGB::Black;
    FastLED.show();

    esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
    esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
    //esp_sleep_enable_ext1_wakeup(1ULL << BUTTON_PIN, ESP_EXT1_WAKEUP_ANY_LOW);

    delay(50);

    esp_deep_sleep_start(); //next command is first command in setup()
}

// -------- enter light sleep ----------------
void enterLightSleep() {
    Serial.println("⚫ Entering light sleep...");

    FastLED.clear();  FastLED.show();
    delay(100);

    // Wake on button LOW (ext0)
    esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);

    // Also wake on timer → to switch to deep sleep later
    esp_sleep_enable_timer_wakeup(DEEP_SLEEP_DELAY * 1000ULL);

    esp_light_sleep_start();


    // --- Code continues after waking ---
    esp_sleep_wakeup_cause_t reason = esp_sleep_get_wakeup_cause();

    if (reason == ESP_SLEEP_WAKEUP_TIMER) {
        Serial.println("⏰ Timer expired → entering DEEP SLEEP");
        leds[0] = CRGB::Red; FastLED.show();
        delay(500);
        enterDeepSleep(); // will never return and wakes in setup()
    } 

    if (reason == ESP_SLEEP_WAKEUP_EXT0) {
        Serial.println("🔵 Woke from LIGHT SLEEP by button");
        leds[0] = CRGB::Blue; FastLED.show();
    }

    /*delay(200);   // let the pin settle
    while (readButton()) {
        Serial.println("Button still pressed after wake-up, waiting...");
        delay(20);
    }*/

    isAwake = true;
    releasedTime = millis();

}


void setup_i2s() {
  // RX (microfoon) kanaal maken
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));

  // Clock config: sets sample rate and decimation internally
  i2s_pdm_rx_clk_config_t clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(SAMPLE_RATE);

  // Slot config: PCM format (hardware PDM→PCM filter enabled)
  i2s_pdm_rx_slot_config_t slot_cfg =
    I2S_PDM_RX_SLOT_PCM_FMT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO);
  
  // GPIO config: Atom Echo mic pins
  i2s_pdm_rx_gpio_config_t gpio_cfg = {
    .clk = GPIO_NUM_33,   // Mic clock/WS (per M5Unified mapping)
    .din = GPIO_NUM_23,   // Mic data
    .invert_flags = { .clk_inv = false }
  };

  // Combine configs
  i2s_pdm_rx_config_t pdm_rx_cfg = {
    .clk_cfg = clk_cfg,
    .slot_cfg = slot_cfg,
    .gpio_cfg = gpio_cfg
  };

  ESP_ERROR_CHECK(i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_rx_cfg));

  Serial.println("Atom Echo SPM1423 mic initialized (PDM mode).");
}

int getServerRSSI(uint8_t* mac) {
  if (!SerialBT.connect(mac, 2)) {
    Serial.println("Kon niet verbinden met server");
    return -999; // foutwaarde
  }
  delay(1000); // even wachten op data

  String msg = SerialBT.readStringUntil('\n'); // verwacht "RSSI:-45"
  SerialBT.disconnect();

  if (msg.startsWith("RSSI:")) {
    return msg.substring(5).toInt();
  }
  return -999;
}

void setup() {
  leds[0] = CRGB::Orange; FastLED.show();
  size_t bytes_read = 0;
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);  // knop met interne pull-up
  
  // Led init
  FastLED.addLeds<NEOPIXEL, LED_PIN>(leds, NUM_LEDS);

  gpio_hold_dis((gpio_num_t)BUTTON_PIN); // release the pin 

  // bluetooth init
  if (!SerialBT.begin("AtomClient", true)) {
    Serial.println("Bluetooth init mislukt!");
    while (1) delay(1000);
  }
  Serial.println("Bluetooth gestart in CLIENT mode.");

  // Meet RSSI van alle servers
  for (int i = 0; i < NUM_SERVERS; i++) {
    rssiValues[i] = getServerRSSI(servers[i].mac);
    Serial.printf("Server %s (%s) RSSI=%d\n", servers[i].name, servers[i].mac, rssiValues[i]);
  }

  // Selecteer server met hoogste RSSI
  bestServerIndex = 0;
  for (int i = 1; i < NUM_SERVERS; i++) {
    if (rssiValues[i] > rssiValues[bestServerIndex]) {
      bestServerIndex = i;
    }
  }

  Serial.printf("Sterkste server: %s RSSI=%d\n", servers[bestServerIndex].name, rssiValues[bestServerIndex]);

  setup_i2s();
  
  isAwake = true;
  releasedTime = millis();

    //FastLED.clear();  
  leds[0] = CRGB::Yellow; FastLED.show();

}

void loop() {

  size_t bytes_read = 0;
  bool buttonPressed = (digitalRead(BUTTON_PIN) == LOW);

  if (buttonPressed && !isConnected && isAwake) {
    Serial.println("Knop ingedrukt, verbinden...");

    if (SerialBT.connect(servers[bestServerIndex].mac, 2)) {
      Serial.printf(">>> Verbonden met Linux server %s", servers[bestServerIndex].name);

      // 1. Lees RSSI bericht van server
      String msg = SerialBT.readStringUntil('\n');  // verwacht "RSSI:-45"
      int currentRSSI = -999;
      if (msg.startsWith("RSSI:")) {
        currentRSSI = msg.substring(5).toInt();
        Serial.printf("Actuele RSSI van gekozen server %c: %d\n", servers[bestServerIndex].name, currentRSSI);
      }

      // 2. Vergelijk met oude waarden van andere servers
      bool strongerFound = false;
      for (int i = 0; i < NUM_SERVERS; i++) {
        if (i == bestServerIndex) continue; // sla gekozen server over
        if (rssiValues[i] > currentRSSI) {
          strongerFound = true;
          Serial.printf("Server %s heeft sterker signaal (%d)\n", servers[i].name, rssiValues[i]);
        }
      }

      // 3. Beslissen wat te doen
      if (strongerFound) {
        leds[0] = CRGB::Red; FastLED.show();
        Serial.println(">>> Verbinding geweigerd, andere server sterker!");
        SerialBT.disconnect();
        isConnected = false;
      } else {
        leds[0] = CRGB::Green; FastLED.show();
        Serial.println(">>> RSSI OK, audio starten...");
        isConnected = true;
        ESP_ERROR_CHECK(i2s_channel_enable(rx_handle));
        // hier start je met audio data versturen
      }

    } else {
      leds[0] = CRGB::Red; FastLED.show();
      Serial.println(">>> BT verbinding mislukt.");
    }
  }

  // Bij loslaten: stoppen met opnemen, BT disconnect, buffer afspelen
  if (!buttonPressed && isConnected) {
    Serial.println("Knop losgelaten, verbreken...");
    ESP_ERROR_CHECK(i2s_channel_disable(rx_handle));
    SerialBT.disconnect();
    isConnected = false;
    leds[0] = CRGB::Blue; FastLED.show();
    isRecording = false;
    releasedTime = millis();
  }

  // start opnemen en versturen
  if (buttonPressed && isConnected) {
    esp_err_t err = i2s_channel_read(rx_handle, audio_buffer, sizeof(audio_buffer), &bytes_read, 1000);
    if (err == ESP_OK && bytes_read > 0) {
      SerialBT.write((uint8_t*)audio_buffer, bytes_read);
      Serial.printf("Sent %u over Bluetooth\n", audio_buffer[2]);
    } else {
      Serial.printf("I2S read error: %d\n", (int)err);
    }
  }

  if (!buttonPressed && !isConnected && isAwake) {
      if (millis() - releasedTime >= SLEEP_TIMEOUT) {
          isAwake = false;
          enterLightSleep();
      }
  }

  // Data uitwisseling alleen als verbonden
  if (isConnected) {
    if (Serial.available()) {
      char c = Serial.read();
      SerialBT.write(c);
    }
    if (SerialBT.available()) {
      char c = SerialBT.read();
      Serial.write(c);
    }
  }
  delay(10);
}
