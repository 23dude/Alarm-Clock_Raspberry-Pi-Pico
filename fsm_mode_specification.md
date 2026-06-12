# FSM Mode Specification

Complete specification of all modes in the alarm clock finite state machine, including entry/exit conditions and major actions.

## Top-Level FSM Modes

### MODE 0: TIME_DISPLAY

**Entry Conditions:**
- System startup (initial state)
- From `SET_TIME` after confirming or canceling time input
- From `SET_ALARM_1/2` after confirming or canceling alarm configuration
- From `DELETE_ALARM_SELECTION` or `DELETE_CONFIRM` after canceling deletion
- From `ALARM_ACTIVE` after alarm sequence completes (timeout, gesture stop, or confirmation blink finishes)

**Exit Conditions:**
- IR MODE button pressed → `SET_TIME`
- IR "1" button pressed (no alarm1 exists) → `SET_ALARM_1`
- IR "2" button pressed (no alarm2 exists) → `SET_ALARM_2`
- IR MUTE button pressed → `DELETE_ALARM_SELECTION`
- Alarm time matches enabled alarm → `ALARM_ACTIVE`
- IR POWER button → Program shutdown

**Major Actions:**
- Update LCD display every second with current time (HH:MM:SS AM/PM)
- Check for alarm matches every second at second=0
- Handle alarm toggle requests (IR "1"/"2" when alarm exists)
- Handle RFID time shift (+13 hours)
- Display padded 16-char strings to prevent LCD residue

---

### MODE 1: SET_TIME

**Entry Conditions:**
- From `TIME_DISPLAY` when IR MODE button pressed

**Exit Conditions:**
- IR MODE button pressed again → `TIME_DISPLAY` (cancel)
- IR PLAY/PAUSE button pressed → `TIME_DISPLAY` (confirm if valid, reject if invalid)

**Major Actions:**
- Display "Set Time (HHMM)" prompt
- Accumulate 4 digits from IR numeric keys into `time_buffer`
- Accept AM/PM selection via IR +/- buttons
- Validate input (HH: 1-12, MM: 0-59, AM/PM selected)
- Write validated time to RTC in 24-hour format
- Show success/failure message via non-blocking temp message system

---

### MODE 2: SET_ALARM_1

**Entry Conditions:**
- From `TIME_DISPLAY` when IR "1" pressed and alarm1 does not exist

**Exit Conditions:**
- IR MODE button pressed → `TIME_DISPLAY` (cancel)
- IR PLAY/PAUSE button pressed → `TIME_DISPLAY` (confirm if valid, reject if invalid)

**Major Actions:**
- Display "Set Alarm 1" prompt
- Accumulate 4 digits from IR numeric keys into `time_buffer`
- Accept AM/PM selection via IR +/- buttons
- Validate input (HH: 1-12, MM: 0-59, AM/PM selected)
- Store alarm as dictionary: `{"h": h, "m": m, "ampm": "AM/PM", "enabled": True}`
- Light LED index 0 green to indicate enabled alarm
- Show success/failure message

---

### MODE 3: SET_ALARM_2

**Entry Conditions:**
- From `TIME_DISPLAY` when IR "2" pressed and alarm2 does not exist

**Exit Conditions:**
- IR MODE button pressed → `TIME_DISPLAY` (cancel)
- IR PLAY/PAUSE button pressed → `TIME_DISPLAY` (confirm if valid, reject if invalid)

**Major Actions:**
- Display "Set Alarm 2" prompt
- Accumulate 4 digits from IR numeric keys into `time_buffer`
- Accept AM/PM selection via IR +/- buttons
- Validate input (HH: 1-12, MM: 0-59, AM/PM selected)
- Store alarm as dictionary: `{"h": h, "m": m, "ampm": "AM/PM", "enabled": True}`
- Light LED index 1 green to indicate enabled alarm
- Show success/failure message

---

### MODE 4: ALARM_ACTIVE (Sub-FSM Container)

**Entry Conditions:**
- From `TIME_DISPLAY` when RTC time matches an enabled alarm (at second=0)

**Exit Conditions:**
- Sub-FSM returns `True` (alarm finished) → `TIME_DISPLAY`

**Major Actions:**
- Delegate all events to Sub-FSM (`alarm_handle_event`)
- Sub-FSM manages three internal modes: `ALARM_RINGING`, `SNOOZE`, `CONFIRMATION`
- Clear residual button events on entry to prevent spurious snooze
- Re-render screen after each Sub-FSM tick

