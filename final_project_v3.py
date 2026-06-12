"""
FSM-Based Alarm Clock - Final Project V2 (Updated Requirements)
Key changes:
- MODE button enters SET_TIME (not delete menu)
- MUTE button enters delete menu
- Alarms support toggle enabled/disabled
- Snooze duration: 30 seconds
- RFID: simple +13 hour shift (no timezone)
- PLAY/PAUSE confirms all operations

Hardware:
- LCD1602 I2C0 (SDA=GP4, SCL=GP5)
- IR Receiver NEC_8 on GP13
- RFID MFRC522 SPI0 (SCK=18, MOSI=19, MISO=16, CS=17, RST=9)
- Gesture Sensor HC-SR04 (TRIG=GP11, ECHO=GP12)
- WS2812 LED strip on GP0 (index 0=Alarm1, index 1=Alarm2)
- Buzzer PWM GP15
- Snooze button GP14
"""

from machine import Pin, I2C, SPI, PWM, Timer, RTC
import time, utime
from lcd1602 import LCD
from ir_rx.nec import NEC_8
from mfrc522 import SimpleMFRC522
from ws2812 import WS2812

###############################################################################
# ------------------------- Hardware Initialization ---------------------------
###############################################################################

# LCD
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100000)
lcd = LCD(i2c, addr=0x27)
lcd.clear()

# IR Receiver
ir_pin = Pin(13, Pin.IN)
last_ir_value = None

# RFID
reader = SimpleMFRC522(spi_id=0, sck=18, mosi=19, miso=16, cs=17, rst=9)

def rfid_read_no_block():
    """Return (id, text) or (None, None) without blocking."""
    try:
        reader.reader.init()
        stat, tag_type = reader.reader.request(reader.reader.REQIDL)
        if stat != reader.reader.OK:
            return None, None
        stat, uid = reader.reader.SelectTagSN()
        if stat != reader.reader.OK:
            return None, None
        text_read = ""
        id_str = "".join("{:02X}".format(i) for i in uid)
        for block_num in reader.BLOCK_ADDRS:
            status = reader.reader.authKeys(uid, block_num, reader.KEY, None)
            if status != reader.reader.OK:
                return None, None
            status, block = reader.reader.read(block_num)
            if status == reader.reader.ERR:
                return None, None
            for v in block:
                text_read += chr(v)
        return id_str, text_read.strip()
    except:
        return None, None

# Gesture Sensor
TRIG = Pin(11, Pin.OUT)
ECHO = Pin(12, Pin.IN)

def measure_distance_cm():
    """Non-blocking distance measurement with timeout"""
    try:
        TRIG.low()
        utime.sleep_us(2)
        TRIG.high()
        utime.sleep_us(10)
        TRIG.low()
        
        timeout = utime.ticks_us()
        while ECHO.value() == 0:
            if utime.ticks_diff(utime.ticks_us(), timeout) > 30000:
                return 999
        
        start = utime.ticks_us()
        while ECHO.value() == 1:
            if utime.ticks_diff(utime.ticks_us(), start) > 30000:
                return 999
        
        end = utime.ticks_us()
        duration = utime.ticks_diff(end, start)
        return (duration * 0.0343) / 2
    except:
        return 999

gesture_counter = 0

# WS2812 LED strip
led_strip = WS2812(Pin(0), 8)

def set_alarm_led(index, r, g, b):
    led_strip[index] = [r, g, b]
    led_strip.write()

def clear_alarm_led(index):
    led_strip[index] = [0, 0, 0]
    led_strip.write()

# Buzzer
buzzer = PWM(Pin(15))
buzzer.freq(2000)
buzzer.duty_u16(0)

def stop_alarm_output():
    buzzer.duty_u16(0)

def update_alarm_outputs():
    """Update hardware outputs based on state flags"""
    global active_alarm_led, alarm_led_on, alarm_buzzer_on
    
    # Update LED
    if alarm_led_on:
        set_alarm_led(active_alarm_led, 255, 0, 0)
    else:
        set_alarm_led(active_alarm_led, 0, 0, 0)
    
    # Update buzzer
    if alarm_buzzer_on:
        buzzer.duty_u16(30000)
    else:
        buzzer.duty_u16(0)

