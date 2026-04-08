use wasm_bindgen::prelude::*;

// Action codes
const ACT_NONE: u8 = 0;
const ACT_SALT: u8 = 1;
const ACT_OPEN: u8 = 2;
const ACT_CLEANUP: u8 = 9;

// Secret constants (hidden in WASM binary)
const REQUIRED_TAPS: u8 = 6;
const TAP_WINDOW_MS: f64 = 5000.0;
const TIMEOUT_MS: f64 = 6000.0;
const SALT_PATH: &str = "/api/v1/salt?fp=";

#[wasm_bindgen]
pub struct Stealth {
    tap_count: u8,
    last_tap_time: f64,
    load_time: f64,
    salt_verified: bool,
    active: bool,
    timed_out: bool,
}

#[wasm_bindgen]
impl Stealth {
    #[wasm_bindgen(constructor)]
    pub fn new(now: f64) -> Stealth {
        Stealth {
            tap_count: 0,
            last_tap_time: 0.0,
            load_time: now,
            salt_verified: false,
            active: false,
            timed_out: false,
        }
    }

    pub fn on_salt_result(&mut self, success: u8) {
        if success == 1 {
            self.salt_verified = true;
            self.active = true;
        }
    }

    pub fn on_tap(&mut self, now: f64) -> u8 {
        if !self.active || self.timed_out {
            return ACT_NONE;
        }

        if now - self.load_time >= TIMEOUT_MS {
            self.timed_out = true;
            self.active = false;
            return ACT_CLEANUP;
        }

        if self.last_tap_time > 0.0 && (now - self.last_tap_time) >= TAP_WINDOW_MS {
            self.tap_count = 0;
        }

        self.last_tap_time = now;
        self.tap_count += 1;

        if self.tap_count >= REQUIRED_TAPS {
            self.tap_count = 0;
            self.active = false;
            return ACT_OPEN;
        }

        ACT_NONE
    }

    pub fn check_timeout(&mut self, now: f64) -> u8 {
        if self.timed_out {
            return ACT_NONE;
        }
        if self.active && (now - self.load_time >= TIMEOUT_MS) {
            self.timed_out = true;
            self.active = false;
            return ACT_CLEANUP;
        }
        ACT_NONE
    }

    pub fn salt_path(&self) -> String {
        String::from(SALT_PATH)
    }

    pub fn init_action(&self) -> u8 {
        ACT_SALT
    }
}