---

### MODE 5: DELETE_ALARM_SELECTION

**Entry Conditions:**
- From `TIME_DISPLAY` when IR MUTE button pressed

**Exit Conditions:**
- IR "1" pressed → `DELETE_CONFIRM` (select alarm1 for deletion)
- IR "2" pressed → `DELETE_CONFIRM` (select alarm2 for deletion)
- IR MODE button pressed → `TIME_DISPLAY` (cancel)

**Major Actions:**
- Display "Delete Alarm" menu
- Display "Press 1 or 2" prompt
- Wait for user selection

---

### MODE 6: DELETE_CONFIRM

**Entry Conditions:**
- From `DELETE_ALARM_SELECTION` when IR "1" or "2" pressed

**Exit Conditions:**
- IR PLAY/PAUSE pressed → `TIME_DISPLAY` (confirm deletion)
- IR MODE button pressed → `TIME_DISPLAY` (cancel deletion)

**Major Actions:**
- Display "Delete Alarm X?" confirmation prompt
- Display "PLAY=Yes MODE=No" instruction
- If confirmed: set `alarm1` or `alarm2` to `None`, turn off corresponding LED
- Show deletion confirmation message

---

## Alarm Sub-FSM Modes (within ALARM_ACTIVE)

### Sub-Mode: ALARM_RINGING (State: ALARM_ON)

**Entry Conditions:**
- From `TIME_DISPLAY` via `EV_ALARM_MATCH` event
- From `SNOOZE` after 30-second snooze timeout expires

**Exit Conditions:**
- Physical button press (snooze button) → `SNOOZE` mode
- Gesture detected (hand wave < 8cm, 5 consecutive reads) → `CONFIRMATION` mode
- 60-second timeout → Return `True` to exit `ALARM_ACTIVE`

**Major Actions:**
- Initialize flags: `alarm_led_on = True`, `alarm_buzzer_on = True`
- Display "ALARM RINGING / Stop or Snooze" on LCD
- Toggle LED (red) and buzzer on/off every 1 Hz timer tick
- Track elapsed time from `alarm_start_time_ms`
- Output driven by state flags via `update_alarm_outputs()`

---

### Sub-Mode: SNOOZE (State: ALARM_SNOOZED)

**Entry Conditions:**
- From `ALARM_RINGING` when snooze button pressed

**Exit Conditions:**
- 30-second timeout → Resume `ALARM_RINGING`
- Gesture detected → `CONFIRMATION` mode

**Major Actions:**
- Stop alarm outputs (buzzer OFF, LED set to solid red)
- Display "Snoozed 30 sec" temp message (800ms)
- Update LCD with current time during snooze period
- Track snooze duration from `snooze_start_ms`
- On timeout: reinitialize alarm flags and resume ringing

---

### Sub-Mode: CONFIRMATION

**Entry Conditions:**
- From `ALARM_RINGING` when gesture detected
- From `SNOOZE` when gesture detected

**Exit Conditions:**
- 3 blink cycles complete → Return `True` to exit `ALARM_ACTIVE`

**Major Actions:**
- Stop buzzer, start with LED off
- Display "Alarm Stopped" temp message (800ms)
- Toggle LED between white and off on each 1 Hz timer tick
- Increment `confirmation_blink_count` after each OFF phase
- After 3 complete blinks: set LED to green and return to `TIME_DISPLAY`

---

## Event Handling Summary

| Mode | Primary Input Sources | Output Channels |
|------|----------------------|-----------------|
| TIME_DISPLAY | IR, RTC timer, RFID, alarm match | LCD (time), LED (alarm status) |
| SET_TIME | IR (digits, +/-, MODE, PLAY/PAUSE) | LCD (input prompt) |
| SET_ALARM_1/2 | IR (digits, +/-, MODE, PLAY/PAUSE) | LCD (input prompt), LED (green when saved) |
| ALARM_ACTIVE | Timer, button ISR, gesture sensor | LCD, LED (red blink), buzzer |
| DELETE_* | IR (1, 2, MODE, PLAY/PAUSE) | LCD (prompts), LED (off on delete) |

---

## System Events

Events that trigger state transitions in the FSM, categorized by source.

### Hardware Events