# Snooze button (interrupt mode with debounce)
button = Pin(14, Pin.IN, Pin.PULL_UP)
button_pending = False
last_button_press_ms = 0
button_debounce_ms = 50  # 50ms debounce

###############################################################################
# ----------------------------- FSM CONSTANTS --------------------------------
###############################################################################

# Top-level States
TIME_DISPLAY = 0
SET_TIME = 1
SET_ALARM_1 = 2
SET_ALARM_2 = 3
ALARM_ACTIVE = 4  # Alarm system is active (Sub-FSM manages details)
DELETE_ALARM_SELECTION = 5
DELETE_CONFIRM = 6

# Sub-FSM states (alarm mode)
ALARM_RINGING = 0
SNOOZE = 1
CONFIRMATION = 2  # LED blink confirmation after stopping alarm

# Sub-FSM states (alarm internal state)
ALARM_ON = 0
ALARM_SNOOZED = 1

# Timeout constants
ALARM_TIMEOUT_MS = 60000  # 60 seconds
SNOOZE_DURATION_MS = 30000  # 30 seconds
CONFIRMATION_BLINK_PERIOD_MS = 1000  # 1 second per toggle (matches timer1 period)
CONFIRMATION_TOTAL_BLINKS = 3  # Blink 3 times

# Events
EV_ENTER_SET_TIME = 10
EV_TIME_INPUT_DIGIT = 11
EV_TIME_SELECT_AM = 12
EV_TIME_SELECT_PM = 13
EV_TIME_CONFIRM = 14
EV_EXIT_SET_TIME = 15

EV_ENTER_SET_ALARM1 = 20
EV_ENTER_SET_ALARM2 = 21
EV_ALARM_CONFIRM = 22
EV_ALARM_CANCEL = 23
EV_ALARM_TOGGLE1 = 24
EV_ALARM_TOGGLE2 = 25

EV_TIMER_TICK = 30
EV_SNOOZE_PRESS = 31

EV_ALARM_MATCH = 40

EV_ENTER_DELETE_MENU = 50
EV_DELETE_SELECT_ALARM1 = 51
EV_DELETE_SELECT_ALARM2 = 52
EV_DELETE_CONFIRM = 53
EV_DELETE_CANCEL = 54

EV_RFID_DETECTED = 60
EV_GESTURE_DETECTED = 70
EV_POWER_OFF = 80

# IR key codes
IR_POWER = 0x45
IR_MODE = 0x46
IR_PLAY_PAUSE = 0x44
IR_MUTE = 0x47
IR_PLUS = 0x09
IR_MINUS = 0x15
IR_1 = 0x0C
IR_2 = 0x18

###############################################################################
# ----------------------------- GLOBAL VARIABLES ------------------------------
###############################################################################

mode = TIME_DISPLAY
alarm_mode = ALARM_RINGING  # Sub-FSM mode
alarm_state = ALARM_ON       # Sub-FSM internal state
time_buffer = ""
ampm_flag = None

# Alarm structure: {"h": 12, "m": 30, "ampm": "AM", "enabled": True}
alarm1 = None
alarm2 = None

active_alarm_led = 0
selected_alarm_for_delete = None
snooze_start_ms = None
alarm_led_on = False  # State flag for alarm LED
alarm_buzzer_on = False  # State flag for alarm buzzer
confirmation_blink_count = 0

# ISR flags
ir_pending = False
timer_pending = False
gesture_pending = False
rfid_pending = False
button_pending = False
last_digit = ""
alarm_start_time_ms = None
last_button_press_ms = 0
alarm_already_triggered = False

# UI message system (non-blocking)
ui_message = None
ui_message_until_ms = 0

# Program control
program_running = True

###############################################################################
# ----------------------------- ISR DEFINITIONS -------------------------------
###############################################################################

def ir_callback(data, addr, ctrl):
    global ir_pending, last_ir_value
    if data >= 0:
        ir_pending = True
        last_ir_value = data

