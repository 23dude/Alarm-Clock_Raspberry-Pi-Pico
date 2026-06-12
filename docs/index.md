---
title: "FSM Alarm Clock"
description: "SYSEN 5412 Final Project — Yi-Chia Wu (yw2839)"
---

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: false, theme: 'default' });
  document.querySelectorAll('pre > code.language-mermaid').forEach((el) => {
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = el.textContent;
    el.parentElement.replaceWith(div);
  });
  await mermaid.run({ querySelector: '.mermaid' });
</script>

<script type="module">
  const headings = document.querySelectorAll('.main-content h2');
  if (headings.length) {
    const nav = document.createElement('nav');
    nav.className = 'top-nav';
    const inner = document.createElement('div');
    inner.className = 'top-nav-inner';
    nav.appendChild(inner);

    const brand = document.createElement('a');
    brand.className = 'top-nav-brand';
    brand.href = '#';
    brand.textContent = 'FSM Clock';
    inner.appendChild(brand);

    const items = [];
    headings.forEach((h) => {
      if (!h.id) h.id = h.textContent.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      const link = document.createElement('a');
      link.href = `#${h.id}`;
      link.textContent = h.textContent;
      link.className = 'top-nav-item';
      inner.appendChild(link);
      items.push(link);
    });

    document.body.insertBefore(nav, document.body.firstChild);

    function setActive(id) {
      items.forEach((l) => l.classList.toggle('active', l.getAttribute('href') === `#${id}`));
    }
    inner.addEventListener('click', (e) => {
      const link = e.target.closest('.top-nav-item');
      if (link) setActive(link.getAttribute('href').slice(1));
    });
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting);
      if (!visible.length) return;
      const topMost = visible.reduce((a, b) => a.boundingClientRect.top < b.boundingClientRect.top ? a : b);
      setActive(topMost.target.id);
    }, { rootMargin: '-10% 0px -75% 0px', threshold: 0 });
    headings.forEach((h) => observer.observe(h));
  }
</script>

# FSM Alarm Clock

## Introduction

An FSM-based smart alarm clock built on the **Raspberry Pi Pico** (MicroPython). Users set times and alarms via an IR remote; the alarm is stopped by waving a hand in front of an ultrasonic sensor or snoozed with a physical button. Scanning an RFID card shifts the displayed time by +13 hours. A WS2812 LED strip provides visual feedback for alarm status throughout.

**Features at a glance:**

- Two independent alarms with enable/disable toggle
- Three stop mechanisms: **gesture** (ultrasonic wave-off), **snooze button** (30 s delay), **60 s auto-timeout**
- RFID card → +13-hour time shift
- IR remote full control (set time, set alarm, delete alarm, power off)
- Non-blocking UI: all messages are timer-driven; no `time.sleep()` in the main loop

**Key concepts applied:**

- ISR flag-set architecture — all handlers are non-blocking; main loop polls flags
- Top-level FSM + nested Sub-FSM for alarm sequence management
- Hardware EMI mitigation: PULL_UP + 50 ms debounce + double-check pin verification
- Single-source timer discipline: hardware timer is the only cadence authority

## Demo Video

<div class="video-short">
  <div class="video-short-inner">
    <iframe
      src="https://www.youtube.com/embed/g99llM1LRGQ"
      title="FSM Alarm Clock Demo"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowfullscreen>
    </iframe>
  </div>
</div>

## System Overview

The system uses five ISRs that set atomic flags, and a main event loop that processes them in priority order. No ISR ever blocks or writes to hardware.

**ISR sources:**

| ISR | Trigger | Flag set |
|-----|---------|----------|
| `ir_callback` | NEC_8 IR decode complete | `ir_pending` + `last_ir_value` |
| `button_isr` | GP14 falling edge (ALARM_ACTIVE only) | `button_pending` |
| `timer_isr` | Timer1, 1 Hz periodic | `timer_pending` |
| `gesture_check_isr` | Timer2, 1 Hz periodic | `gesture_pending` |
| `rfid_poll_isr` | Timer3, 700 ms periodic | `rfid_pending` |

**Main loop event priority** (processed top-to-bottom each 5 ms cycle):

1. IR remote events
2. Snooze button (debounce + pin state re-check before acting)
3. Timer tick (time display, alarm cadence, confirmation blink)
4. Gesture sensor — HC-SR04 polled only during `ALARM_ACTIVE`
5. RFID reader — non-blocking poll only during `TIME_DISPLAY`