**IR Remote Receiver (NEC_8 protocol via ISR):**
- `EV_POWER_OFF` - IR POWER button (0x45) pressed
- `EV_ENTER_SET_TIME` - IR MODE button (0x46) pressed in TIME_DISPLAY
- `EV_EXIT_SET_TIME` - IR MODE button pressed in SET_TIME
- `EV_ALARM_CANCEL` - IR MODE button pressed in SET_ALARM_1/2
- `EV_DELETE_CANCEL` - IR MODE button pressed in delete modes
- `EV_TIME_CONFIRM` - IR PLAY/PAUSE button (0x44) pressed in SET_TIME
- `EV_ALARM_CONFIRM` - IR PLAY/PAUSE button pressed in SET_ALARM_1/2
- `EV_DELETE_CONFIRM` - IR PLAY/PAUSE button pressed in DELETE_CONFIRM
- `EV_ENTER_DELETE_MENU` - IR MUTE button (0x47) pressed in TIME_DISPLAY
- `EV_TIME_INPUT_DIGIT` - IR digit buttons (0-9) pressed in input modes
- `EV_TIME_SELECT_AM` - IR PLUS button (0x09) pressed
- `EV_TIME_SELECT_PM` - IR MINUS button (0x15) pressed
- `EV_ALARM_TOGGLE1` - IR "1" button (0x0C) pressed when alarm1 exists
- `EV_ALARM_TOGGLE2` - IR "2" button (0x18) pressed when alarm2 exists
- `EV_ENTER_SET_ALARM1` - IR "1" button pressed when alarm1 does not exist
- `EV_ENTER_SET_ALARM2` - IR "2" button pressed when alarm2 does not exist
- `EV_DELETE_SELECT_ALARM1` - IR "1" button pressed in DELETE_ALARM_SELECTION
- `EV_DELETE_SELECT_ALARM2` - IR "2" button pressed in DELETE_ALARM_SELECTION

**Physical Snooze Button (GP14, PULL_UP with falling edge ISR):**
- `EV_SNOOZE_PRESS` - Button pressed during ALARM_ACTIVE mode (50ms debounced with pin state verification)

**Hardware Timer (Timer1, 1 Hz periodic):**
- `EV_TIMER_TICK` - Fires every 1000ms, drives time display updates, alarm cadence, confirmation blinks

**Gesture Sensor (HC-SR04 ultrasonic, polled every 1s via Timer2 ISR):**
- `EV_GESTURE_DETECTED` - Hand wave detected (distance < 8cm for 5 consecutive readings) during ALARM_ACTIVE

**RFID Reader (MFRC522 SPI, polled every 700ms via Timer3 ISR):**
- `EV_RFID_DETECTED` - Valid RFID tag detected in TIME_DISPLAY mode

**RTC Alarm Match (software comparison at second=0):**
- `EV_ALARM_MATCH` - Current time matches enabled alarm1 or alarm2 configuration

---

### Software Events

**Internal Timeouts (tracked via `time.ticks_ms()`):**
- Alarm timeout - 60 seconds elapsed since alarm start → exit ALARM_ACTIVE
- Snooze timeout - 30 seconds elapsed since snooze start → resume ALARM_RINGING
- UI message expiry - Temporary message duration expired → clear message and render screen
- Confirmation blink completion - 3 blink cycles complete → exit ALARM_ACTIVE

**State Machine Logic:**
- Validation results - Input validation pass/fail determines transition path
- Sub-FSM completion - `alarm_handle_event()` returns `True` → parent FSM exits ALARM_ACTIVE

---

### Event Processing Architecture

**ISR to Main Loop Flow:**
1. Hardware interrupt fires (IR, button, timer, etc.)
2. ISR sets flag (e.g., `ir_pending`, `button_pending`, `timer_pending`)
3. ISR exits immediately (minimal processing)
4. Main loop detects flag in next iteration (5ms poll cycle)
5. Main loop processes event, clears flag, calls `mode_handle_event()`

**Event Priority (processed in order):**
1. IR events
2. Button events (with debounce verification)
3. Timer ticks
4. Gesture events (ALARM_ACTIVE only)
5. RFID events (TIME_DISPLAY only)

**Critical Event Characteristics:**
- All ISRs are non-blocking (set flag and return)
- Main loop uses 5ms throttle (`time.sleep_ms(5)`)
- Button uses dual verification (ISR flag + debounce + pin state check)
- Gesture requires 5 consecutive positive readings to filter noise
- RFID polling is non-blocking (`rfid_read_no_block()`)
- Timer tick is single source of truth for time-based events