def button_isr(pin):
    global button_pending, mode
    if mode == ALARM_ACTIVE:
        button_pending = True

def timer_isr(t):
    global timer_pending
    timer_pending = True

def gesture_check_isr(t):
    global gesture_pending
    gesture_pending = True

def rfid_poll_isr(t):
    global rfid_pending
    rfid_pending = True

###############################################################################
# ----------------------------- IR DECODING -----------------------------------
###############################################################################

def decode_ir_to_event(key):
    global mode, alarm1, alarm2
    
    # POWER button - shut down program
    if key == IR_POWER:
        return EV_POWER_OFF
    
    # MODE button - context dependent
    if key == IR_MODE:
        if mode == TIME_DISPLAY:
            return EV_ENTER_SET_TIME
        elif mode == SET_TIME:
            return EV_EXIT_SET_TIME
        elif mode in (SET_ALARM_1, SET_ALARM_2):
            return EV_ALARM_CANCEL
        elif mode in (DELETE_ALARM_SELECTION, DELETE_CONFIRM):
            return EV_DELETE_CANCEL
        return None
    
    # PLAY/PAUSE - confirm button
    if key == IR_PLAY_PAUSE:
        if mode == SET_TIME:
            return EV_TIME_CONFIRM
        elif mode in (SET_ALARM_1, SET_ALARM_2):
            return EV_ALARM_CONFIRM
        elif mode == DELETE_CONFIRM:
            return EV_DELETE_CONFIRM
        return None
    
    # MUTE - enter delete menu
    if key == IR_MUTE:
        if mode == TIME_DISPLAY:
            return EV_ENTER_DELETE_MENU
        return None
    
    # Digits - prioritize in input modes
    if key in [0x16, 0x0C, 0x18, 0x5E, 0x08, 0x1C, 0x5A, 0x42, 0x52, 0x4A]:
        if mode in (SET_TIME, SET_ALARM_1, SET_ALARM_2):
            return EV_TIME_INPUT_DIGIT, decode_digit(key)
    
    # Button "1" behavior
    if key == IR_1:
        if mode == TIME_DISPLAY:
            # Toggle if alarm exists, otherwise enter config
            if alarm1 is not None:
                return EV_ALARM_TOGGLE1
            else:
                return EV_ENTER_SET_ALARM1
        elif mode == DELETE_ALARM_SELECTION:
            return EV_DELETE_SELECT_ALARM1
    
    # Button "2" behavior
    if key == IR_2:
        if mode == TIME_DISPLAY:
            if alarm2 is not None:
                return EV_ALARM_TOGGLE2
            else:
                return EV_ENTER_SET_ALARM2
        elif mode == DELETE_ALARM_SELECTION:
            return EV_DELETE_SELECT_ALARM2
    
    # AM/PM
    if key == IR_PLUS: return EV_TIME_SELECT_AM
    if key == IR_MINUS: return EV_TIME_SELECT_PM
    
    return None

def decode_digit(d):
    table = {
        0x16: '0', 0x0C: '1', 0x18: '2', 0x5E: '3', 0x08: '4',
        0x1C: '5', 0x5A: '6', 0x42: '7', 0x52: '8', 0x4A: '9'
    }
    return table.get(d, "")

###############################################################################
# ----------------------------- HELPER FUNCTIONS ------------------------------
###############################################################################

def convert_24_to_12(h24):
    """Convert 24-hour format to 12-hour with AM/PM"""
    period = "AM" if h24 < 12 else "PM"
    h12 = h24 % 12
    if h12 == 0:
        h12 = 12
    return h12, period

def convert_12_to_24(h12, period):
    """Convert 12-hour format to 24-hour"""
    if period == "AM":
        return h12 % 12
    else:
        return (h12 % 12) + 12

def lcd_show_set_time_ui():
    lcd.clear()
    lcd.write(0, 0, "Set Time (HHMM)")
    lcd.write(0, 1, time_buffer)

def lcd_show_ampm(txt):
    lcd.write(14, 1, txt)

def append_digit_to_time_buffer():
    global time_buffer
    if len(time_buffer) < 4:
        time_buffer += last_digit
        lcd_show_set_time_ui()