```mermaid
flowchart TB
    subgraph ISR_BOX["ISRs — flag-set only"]
        direction LR
        I1["IR callback"]
        I2["Button ISR<br/>(GP14, PULL_UP)"]
        I3["Timer1 1Hz"]
        I4["Timer2 1Hz"]
        I5["Timer3 700ms"]
    end

    subgraph FLAGS["Atomic flags"]
        direction LR
        F1[ir_pending]
        F2[button_pending]
        F3[timer_pending]
        F4[gesture_pending]
        F5[rfid_pending]
    end

    I1 --> F1
    I2 --> F2
    I3 --> F3
    I4 --> F4
    I5 --> F5

    LOOP["Main loop<br/>poll flags → mode_handle_event()"]

    F1 --> LOOP
    F2 --> LOOP
    F3 --> LOOP
    F4 --> LOOP
    F5 --> LOOP

    subgraph SENSORS["Sensors (polled in loop)"]
        direction LR
        S1["HC-SR04<br/>(ALARM_ACTIVE only)"]
        S2["MFRC522 RFID<br/>(TIME_DISPLAY only)"]
    end

    LOOP --> S1
    LOOP --> S2

    subgraph OUT["Hardware Outputs"]
        direction LR
        O1["LCD1602"]
        O2["WS2812 LEDs"]
        O3["Buzzer PWM"]
    end

    LOOP --> O1
    LOOP --> O2
    LOOP --> O3
```

## Hardware

| Component | Pin(s) | Protocol | Notes |
|-----------|--------|----------|-------|
| **LCD1602** | SDA=GP4, SCL=GP5 | I2C0 | Address 0x27; 16-char padding prevents residue |
| **IR Receiver** | GP13 | NEC_8 via ISR | Decodes 0x45–0x4A key codes |
| **RFID MFRC522** | SCK=GP18, MOSI=GP19, MISO=GP16, CS=GP17, RST=GP9 | SPI0 | Non-blocking `rfid_read_no_block()` |
| **HC-SR04 Ultrasonic** | TRIG=GP11, ECHO=GP12 | GPIO | 5 consecutive reads < 8 cm = gesture stop |
| **WS2812 LED Strip** | GP0 | One-wire | Index 0 = Alarm 1 status; Index 1 = Alarm 2 status |
| **Buzzer** | GP15 | PWM 2 kHz | Toggled by state flags; never driven inside ISR |
| **Snooze Button** | GP14 | GPIO PULL_UP | `IRQ_FALLING`; 50 ms debounce + pin re-read in main loop |

## FSM Design

The system uses a **two-layer FSM**: a top-level FSM handles 7 modes; when the system enters `ALARM_ACTIVE` all events are delegated to an alarm Sub-FSM with 3 internal sub-modes.

### Top-Level FSM

| Mode | LCD shows | Entry from | Exits to |
|------|-----------|------------|----------|
| `TIME_DISPLAY` | `HH:MM:SS AM/PM` | startup / any mode | SET_TIME, SET_ALARM_x, DELETE, ALARM_ACTIVE |
| `SET_TIME` | `Set Time (HHMM)` | IR MODE | TIME_DISPLAY (confirm/cancel) |
| `SET_ALARM_1` | `Set Alarm 1` | IR 1 (no alarm) | TIME_DISPLAY (confirm/cancel) |
| `SET_ALARM_2` | `Set Alarm 2` | IR 2 (no alarm) | TIME_DISPLAY (confirm/cancel) |
| `DELETE_ALARM_SELECTION` | `Delete Alarm` | IR MUTE | DELETE_CONFIRM / TIME_DISPLAY |
| `DELETE_CONFIRM` | `Delete Alarm X?` | SELECT 1 or 2 | TIME_DISPLAY (confirm/cancel) |
| `ALARM_ACTIVE` | Sub-FSM controls | alarm time match | TIME_DISPLAY (alarm finished) |

```mermaid
stateDiagram-v2
    [*] --> TIME_DISPLAY
    TIME_DISPLAY --> SET_TIME : IR MODE
    TIME_DISPLAY --> SET_ALARM_1 : IR 1 (alarm1 absent)
    TIME_DISPLAY --> SET_ALARM_2 : IR 2 (alarm2 absent)
    TIME_DISPLAY --> DELETE_ALARM_SELECTION : IR MUTE
    TIME_DISPLAY --> ALARM_ACTIVE : RTC matches alarm
    SET_TIME --> TIME_DISPLAY : confirm / cancel
    SET_ALARM_1 --> TIME_DISPLAY : confirm / cancel
    SET_ALARM_2 --> TIME_DISPLAY : confirm / cancel
    DELETE_ALARM_SELECTION --> DELETE_CONFIRM : IR 1 or 2
    DELETE_ALARM_SELECTION --> TIME_DISPLAY : IR MODE
    DELETE_CONFIRM --> TIME_DISPLAY : confirm / cancel
    ALARM_ACTIVE --> TIME_DISPLAY : alarm sequence done
```

