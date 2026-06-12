# FSM Alarm Clock — SYSEN 5412 Final Project

An FSM-based smart alarm clock built on the Raspberry Pi Pico (MicroPython).

- **Project website**: [coming soon via GitHub Pages]
- **Demo video**: [YouTube Short](https://youtube.com/shorts/g99llM1LRGQ)

## Hardware

- LCD1602 via I2C (SDA=GP4, SCL=GP5)
- IR Remote receiver NEC_8 (GP13)
- RFID MFRC522 via SPI0 (SCK=18, MOSI=19, MISO=16, CS=17, RST=9)
- HC-SR04 Ultrasonic sensor — gesture stop (TRIG=GP11, ECHO=GP12)
- WS2812 LED strip (GP0)
- Buzzer PWM (GP15)
- Snooze button (GP14)

## Running

Flash `final_project_v3.py` to a Raspberry Pi Pico running MicroPython, along with the required libraries (`lcd1602`, `ir_rx`, `mfrc522`, `ws2812`).