def validate_time_input():
    global time_buffer, ampm_flag
    if len(time_buffer) != 4:
        return False
    h = int(time_buffer[:2])
    m = int(time_buffer[2:])
    return 1 <= h <= 12 and 0 <= m < 60 and ampm_flag in ("AM", "PM")

def write_time_to_rtc():
    """Convert and write time to RTC"""
    h12 = int(time_buffer[:2])
    m = int(time_buffer[2:])
    h24 = convert_12_to_24(h12, ampm_flag)
    
    t = time.localtime()
    rtc_tuple = (t[0], t[1], t[2], t[6], h24, m, 0, 0)
    RTC().datetime(rtc_tuple)

def show_temp_message(msg, duration_ms=1000):
    """Set temporary message state without blocking"""
    global ui_message, ui_message_until_ms
    ui_message = msg
    ui_message_until_ms = time.ticks_add(time.ticks_ms(), duration_ms) #do not use time.sleep()
    lcd.clear()
    lcd.write(0, 0, msg)

def render_screen():
    """Render screen based on current mode"""
    if mode == TIME_DISPLAY:
        lcd.clear()
        update_time_display()
    elif mode == SET_TIME:
        lcd_show_set_time_ui()
    elif mode == SET_ALARM_1:
        lcd_show_set_alarm_ui(1)
    elif mode == SET_ALARM_2:
        lcd_show_set_alarm_ui(2)
    elif mode == DELETE_ALARM_SELECTION:
        lcd_show_delete_menu()
    elif mode == DELETE_CONFIRM:
        lcd_show_delete_confirm(selected_alarm_for_delete)
    elif mode == ALARM_ACTIVE:
        # For ALARM_ACTIVE, delegate to alarm_mode
        if alarm_mode == ALARM_RINGING:
            lcd_show_alarm_ringing()
        elif alarm_mode == SNOOZE:
            # During snooze, show current time
            update_time_display()
        # CONFIRMATION mode: message already shown via show_temp_message, no need to render

def update_time_display():
    """Update LCD with current time"""
    rtc = RTC().datetime()
    h24 = rtc[4]
    m = rtc[5]
    s = rtc[6]
    
    h12, period = convert_24_to_12(h24)
    
    lcd.write(0, 0, "Current Time:   ")  # Pad to 16 chars to clear any residue
    lcd.write(0, 1, "{:02d}:{:02d}:{:02d} {}    ".format(h12, m, s, period))  # Pad to 16 chars

def apply_time_shift():
    """Add 13 hours to current RTC time"""
    rtc = RTC().datetime()
    h24 = rtc[4]
    m = rtc[5]
    
    # Add 13 hours
    h24 = (h24 + 13) % 24
    
    t = time.localtime()
    rtc_tuple = (t[0], t[1], t[2], t[6], h24, m, 0, 0)
    RTC().datetime(rtc_tuple)
    
    show_temp_message("Time Shifted", 1000)

def check_alarm_match():
    """Check if current time matches any enabled alarm"""
    global alarm1, alarm2, active_alarm_led, alarm_already_triggered
    
    rtc = RTC().datetime()
    h24 = rtc[4]
    m = rtc[5]
    s = rtc[6]
    
    h12, period = convert_24_to_12(h24)
    
    def match(alarm):
        if not alarm or not alarm.get("enabled", False):
            return False
        return alarm["h"] == h12 and alarm["m"] == m and alarm["ampm"] == period
    
    # Only trigger at second 0
    if s == 0 and not alarm_already_triggered:
        if match(alarm1):
            active_alarm_led = 0
            alarm_already_triggered = True
            mode_handle_event(EV_ALARM_MATCH)
            return
        if match(alarm2):
            active_alarm_led = 1
            alarm_already_triggered = True
            mode_handle_event(EV_ALARM_MATCH)
            return
    
    if s != 0:
        alarm_already_triggered = False

def append_digit_to_alarm_buffer(idx):
    global time_buffer
    if len(time_buffer) < 4:
        time_buffer += last_digit
        lcd_show_set_alarm_ui(idx)