### Alarm Sub-FSM (inside `ALARM_ACTIVE`)

| Sub-mode | Behavior | Exit condition |
|----------|----------|----------------|
| `ALARM_RINGING` | LED red blink + buzzer at 1 Hz | snooze button → SNOOZE; gesture → CONFIRMATION; 60 s → exit |
| `SNOOZE` | Silent, LCD shows current time | 30 s elapsed → resume ALARM_RINGING; gesture → CONFIRMATION |
| `CONFIRMATION` | LED white blink × 3, then green | 3 cycles complete → exit to TIME_DISPLAY |

```mermaid
stateDiagram-v2
    [*] --> ALARM_RINGING
    ALARM_RINGING --> SNOOZE : snooze button pressed
    ALARM_RINGING --> CONFIRMATION : gesture detected
    ALARM_RINGING --> [*] : 60 s timeout
    SNOOZE --> ALARM_RINGING : 30 s elapsed
    SNOOZE --> CONFIRMATION : gesture detected
    CONFIRMATION --> [*] : 3 blinks complete
```

## Key Challenges

### 1. Buzzer EMI Triggering False Snooze Presses

With the snooze button configured as `PULL_DOWN`, the input pin floated near 1.5 V when idle — well within the noise margin of the 2 kHz buzzer PWM. Random false `IRQ_FALLING` edges fired during every alarm.

**Fix:** Switched to `PULL_UP` (pin held at stable 3.3 V; button grounds it). Raised debounce from 10 ms → 50 ms. Added a double-check: ISR sets flag, main loop **re-reads the pin** before acting — if the pin already returned high it was a transient, not a real press.

### 2. LCD Residue and Alarm Flicker

Variable-length strings left stale characters on the display. Calling `lcd.clear()` before every update caused a visible flash at 1 Hz.

**Fix:** All strings padded to exactly 16 chars. `lcd.clear()` removed from the per-tick path; lines are updated in place with `lcd.write(col, row, padded_string)`.

### 3. Snooze Message Instantly Overwritten

"Snoozed 30 sec" appeared for less than one frame before the alarm render path overwrote it.

**Fix:** Centralized `show_temp_message(msg, duration_ms)` stores a deadline timestamp. Every `EV_TIMER_TICK` handler checks the deadline first; if the message is still live, the normal screen render is skipped until it expires.

### 4. Buzzer/LED Rhythm Drift (Dual Timing Layers)

An extra `time.ticks_diff()` gate inside the alarm tick handler was intended to blink at 500 ms, but the hardware timer fired at 1000 ms. The two clocks drifted under main-loop load, causing occasional skipped beats.

**Fix:** Removed the software gate entirely. The 1 Hz hardware timer is the sole cadence authority — every `EV_TIMER_TICK` toggles the flags directly. No secondary timing math needed.

### 5. Silent/Dark First Beat After Snooze Resume

On snooze timeout the alarm resumed, but `alarm_led_on` and `alarm_buzzer_on` flags retained their last-toggled values — sometimes both `False` — so the first second was silent and dark.

**Fix:** On every entry into `ALARM_RINGING` (initial trigger or snooze resume), both flags are explicitly set to `True` and `update_alarm_outputs()` is called before the tick loop begins.

## What I Learned

- **Hardware EMI looks like software bugs.** Random false triggers initially seemed like debounce logic errors; the root cause was inadequate pin configuration. Measure before writing workarounds.
- **One timing authority only.** Nesting a software `ticks_diff()` check inside a hardware-timer callback introduces a redundant clock that drifts. Let the hardware timer be the sole source of truth.
- **State flags separate logic from hardware.** Splitting `alarm_led_on` / `alarm_buzzer_on` flags from the `update_alarm_outputs()` hardware call made FSM transitions testable independent of the physical outputs.
- **Non-blocking UI is non-negotiable on a single-threaded MCU.** Any `time.sleep()` in the event loop freezes all other inputs. The temp-message system with a timestamp deadline was the key to eliminating all blocking delays.