---

## State Transition Tables

Comprehensive mapping of state transitions with associated actions.

### Top-Level FSM: TIME_DISPLAY Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| TIME_DISPLAY | EV_TIMER_TICK | TIME_DISPLAY | Update LCD with current time (HH:MM:SS AM/PM), check alarm match |
| TIME_DISPLAY | EV_ENTER_SET_TIME | SET_TIME | Clear `time_buffer`, clear `ampm_flag`, display "Set Time (HHMM)" |
| TIME_DISPLAY | EV_ALARM_TOGGLE1 | TIME_DISPLAY | Toggle `alarm1["enabled"]`, update LED (green=on, off=off), show temp message |
| TIME_DISPLAY | EV_ALARM_TOGGLE2 | TIME_DISPLAY | Toggle `alarm2["enabled"]`, update LED (green=on, off=off), show temp message |
| TIME_DISPLAY | EV_ENTER_SET_ALARM1 | SET_ALARM_1 | Reset input buffers, display "Set Alarm 1" |
| TIME_DISPLAY | EV_ENTER_SET_ALARM2 | SET_ALARM_2 | Reset input buffers, display "Set Alarm 2" |
| TIME_DISPLAY | EV_ENTER_DELETE_MENU | DELETE_ALARM_SELECTION | Display "Delete Alarm / Press 1 or 2" |
| TIME_DISPLAY | EV_RFID_DETECTED | TIME_DISPLAY | Add 13 hours to RTC, show "Time Shifted" message |
| TIME_DISPLAY | EV_ALARM_MATCH | ALARM_ACTIVE | Set `alarm_mode=ALARM_RINGING`, `alarm_state=ALARM_ON`, clear `button_pending`, delegate to Sub-FSM |
| TIME_DISPLAY | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()`, deinit timers, turn off outputs, display "End Program" |

---

### Top-Level FSM: SET_TIME Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| SET_TIME | EV_TIME_INPUT_DIGIT | SET_TIME | Append digit to `time_buffer` (max 4 chars), refresh display |
| SET_TIME | EV_TIME_SELECT_AM | SET_TIME | Set `ampm_flag="AM"`, display "AM" at position (14,1) |
| SET_TIME | EV_TIME_SELECT_PM | SET_TIME | Set `ampm_flag="PM"`, display "PM" at position (14,1) |
| SET_TIME | EV_TIME_CONFIRM | TIME_DISPLAY | Validate input (HH:1-12, MM:0-59, AM/PM set), write to RTC if valid, show "Time Updated" or "Invalid Time" |
| SET_TIME | EV_EXIT_SET_TIME | TIME_DISPLAY | Show "Cancel Set Time" message, discard input |
| SET_TIME | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()` |

---

### Top-Level FSM: SET_ALARM_1 Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| SET_ALARM_1 | EV_TIME_INPUT_DIGIT | SET_ALARM_1 | Append digit to `time_buffer` (max 4 chars), refresh display |
| SET_ALARM_1 | EV_TIME_SELECT_AM | SET_ALARM_1 | Set `ampm_flag="AM"`, display "AM" |
| SET_ALARM_1 | EV_TIME_SELECT_PM | SET_ALARM_1 | Set `ampm_flag="PM"`, display "PM" |
| SET_ALARM_1 | EV_ALARM_CONFIRM | TIME_DISPLAY | Validate input, save to `alarm1` dict with `enabled=True`, light LED0 green, show "Alarm 1 Saved" or "Invalid Alarm" |
| SET_ALARM_1 | EV_ALARM_CANCEL | TIME_DISPLAY | Discard input, render TIME_DISPLAY screen |
| SET_ALARM_1 | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()` |

---

### Top-Level FSM: SET_ALARM_2 Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| SET_ALARM_2 | EV_TIME_INPUT_DIGIT | SET_ALARM_2 | Append digit to `time_buffer` (max 4 chars), refresh display |
| SET_ALARM_2 | EV_TIME_SELECT_AM | SET_ALARM_2 | Set `ampm_flag="AM"`, display "AM" |
| SET_ALARM_2 | EV_TIME_SELECT_PM | SET_ALARM_2 | Set `ampm_flag="PM"`, display "PM" |
| SET_ALARM_2 | EV_ALARM_CONFIRM | TIME_DISPLAY | Validate input, save to `alarm2` dict with `enabled=True`, light LED1 green, show "Alarm 2 Saved" or "Invalid Alarm" |
| SET_ALARM_2 | EV_ALARM_CANCEL | TIME_DISPLAY | Discard input, render TIME_DISPLAY screen |
| SET_ALARM_2 | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()` |