def lcd_show_set_alarm_ui(n):
    lcd.clear()
    lcd.write(0, 0, "Set Alarm " + str(n))
    lcd.write(0, 1, time_buffer)

def save_alarm(n):
    global alarm1, alarm2, time_buffer, ampm_flag
    if not validate_time_input():
        return False
    h = int(time_buffer[:2])
    m = int(time_buffer[2:])
    alarm = {"h": h, "m": m, "ampm": ampm_flag, "enabled": True}
    if n == 1:
        alarm1 = alarm
    if n == 2:
        alarm2 = alarm
    return True

def light_alarm_led(idx):
    """Light LED green to indicate enabled alarm"""
    set_alarm_led(idx, 0, 255, 0)

def toggle_alarm_enabled(n):
    """Toggle alarm enabled status"""
    global alarm1, alarm2
    alarm = alarm1 if n == 1 else alarm2
    if alarm:
        alarm["enabled"] = not alarm["enabled"]
        if alarm["enabled"]:
            light_alarm_led(n - 1)
            show_temp_message("Alarm {} ON".format(n))
        else:
            clear_alarm_led(n - 1)
            show_temp_message("Alarm {} OFF".format(n))

def lcd_show_alarm_ringing():
    lcd.write(0, 0, "ALARM RINGING   ")
    lcd.write(0, 1, "Stop or Snooze  ")

def lcd_show_snooze_started():
    show_temp_message("Snoozed 30 sec", 800)

def reset_alarm_input():
    global time_buffer, ampm_flag
    time_buffer = ""
    ampm_flag = None

def lcd_show_delete_menu():
    lcd.write(0, 0, "Delete Alarm    ")
    lcd.write(0, 1, "Press 1 or 2    ")

def lcd_show_delete_confirm(n):
    lcd.write(0, 0, "Delete Alarm {}? ".format(n))
    lcd.write(0, 1, "PLAY=Yes MODE=No")

def delete_alarm(n):
    global alarm1, alarm2
    if n == 1:
        alarm1 = None
    if n == 2:
        alarm2 = None

def turn_off_alarm_led(n):
    clear_alarm_led(n - 1)

def shutdown_all_hardware():
    """Shut down all actuators and sensors"""
    global program_running
    
    # Stop all timers
    try:
        timer1.deinit()
        timer2.deinit()
        timer3.deinit()
    except:
        pass
    
    # Turn off buzzer
    buzzer.duty_u16(0)
    
    # Turn off all LEDs
    for i in range(8):
        led_strip[i] = [0, 0, 0]
    led_strip.write()
    
    # Display shutdown message
    lcd.clear()
    lcd.write(0, 0, "End Program")
    
    # Set program flag to exit main loop
    program_running = False


###############################################################################
# ----------------------------- Sub-FSM ---------------------------------------
###############################################################################

