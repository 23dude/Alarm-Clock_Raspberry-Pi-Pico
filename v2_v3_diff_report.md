# v2 vs v3 Comparison

## Scope
English summary of differences between final_project_v2.py and final_project_v3.py, the obstacles observed, and the fixes applied. Snippets reference actual code sections.

## Core Differences
- Button input: v2 used polling with PULL_DOWN and a software debouncer; v3 uses PULL_UP with an IRQ_FALLING ISR plus 50 ms debounce and pin recheck in the main loop.
- Alarm output architecture: v2 directly toggled hardware (read current duty_u16, invert); v3 maintains state flags (alarm_led_on, alarm_buzzer_on) and a separate update_alarm_outputs() function that reflects flags to hardware.
- Alarm cadence: v2 layered a software tick-diff (500 ms) on top of the 1 Hz hardware timer; v3 removes the extra layer and toggles outputs on every hardware timer tick.
- Confirmation blink: v2 ran a 0.2 s blocking loop; v3 adds a CONFIRMATION sub-state driven by the 1 Hz timer with a 3-blink counter.
- UI messaging: v2 relied on lcd.clear() + time.sleep(); v3 introduces a non-blocking temp message window that expires on timer ticks, plus 16-char padding to overwrite residue without repeated clears.
- Power-off: v3 adds an IR POWER event that deinitializes timers, silences outputs, and exits the loop.

## Obstacles and Resolutions
- False snooze triggers (likely EMI): PULL_DOWN input floated near buzzer/LED wires, so PWM spikes could look like presses. Resolution: switch to PULL_UP, interrupt-driven detection, longer debounce, and main-loop pin verification.
- Rhythm drift / missed beeps: dual timing layers (timer + ticks_diff) caused missed toggles when the main loop lagged. Resolution: single timing source (hardware timer) drives flag toggles; hardware just reflects flags.
- Flickering/overwritten messages: blocking sleeps and repeated clears caused residue. Resolution: queued temp messages with expiry time, padded 16-char writes to cover the line, and minimized lcd.clear() calls.
- No graceful exit: v2 required Ctrl+C; v3 handles IR POWER to stop timers, mute buzzer, blank LEDs, and show "End Program".

## Key Code Snippets

### Button Path (Polling vs Interrupt)
**v2 (polling, PULL_DOWN)**
```python
button = Pin(14, Pin.IN, Pin.PULL_DOWN)
button_debounce_ms = 10

def check_button_press():
    if mode != ALARM_ACTIVE:
        return False
    current_read = button.value()
    now = time.ticks_ms()
    if button_first_read_time_ms == 0:
        button_first_read = current_read
        button_first_read_time_ms = now
        return False
    if time.ticks_diff(now, button_first_read_time_ms) >= button_debounce_ms:
        if current_read == button_first_read and current_read == 1:
            if time.ticks_diff(now, last_button_press_ms) > 300:
                last_button_press_ms = now
                return True
    return False
```

**v3 (interrupt, PULL_UP)**
```python
button = Pin(14, Pin.IN, Pin.PULL_UP)
button_debounce_ms = 50
button_pending = False

# ISR
button.irq(trigger=Pin.IRQ_FALLING, handler=button_isr)

def button_isr(pin):
    if mode == ALARM_ACTIVE:
        button_pending = True

# Main loop verification
if button_pending:
    button_pending = False
    now = time.ticks_ms()
    if time.ticks_diff(now, last_button_press_ms) > button_debounce_ms:
        if button.value() == 0:  # active-low
            last_button_press_ms = now
            mode_handle_event(EV_SNOOZE_PRESS)
```

### Alarm Output Architecture
**v2 (direct hardware toggle)**
```python
def toggle_alarm_outputs():
    global active_alarm_led
    color = led_strip[active_alarm_led]
    new = [0, 0, 0] if color != [0, 0, 0] else [255, 0, 0]
    led_strip[active_alarm_led] = new
    led_strip.write()
    if buzzer.duty_u16() > 0:
        buzzer.duty_u16(0)
    else:
        buzzer.duty_u16(30000)
```

**v3 (state flags + hardware layer)**
```python
# State flags
alarm_led_on = False
alarm_buzzer_on = False

def update_alarm_outputs():
    """Hardware layer reflects flag state"""
    if alarm_led_on:
        set_alarm_led(active_alarm_led, 255, 0, 0)
    else:
        set_alarm_led(active_alarm_led, 0, 0, 0)
    if alarm_buzzer_on:
        buzzer.duty_u16(30000)
    else:
        buzzer.duty_u16(0)
```