---

### Top-Level FSM: DELETE_ALARM_SELECTION Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| DELETE_ALARM_SELECTION | EV_DELETE_SELECT_ALARM1 | DELETE_CONFIRM | Set `selected_alarm_for_delete=1`, display "Delete Alarm 1? / PLAY=Yes MODE=No" |
| DELETE_ALARM_SELECTION | EV_DELETE_SELECT_ALARM2 | DELETE_CONFIRM | Set `selected_alarm_for_delete=2`, display "Delete Alarm 2? / PLAY=Yes MODE=No" |
| DELETE_ALARM_SELECTION | EV_DELETE_CANCEL | TIME_DISPLAY | Render TIME_DISPLAY screen |
| DELETE_ALARM_SELECTION | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()` |

---

### Top-Level FSM: DELETE_CONFIRM Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| DELETE_CONFIRM | EV_DELETE_CONFIRM | TIME_DISPLAY | Set `alarm1` or `alarm2` to `None`, turn off corresponding LED, show "Alarm Deleted" |
| DELETE_CONFIRM | EV_DELETE_CANCEL | TIME_DISPLAY | Render TIME_DISPLAY screen without deletion |
| DELETE_CONFIRM | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()` |

---

### Top-Level FSM: ALARM_ACTIVE Mode (Delegates to Sub-FSM)

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| ALARM_ACTIVE | EV_ALARM_MATCH | ALARM_ACTIVE | Delegate to Sub-FSM (initializes alarm) |
| ALARM_ACTIVE | EV_TIMER_TICK | ALARM_ACTIVE or TIME_DISPLAY | Delegate to Sub-FSM, if Sub-FSM returns `True` → TIME_DISPLAY with screen render |
| ALARM_ACTIVE | EV_SNOOZE_PRESS | ALARM_ACTIVE | Delegate to Sub-FSM (may transition to SNOOZE sub-mode) |
| ALARM_ACTIVE | EV_GESTURE_DETECTED | ALARM_ACTIVE | Delegate to Sub-FSM (may transition to CONFIRMATION sub-mode) |
| ALARM_ACTIVE | EV_POWER_OFF | (exit) | Call `shutdown_all_hardware()` |

---

### Sub-FSM: ALARM_RINGING Mode (State: ALARM_ON)

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| ALARM_RINGING (ALARM_ON) | EV_ALARM_MATCH | ALARM_RINGING | Set `alarm_start_time_ms`, set `alarm_led_on=True`, `alarm_buzzer_on=True`, call `update_alarm_outputs()`, display "ALARM RINGING" |
| ALARM_RINGING (ALARM_ON) | EV_TIMER_TICK | ALARM_RINGING or (exit) | Check 60s timeout → exit if expired. Otherwise toggle `alarm_led_on` and `alarm_buzzer_on`, call `update_alarm_outputs()` |
| ALARM_RINGING (ALARM_ON) | EV_SNOOZE_PRESS | SNOOZE (ALARM_SNOOZED) | Set `snooze_start_ms`, call `stop_alarm_output()`, set LED to solid red, show "Snoozed 30 sec" |
| ALARM_RINGING (ALARM_ON) | EV_GESTURE_DETECTED | CONFIRMATION | Call `stop_alarm_output()`, clear `alarm_start_time_ms`, reset `confirmation_blink_count`, set LED off, show "Alarm Stopped" |

---

### Sub-FSM: SNOOZE Mode (State: ALARM_SNOOZED)

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| SNOOZE (ALARM_SNOOZED) | EV_TIMER_TICK | SNOOZE or ALARM_RINGING | Check 30s timeout → resume ALARM_RINGING if expired (reinit flags, set `alarm_start_time_ms`, call `update_alarm_outputs()`, display "ALARM RINGING") |
| SNOOZE (ALARM_SNOOZED) | EV_GESTURE_DETECTED | CONFIRMATION | Call `stop_alarm_output()`, clear `snooze_start_ms`, reset `confirmation_blink_count`, set LED off, show "Alarm Stopped" |

---