def alarm_handle_event(event):
    """Handle alarm sub-FSM. Manages alarm_mode and alarm_state.
    Returns True if alarm is finished and should return to TIME_DISPLAY."""
    global alarm_mode, alarm_state, snooze_start_ms
    global alarm_start_time_ms, active_alarm_led
    
    # ALARM_RINGING mode
    if alarm_mode == ALARM_RINGING:
        
        if alarm_state == ALARM_ON:
            
            if event == EV_ALARM_MATCH:
                # Initialize alarm when it starts
                alarm_start_time_ms = time.ticks_ms()
                global alarm_led_on, alarm_buzzer_on
                alarm_led_on = True
                alarm_buzzer_on = True
                update_alarm_outputs()
                lcd_show_alarm_ringing()
                return False
            
            if event == EV_TIMER_TICK:
                # Check timeout
                if alarm_start_time_ms is not None:
                    elapsed = time.ticks_diff(time.ticks_ms(), alarm_start_time_ms)
                    if elapsed >= ALARM_TIMEOUT_MS:
                        alarm_start_time_ms = None
                        stop_alarm_output()
                        set_alarm_led(active_alarm_led, 0, 255, 0)
                        return True  # Exit to TIME_DISPLAY
                
                # Normal blink - toggle on every timer tick (1Hz)
                # No need for separate timing check since timer is already 1 second
                global alarm_led_on, alarm_buzzer_on
                alarm_led_on = not alarm_led_on
                alarm_buzzer_on = not alarm_buzzer_on
                update_alarm_outputs()
                return False
            
            if event == EV_SNOOZE_PRESS:
                alarm_state = ALARM_SNOOZED
                alarm_mode = SNOOZE
                snooze_start_ms = time.ticks_ms()
                stop_alarm_output()
                set_alarm_led(active_alarm_led, 255, 0, 0)  # Red for snooze
                lcd_show_snooze_started()
                return False
            
            if event == EV_GESTURE_DETECTED:
                stop_alarm_output()
                alarm_start_time_ms = None
                # Enter confirmation mode to blink LED
                alarm_mode = CONFIRMATION
                global confirmation_blink_count
                confirmation_blink_count = 0
                set_alarm_led(active_alarm_led, 0, 0, 0)  # Start with LED off
                show_temp_message("Alarm Stopped", 800)
                return False
    
    # SNOOZE mode
    if alarm_mode == SNOOZE:
        
        if alarm_state == ALARM_SNOOZED:
            
            if event == EV_TIMER_TICK:
                # Check snooze timeout
                if snooze_start_ms is not None:
                    elapsed = time.ticks_diff(time.ticks_ms(), snooze_start_ms)
                    if elapsed >= SNOOZE_DURATION_MS:
                        snooze_start_ms = None
                        # Resume alarm
                        alarm_state = ALARM_ON
                        alarm_mode = ALARM_RINGING
                        alarm_start_time_ms = time.ticks_ms()
                        global alarm_led_on, alarm_buzzer_on
                        alarm_led_on = True
                        alarm_buzzer_on = True
                        update_alarm_outputs()
                        lcd_show_alarm_ringing()
                        return False
                
                # No need to update display - handled by centralized render_screen()
                return False
            
            if event == EV_GESTURE_DETECTED:
                stop_alarm_output()
                snooze_start_ms = None
                # Enter confirmation mode to blink LED
                alarm_mode = CONFIRMATION
                global confirmation_blink_count
                confirmation_blink_count = 0
                set_alarm_led(active_alarm_led, 0, 0, 0)  # Start with LED off
                show_temp_message("Alarm Stopped", 800)
                return False
    
    # CONFIRMATION mode - blink LED to confirm alarm stopped
    if alarm_mode == CONFIRMATION:
        if event == EV_TIMER_TICK:
            global confirmation_blink_count
            
            # Check if blink sequence complete
            if confirmation_blink_count >= CONFIRMATION_TOTAL_BLINKS:
                set_alarm_led(active_alarm_led, 0, 255, 0)  # Set to green
                return True  # Exit to TIME_DISPLAY
            
            # Toggle LED between white and off on each timer tick
            color = led_strip[active_alarm_led]
            if color == [0, 0, 0]:
                set_alarm_led(active_alarm_led, 255, 255, 255)  # White on
            else:
                set_alarm_led(active_alarm_led, 0, 0, 0)  # Off
                confirmation_blink_count += 1
            return False
    
    return False

###############################################################################
# ----------------------------- Top-FSM ---------------------------------------
###############################################################################