### Alarm Cadence (Dual vs Single Timing Layer)
**v2 (dual layer)**
```python
last_blink_ms = time.ticks_ms()
blink_period_ms = 500

if event == EV_TIMER_TICK:
    now = time.ticks_ms()
    if time.ticks_diff(now, last_blink_ms) >= blink_period_ms:
        last_blink_ms = now
        toggle_alarm_outputs()
```

**v3 (single hardware timer)**
```python
if event == EV_TIMER_TICK:
    alarm_led_on = not alarm_led_on
    alarm_buzzer_on = not alarm_buzzer_on
    update_alarm_outputs()  # reflect flags only
```

### Confirmation Blink
**v2 (blocking loop)**
```python
def blink_led_confirmation():
    for _ in range(3):
        set_alarm_led(active_alarm_led, 255, 255, 255)
        time.sleep(0.2)
        clear_alarm_led(active_alarm_led)
        time.sleep(0.2)
```

**v3 (timer-driven sub-state)**
```python
confirmation_blink_count = 0
if alarm_mode == CONFIRMATION and event == EV_TIMER_TICK:
    if confirmation_blink_count >= CONFIRMATION_TOTAL_BLINKS:
        set_alarm_led(active_alarm_led, 0, 255, 0)  # green
        return True
    color = led_strip[active_alarm_led]
    if color == [0, 0, 0]:
        set_alarm_led(active_alarm_led, 255, 255, 255)
    else:
        set_alarm_led(active_alarm_led, 0, 0, 0)
        confirmation_blink_count += 1
```

### UI Messaging (Blocking vs Non-blocking)
**v2 (blocking + no padding)**
```python
def lcd_show_time_set_success():
    lcd.clear()
    lcd.write(0, 0, "Time Updated")
    time.sleep(1)

def update_time_display():
    lcd.write(0, 0, "Current Time:")  # No padding
    lcd.write(0, 1, "{:02d}:{:02d}:{:02d} {}".format(h12, m, s, period))
```

**v3 (non-blocking + padded writes)**
```python
def show_temp_message(msg, duration_ms=1000):
    ui_message = msg
    ui_message_until_ms = time.ticks_add(time.ticks_ms(), duration_ms)
    lcd.clear()
    lcd.write(0, 0, msg)

# In EV_TIMER_TICK handler
if ui_message is not None:
    if time.ticks_diff(now, ui_message_until_ms) < 0:
        lcd.clear(); lcd.write(0, 0, ui_message); return
    ui_message = None; render_screen()

# Padded writes to avoid residue
def update_time_display():
    lcd.write(0, 0, "Current Time:   ")  # Pad to 16 chars
    lcd.write(0, 1, "{:02d}:{:02d}:{:02d} {}    ".format(h12, m, s, period))
```

## Synchronous Operations (Retained in v3)
While v3 eliminates application-level blocking (removed all `time.sleep(1)` calls), necessary hardware-level synchronous operations remain:

**Hardware Communication (inherent to protocols):**
- I2C LCD: `lcd.write()`, `lcd.clear()` - synchronous bus transactions
- SPI RFID: `rfid_read_no_block()` - despite the name, SPI communication is synchronous
- WS2812 LED: `led_strip.write()` - bit-banged protocol requires precise timing

**Microsecond-level delays (negligible impact):**
```python
def measure_distance_cm():
    utime.sleep_us(2)   # Trigger setup
    utime.sleep_us(10)  # Pulse width
```

**Main loop throttle:**
```python
time.sleep_ms(5)  # Prevent CPU spinning
```

**Why these are acceptable:**
- Hardware protocols (I2C/SPI) inherently synchronous by design
- Microsecond delays don't affect responsiveness (< 0.01 ms)
- 5 ms loop sleep balances CPU usage without blocking events
- No long-duration (≥100 ms) blocking in application logic

**Key improvement v2→v3:** Eliminated seconds-long blocking (`time.sleep(1)`) that froze UI and delayed event handling.

## Residual Assumptions
- EMI as root cause for false presses is inferred from behavior near PWM/LED wiring; not instrumented with scope in this codebase (推測).
- Hardware timer is assumed stable at 1 Hz for cadence; main loop may still sleep 5 ms per iteration but no longer gates output timing.

## Files Referenced
- final_project_v2.py
- final_project_v3.py