### Sub-FSM: CONFIRMATION Mode

| Current State | Event | Next State | Actions |
|--------------|-------|------------|---------|
| CONFIRMATION | EV_TIMER_TICK | CONFIRMATION or (exit to TIME_DISPLAY) | Check blink count: if ≥3 → set LED green, return `True` to exit. Otherwise toggle LED white/off, increment count on OFF phase |

---

## Special Mode Characteristics

### Non-blocking UI Message System
- All modes can display temporary messages via `show_temp_message(msg, duration_ms)`
- Message expiry handled in `EV_TIMER_TICK` centralized handler
- Prevents blocking sleeps that would freeze FSM

### Power-Off Pathway
- `EV_POWER_OFF` handled in any mode
- Deinitializes all timers, stops outputs, displays "End Program", exits loop

### State Persistence
- Alarm configurations stored in global dictionaries (`alarm1`, `alarm2`)
- Mode transitions preserve alarm data
- LED status reflects alarm enabled/disabled state across modes

---

## Pseudocode for Core System Behavior

### FSM Architecture Overview

```
Top-Level FSM (mode variable)
 ├── TIME_DISPLAY
 ├── SET_TIME
 ├── SET_ALARM_1
 ├── SET_ALARM_2
 ├── ALARM_ACTIVE → delegates all events to Sub-FSM
 ├── DELETE_ALARM_SELECTION
 └── DELETE_CONFIRM

Sub-FSM (alarm_mode variable, within ALARM_ACTIVE)
 ├── ALARM_RINGING (alarm_state: ALARM_ON)
 ├── SNOOZE (alarm_state: ALARM_SNOOZED)
 └── CONFIRMATION
```

---

### Top-Level FSM Implementation