def mode_handle_event(event):
    global mode, selected_alarm_for_delete
    global time_buffer, ampm_flag, snooze_start_ms
    global alarm_start_time_ms
    global alarm_mode, alarm_state  # Sub-FSM state variables
    global ui_message, ui_message_until_ms
    
    # Handle power off - works in any mode
    if event == EV_POWER_OFF:
        shutdown_all_hardware()
        return
    
    # Centralized EV_TIMER_TICK handling for UI messages and mode-specific updates
    if event == EV_TIMER_TICK:
        now = time.ticks_ms()
        
        # Display active UI message
        if ui_message is not None:
            if time.ticks_diff(now, ui_message_until_ms) < 0:
                lcd.clear()
                lcd.write(0, 0, ui_message)
                return
            else:
                # Message expired, clear and render normal screen
                ui_message = None
                render_screen()
                if mode == TIME_DISPLAY:
                    check_alarm_match()
                return
        
        # Normal mode-specific timer handling
        if mode == TIME_DISPLAY:
            update_time_display()
            check_alarm_match()
        elif mode == ALARM_ACTIVE:
            should_exit = alarm_handle_event(EV_TIMER_TICK)
            if should_exit:
                mode = TIME_DISPLAY
                render_screen()
            else:
                render_screen()
        return
    
    # TIME_DISPLAY
    if mode == TIME_DISPLAY:
        if event == EV_ENTER_SET_TIME:
            mode = SET_TIME
            time_buffer = ""
            ampm_flag = None
            lcd_show_set_time_ui()
            return
        
        if event == EV_ALARM_TOGGLE1:
            toggle_alarm_enabled(1)
            return
        
        if event == EV_ALARM_TOGGLE2:
            toggle_alarm_enabled(2)
            return
        
        if event == EV_ENTER_SET_ALARM1:
            mode = SET_ALARM_1
            reset_alarm_input()
            lcd_show_set_alarm_ui(1)
            return
        
        if event == EV_ENTER_SET_ALARM2:
            mode = SET_ALARM_2
            reset_alarm_input()
            lcd_show_set_alarm_ui(2)
            return
        
        if event == EV_ENTER_DELETE_MENU:
            mode = DELETE_ALARM_SELECTION
            lcd_show_delete_menu()
            return
        
        if event == EV_RFID_DETECTED:
            apply_time_shift()
            return
        
        if event == EV_ALARM_MATCH:
            mode = ALARM_ACTIVE
            alarm_mode = ALARM_RINGING
            alarm_state = ALARM_ON
            # Clear any residual button events
            global button_pending
            button_pending = False
            alarm_handle_event(EV_ALARM_MATCH)
            return
    
    # SET_TIME
    if mode == SET_TIME:
        if event == EV_TIME_INPUT_DIGIT:
            append_digit_to_time_buffer()
            return
        
        if event == EV_TIME_SELECT_AM:
            ampm_flag = "AM"
            lcd_show_ampm("AM")
            return
        
        if event == EV_TIME_SELECT_PM:
            ampm_flag = "PM"
            lcd_show_ampm("PM")
            return
        
        if event == EV_TIME_CONFIRM:
            if validate_time_input():
                write_time_to_rtc()
                mode = TIME_DISPLAY
                show_temp_message("Time Updated", 1000)
            else:
                mode = TIME_DISPLAY
                show_temp_message("Invalid Time", 1000)
            return
        
        if event == EV_EXIT_SET_TIME:
            mode = TIME_DISPLAY
            show_temp_message("Cancel Set Time", 1000)
            return
    
    # SET_ALARM_1
    if mode == SET_ALARM_1:
        if event == EV_TIME_INPUT_DIGIT:
            append_digit_to_alarm_buffer(1)
            return
        if event == EV_TIME_SELECT_AM:
            ampm_flag = "AM"
            lcd_show_ampm("AM")
            return
        if event == EV_TIME_SELECT_PM:
            ampm_flag = "PM"
            lcd_show_ampm("PM")
            return
        if event == EV_ALARM_CONFIRM:
            if save_alarm(1):
                light_alarm_led(0)
                mode = TIME_DISPLAY
                show_temp_message("Alarm 1 Saved", 1000)
            else:
                mode = TIME_DISPLAY
                show_temp_message("Invalid Alarm", 1000)
            return
        if event == EV_ALARM_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
            return
    
    # SET_ALARM_2
    if mode == SET_ALARM_2:
        if event == EV_TIME_INPUT_DIGIT:
            append_digit_to_alarm_buffer(2)
            return
        if event == EV_TIME_SELECT_AM:
            ampm_flag = "AM"
            lcd_show_ampm("AM")
            return
        if event == EV_TIME_SELECT_PM:
            ampm_flag = "PM"
            lcd_show_ampm("PM")
            return
        if event == EV_ALARM_CONFIRM:
            if save_alarm(2):
                light_alarm_led(1)
                mode = TIME_DISPLAY
                show_temp_message("Alarm 2 Saved", 1000)
            else:
                mode = TIME_DISPLAY
                show_temp_message("Invalid Alarm", 1000)
            return
        if event == EV_ALARM_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
            return
    
    # ALARM_ACTIVE (Sub-FSM handles all alarm logic)
    if mode == ALARM_ACTIVE:
        # Delegate everything to Sub-FSM
        should_exit = alarm_handle_event(event)
        if should_exit:
            mode = TIME_DISPLAY
            render_screen()
        return
    
    # DELETE_ALARM_SELECTION
    if mode == DELETE_ALARM_SELECTION:
        if event == EV_DELETE_SELECT_ALARM1:
            selected_alarm_for_delete = 1
            mode = DELETE_CONFIRM
            lcd_show_delete_confirm(1)
            return
        if event == EV_DELETE_SELECT_ALARM2:
            selected_alarm_for_delete = 2
            mode = DELETE_CONFIRM
            lcd_show_delete_confirm(2)
            return
        if event == EV_DELETE_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
            return
    
    # DELETE_CONFIRM
    if mode == DELETE_CONFIRM:
        if event == EV_DELETE_CONFIRM:
            delete_alarm(selected_alarm_for_delete)
            turn_off_alarm_led(selected_alarm_for_delete)
            mode = TIME_DISPLAY
            show_temp_message("Alarm Deleted", 1000)
            return
        if event == EV_DELETE_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
            return

