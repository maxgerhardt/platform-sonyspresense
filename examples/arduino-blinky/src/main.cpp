#include <Arduino.h>

#define LED LED_BUILTIN

static int i=0;
void setup(){
    Serial.begin(115200);
    pinMode(LED, OUTPUT);
}

void loop(){
    digitalWrite(LED, LOW);
    delay(500);
    digitalWrite(LED, HIGH);
    delay(500);
    Serial.println("Blinky nr. " + String(i++));
}