```python
def mode_handle_event(event):
    global mode, alarm_mode, alarm_state
    
    # ========== EV_POWER_OFF (global handler) ==========
    if event == EV_POWER_OFF:
        shutdown_all_hardware()
        return
    
    # ========== EV_TIMER_TICK (centralized UI message + mode dispatch) ==========
    if event == EV_TIMER_TICK:
        if ui_message_expired():
            clear_message_and_render_screen()
            if mode == TIME_DISPLAY:
                check_alarm_match()
            return
        
        if mode == TIME_DISPLAY:
            update_time_display()
            check_alarm_match()
        
        elif mode == ALARM_ACTIVE:
            should_exit = alarm_handle_event(EV_TIMER_TICK)
            if should_exit:
                mode = TIME_DISPLAY
                render_screen()
        return
    
    # ========== TIME_DISPLAY ==========
    if mode == TIME_DISPLAY:
        if event == EV_ENTER_SET_TIME:
            mode = SET_TIME
            reset_input_buffers()
            lcd_show_set_time_ui()
        
        elif event == EV_ENTER_SET_ALARM1:
            mode = SET_ALARM_1
            reset_alarm_input()
            lcd_show_set_alarm_ui(1)
        
        elif event == EV_ENTER_SET_ALARM2:
            mode = SET_ALARM_2
            reset_alarm_input()
            lcd_show_set_alarm_ui(2)
        
        elif event == EV_ALARM_TOGGLE1:
            toggle_alarm_enabled(1)
        
        elif event == EV_ALARM_TOGGLE2:
            toggle_alarm_enabled(2)
        
        elif event == EV_ENTER_DELETE_MENU:
            mode = DELETE_ALARM_SELECTION
            lcd_show_delete_menu()
        
        elif event == EV_RFID_DETECTED:
            apply_time_shift()
        
        elif event == EV_ALARM_MATCH:
            mode = ALARM_ACTIVE
            alarm_mode = ALARM_RINGING
            alarm_state = ALARM_ON
            clear_button_pending()
            alarm_handle_event(EV_ALARM_MATCH)
        return
    
    # ========== SET_TIME ==========
    if mode == SET_TIME:
        if event == EV_TIME_INPUT_DIGIT:
            append_digit_to_time_buffer()
        
        elif event == EV_TIME_SELECT_AM:
            set_ampm_flag("AM")
        
        elif event == EV_TIME_SELECT_PM:
            set_ampm_flag("PM")
        
        elif event == EV_TIME_CONFIRM:
            if validate_time_input():
                write_time_to_rtc()
                show_temp_message("Time Updated")
            else:
                show_temp_message("Invalid Time")
            mode = TIME_DISPLAY
        
        elif event == EV_EXIT_SET_TIME:
            mode = TIME_DISPLAY
            show_temp_message("Cancel Set Time")
        return
    
    # ========== SET_ALARM_1 ==========
    if mode == SET_ALARM_1:
        if event == EV_TIME_INPUT_DIGIT:
            append_digit_to_alarm_buffer(1)
        
        elif event == EV_TIME_SELECT_AM:
            set_ampm_flag("AM")
        
        elif event == EV_TIME_SELECT_PM:
            set_ampm_flag("PM")
        
        elif event == EV_ALARM_CONFIRM:
            if save_alarm(1):
                light_alarm_led(0)
                show_temp_message("Alarm 1 Saved")
            else:
                show_temp_message("Invalid Alarm")
            mode = TIME_DISPLAY
        
        elif event == EV_ALARM_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
        return
    
    # ========== SET_ALARM_2 ==========
    if mode == SET_ALARM_2:
        if event == EV_TIME_INPUT_DIGIT:
            append_digit_to_alarm_buffer(2)
        
        elif event == EV_TIME_SELECT_AM:
            set_ampm_flag("AM")
        
        elif event == EV_TIME_SELECT_PM:
            set_ampm_flag("PM")
        
        elif event == EV_ALARM_CONFIRM:
            if save_alarm(2):
                light_alarm_led(1)
                show_temp_message("Alarm 2 Saved")
            else:
                show_temp_message("Invalid Alarm")
            mode = TIME_DISPLAY
        
        elif event == EV_ALARM_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
        return
    
    # ========== ALARM_ACTIVE (delegates to Sub-FSM) ==========
    if mode == ALARM_ACTIVE:
        should_exit = alarm_handle_event(event)
        if should_exit:
            mode = TIME_DISPLAY
            render_screen()
        return
    
    # ========== DELETE_ALARM_SELECTION ==========
    if mode == DELETE_ALARM_SELECTION:
        if event == EV_DELETE_SELECT_ALARM1:
            selected_alarm_for_delete = 1
            mode = DELETE_CONFIRM
            lcd_show_delete_confirm(1)
        
        elif event == EV_DELETE_SELECT_ALARM2:
            selected_alarm_for_delete = 2
            mode = DELETE_CONFIRM
            lcd_show_delete_confirm(2)
        
        elif event == EV_DELETE_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
        return
    
    # ========== DELETE_CONFIRM ==========
    if mode == DELETE_CONFIRM:
        if event == EV_DELETE_CONFIRM:
            delete_alarm(selected_alarm_for_delete)
            turn_off_alarm_led(selected_alarm_for_delete)
            show_temp_message("Alarm Deleted")
            mode = TIME_DISPLAY
        
        elif event == EV_DELETE_CANCEL:
            mode = TIME_DISPLAY
            render_screen()
        return
```

---

### Sub-FSM Implementation (Alarm Management)

```python
def alarm_handle_event(event):
    """Returns True if alarm sequence complete and should exit to TIME_DISPLAY"""
    global alarm_mode, alarm_state
    
    # ========== ALARM_RINGING (ALARM_ON) ==========
    if alarm_mode == ALARM_RINGING and alarm_state == ALARM_ON:
        
        if event == EV_ALARM_MATCH:
            initialize_alarm_start_time()
            set_alarm_flags_on()
            update_alarm_outputs()
            lcd_show_alarm_ringing()
            return False
        
        elif event == EV_TIMER_TICK:
            if check_alarm_timeout():
                stop_alarm_output()
                set_led_green()
                return True  # Exit to TIME_DISPLAY
            
            toggle_alarm_flags()
            update_alarm_outputs()
            return False
        
        elif event == EV_SNOOZE_PRESS:
            alarm_state = ALARM_SNOOZED
            alarm_mode = SNOOZE
            initialize_snooze_start_time()
            stop_alarm_output()
            set_led_red()
            show_temp_message("Snoozed 30 sec")
            return False
        
        elif event == EV_GESTURE_DETECTED:
            stop_alarm_output()
            alarm_mode = CONFIRMATION
            reset_confirmation_blink_count()
            set_led_off()
            show_temp_message("Alarm Stopped")
            return False
    
    # ========== SNOOZE (ALARM_SNOOZED) ==========
    if alarm_mode == SNOOZE and alarm_state == ALARM_SNOOZED:
        
        if event == EV_TIMER_TICK:
            if check_snooze_timeout():
                alarm_state = ALARM_ON
                alarm_mode = ALARM_RINGING
                initialize_alarm_start_time()
                set_alarm_flags_on()
                update_alarm_outputs()
                lcd_show_alarm_ringing()
            return False
        
        elif event == EV_GESTURE_DETECTED:
            stop_alarm_output()
            alarm_mode = CONFIRMATION
            reset_confirmation_blink_count()
            set_led_off()
            show_temp_message("Alarm Stopped")
            return False
    
    # ========== CONFIRMATION ==========
    if alarm_mode == CONFIRMATION:
        
        if event == EV_TIMER_TICK:
            if confirmation_blink_complete():
                set_led_green()
                return True  # Exit to TIME_DISPLAY
            
            toggle_led_white_off()
            increment_blink_count_on_off()
            return False
    
    return False
```