###############################################################################
# ----------------------------- ISR HOOK SETUP --------------------------------
###############################################################################

# IR interrupt
ir = NEC_8(ir_pin, ir_callback)

# Button interrupt (falling edge for PULL_UP)
button.irq(trigger=Pin.IRQ_FALLING, handler=button_isr)

# Timer tick (1s)
timer1 = Timer()
timer1.init(period=1000, mode=Timer.PERIODIC, callback=timer_isr)

# Gesture check timer
timer2 = Timer()
timer2.init(period=1000, mode=Timer.PERIODIC, callback=gesture_check_isr)

# RFID check trigger timer (actual polling in main loop)
timer3 = Timer()
timer3.init(period=700, mode=Timer.PERIODIC, callback=rfid_poll_isr)

###############################################################################
# ----------------------------- MAIN EVENT LOOP -------------------------------
###############################################################################

# Show startup message (will be displayed by first timer tick)
show_temp_message("System Ready", 1000)

while program_running:
    
    # IR event
    if ir_pending:
        ir_pending = False
        decoded = decode_ir_to_event(last_ir_value)
        if decoded:
            if isinstance(decoded, tuple):
                event, digit = decoded
                last_digit = digit
                mode_handle_event(event)
            else:
                mode_handle_event(decoded)
    
    # Button interrupt (with debounce and actual state verification)
    if button_pending:
        button_pending = False
        if mode == ALARM_ACTIVE:
            now = time.ticks_ms()
            # Check debounce time
            if time.ticks_diff(now, last_button_press_ms) > button_debounce_ms:
                # Verify button is actually pressed (low for PULL_UP)
                if button.value() == 0:
                    last_button_press_ms = now
                    mode_handle_event(EV_SNOOZE_PRESS)
    
    # Timer tick
    if timer_pending:
        timer_pending = False
        mode_handle_event(EV_TIMER_TICK)
    
    # Gesture event (only process during alarm)
    if gesture_pending:
        gesture_pending = False
        if mode == ALARM_ACTIVE:
            dist = measure_distance_cm()
            if dist < 8:
                gesture_counter += 1
                if gesture_counter >= 5:
                    gesture_counter = 0
                    mode_handle_event(EV_GESTURE_DETECTED)
            else:
                gesture_counter = 0
    
    # RFID event (only in TIME_DISPLAY mode per Use Case 6)
    if rfid_pending:
        rfid_pending = False
        if mode == TIME_DISPLAY:
            id_str, text = rfid_read_no_block()
            if id_str:
                mode_handle_event(EV_RFID_DETECTED)
    
    time.sleep_ms(5)