---

### Main Event Loop

```python
# Show startup message
show_temp_message("System Ready", 1000)

while program_running:
    
    # IR remote events
    if ir_pending:
        ir_pending = False
        event = decode_ir_to_event(last_ir_value)
        if event:
            mode_handle_event(event)
    
    # Physical snooze button (with debounce + pin verification)
    if button_pending:
        button_pending = False
        if mode == ALARM_ACTIVE:
            if verify_button_debounce_and_state():
                mode_handle_event(EV_SNOOZE_PRESS)
    
    # 1 Hz timer tick
    if timer_pending:
        timer_pending = False
        mode_handle_event(EV_TIMER_TICK)
    
    # Gesture sensor (ALARM_ACTIVE only)
    if gesture_pending:
        gesture_pending = False
        if mode == ALARM_ACTIVE:
            if detect_gesture():
                mode_handle_event(EV_GESTURE_DETECTED)
    
    # RFID reader (TIME_DISPLAY only)
    if rfid_pending:
        rfid_pending = False
        if mode == TIME_DISPLAY:
            if read_rfid_tag():
                mode_handle_event(EV_RFID_DETECTED)
    
    time.sleep_ms(5)
```

---

### Interrupt Service Routines

```python
# ISR flags
ir_pending = False
button_pending = False
timer_pending = False
gesture_pending = False
rfid_pending = False

def ir_callback(data, addr, ctrl):
    global ir_pending, last_ir_value
    if data >= 0:
        ir_pending = True
        last_ir_value = data

def button_isr(pin):
    global button_pending
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
```

---

### Helper Functions (Abstractions)

```python
# Time management
def update_time_display(): pass
def write_time_to_rtc(): pass
def apply_time_shift(): pass
def check_alarm_match(): pass

# Input handling
def reset_input_buffers(): pass
def append_digit_to_time_buffer(): pass
def append_digit_to_alarm_buffer(n): pass
def validate_time_input(): pass
def set_ampm_flag(value): pass

# Alarm configuration
def save_alarm(n): pass
def delete_alarm(n): pass
def toggle_alarm_enabled(n): pass
def reset_alarm_input(): pass

# Alarm output control
def update_alarm_outputs(): pass
def stop_alarm_output(): pass
def set_alarm_flags_on(): pass
def toggle_alarm_flags(): pass

# LED control
def light_alarm_led(index): pass
def set_led_red(): pass
def set_led_green(): pass
def set_led_off(): pass
def turn_off_alarm_led(n): pass
def toggle_led_white_off(): pass

# LCD display
def lcd_show_set_time_ui(): pass
def lcd_show_set_alarm_ui(n): pass
def lcd_show_alarm_ringing(): pass
def lcd_show_delete_menu(): pass
def lcd_show_delete_confirm(n): pass
def render_screen(): pass

# UI message system
def show_temp_message(msg, duration_ms=1000): pass
def ui_message_expired(): pass
def clear_message_and_render_screen(): pass

# Timing checks
def initialize_alarm_start_time(): pass
def initialize_snooze_start_time(): pass
def check_alarm_timeout(): pass
def check_snooze_timeout(): pass

# Confirmation blink
def reset_confirmation_blink_count(): pass
def confirmation_blink_complete(): pass
def increment_blink_count_on_off(): pass

# Sensor verification
def verify_button_debounce_and_state(): pass
def detect_gesture(): pass
def read_rfid_tag(): pass

# System control
def shutdown_all_hardware(): pass
def clear_button_pending(): pass
```
