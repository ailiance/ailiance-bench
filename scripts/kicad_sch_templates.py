#!/usr/bin/env python3
"""
Hand-crafted KiCad 6/10 .kicad_sch templates et leurs prompts/ground truth.

Sert de seed dataset pour bench_kicad_phase2.py (generation prompt -> sch)
et bench_kicad_phase3.py (extraction sch -> JSON composants/nets).

Chaque entree :
  prompt          : description textuelle du circuit (input modele)
  sch             : contenu .kicad_sch S-expression (KiCad 6/10) reference
  ground_truth    : {components: [{ref, value, footprint}], nets: [{name, pins}]}

Tous les .kicad_sch sont volontairement simplifies (sans uuid complets, sans
positionnements precis) — ils restent parsables par notre parser Python pur
et representent la topologie minimale. KiCad 10 accepterait ces fichiers
apres ouverture+sauvegarde, mais ils ne passeraient pas un kicad-cli erc
strict — ce qui est ok pour un bench fonctionnel structurel.
"""
from __future__ import annotations


# Helpers pour generer des blocs symbol minimaux mais syntaxiquement valides
def _mksym(ref: str, value: str, footprint: str = "", lib: str = "Device") -> str:
    return f'''  (symbol
    (lib_id "{lib}:{value if lib == "Device" else value}")
    (at 50 50 0)
    (uuid "00000000-0000-0000-0000-{ref:0>12}")
    (property "Reference" "{ref}" (at 50 45 0))
    (property "Value" "{value}" (at 50 55 0))
    (property "Footprint" "{footprint}" (at 50 50 0))
  )'''


def _mklabel(name: str) -> str:
    return f'  (label "{name}" (at 60 60 0))'


# ---------------------------------------------------------------------------
# Template 1 : LED blinker (R + LED + power)
# ---------------------------------------------------------------------------
TPL_LED = {
    "id": "led_blinker",
    "prompt": (
        "Generate a KiCad 10 schematic (S-expression format) for a simple "
        "LED indicator circuit: a 5V power source, a 330 ohm current-limiting "
        "resistor R1, and a red LED D1 to ground. Use Device:R for the resistor "
        "and Device:LED for the LED. Add labels VCC and GND for the power rails."
    ),
    "sch": '''(kicad_sch
  (version 20250114)
  (generator "hand")
  (uuid "10000000-0000-0000-0000-000000000001")
  (paper "A4")
  (title_block (title "LED Blinker"))
  (lib_symbols
    (symbol "Device:R" (property "Reference" "R" (at 0 0 0)) (property "Value" "R" (at 0 0 0)))
    (symbol "Device:LED" (property "Reference" "D" (at 0 0 0)) (property "Value" "LED" (at 0 0 0)))
  )
  (symbol
    (lib_id "Device:R")
    (at 80 60 0)
    (uuid "10000000-0000-0000-0000-000000000R01")
    (property "Reference" "R1" (at 80 55 0))
    (property "Value" "330" (at 80 65 0))
    (property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 80 60 0))
  )
  (symbol
    (lib_id "Device:LED")
    (at 80 80 0)
    (uuid "10000000-0000-0000-0000-000000000D01")
    (property "Reference" "D1" (at 80 75 0))
    (property "Value" "LED_Red" (at 80 85 0))
    (property "Footprint" "LED_SMD:LED_0805_2012Metric" (at 80 80 0))
  )
  (label "VCC" (at 80 50 0))
  (label "MID" (at 80 70 0))
  (label "GND" (at 80 90 0))
)''',
    "ground_truth": {
        "components": [
            {"ref": "R1", "value": "330", "footprint": "Resistor_SMD:R_0805_2012Metric"},
            {"ref": "D1", "value": "LED_Red", "footprint": "LED_SMD:LED_0805_2012Metric"},
        ],
        "nets": [
            {"name": "VCC", "pins": ["R1.1"]},
            {"name": "MID", "pins": ["R1.2", "D1.1"]},
            {"name": "GND", "pins": ["D1.2"]},
        ],
    },
}

# ---------------------------------------------------------------------------
# Template 2 : Voltage divider (2 resistors)
# ---------------------------------------------------------------------------
TPL_VDIV = {
    "id": "voltage_divider",
    "prompt": (
        "Generate a KiCad 10 schematic for a 2:1 resistive voltage divider: "
        "VIN at the top, two equal 10k resistors R1 (top) and R2 (bottom) in "
        "series, with the midpoint labelled VOUT and the bottom tied to GND. "
        "Use Device:R for the resistors."
    ),
    "sch": '''(kicad_sch
  (version 20250114)
  (generator "hand")
  (uuid "20000000-0000-0000-0000-000000000001")
  (paper "A4")
  (title_block (title "Voltage Divider"))
  (lib_symbols
    (symbol "Device:R" (property "Reference" "R" (at 0 0 0)) (property "Value" "R" (at 0 0 0)))
  )
  (symbol
    (lib_id "Device:R")
    (at 100 60 0)
    (uuid "20000000-0000-0000-0000-000000000R01")
    (property "Reference" "R1" (at 100 55 0))
    (property "Value" "10k" (at 100 65 0))
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 100 60 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 100 80 0)
    (uuid "20000000-0000-0000-0000-000000000R02")
    (property "Reference" "R2" (at 100 75 0))
    (property "Value" "10k" (at 100 85 0))
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 100 80 0))
  )
  (label "VIN" (at 100 50 0))
  (label "VOUT" (at 100 70 0))
  (label "GND" (at 100 90 0))
)''',
    "ground_truth": {
        "components": [
            {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0603_1608Metric"},
            {"ref": "R2", "value": "10k", "footprint": "Resistor_SMD:R_0603_1608Metric"},
        ],
        "nets": [
            {"name": "VIN", "pins": ["R1.1"]},
            {"name": "VOUT", "pins": ["R1.2", "R2.1"]},
            {"name": "GND", "pins": ["R2.2"]},
        ],
    },
}

# ---------------------------------------------------------------------------
# Template 3 : 555 astable timer
# ---------------------------------------------------------------------------
TPL_555 = {
    "id": "ne555_astable",
    "prompt": (
        "Generate a KiCad 10 schematic for a classic NE555 astable multivibrator: "
        "U1 is the NE555, R1 (10k) between VCC and pin 7 (DIS), R2 (47k) between "
        "pin 7 and pin 6 (THR), C1 (10nF) between pin 6 and GND, and pin 6 also "
        "tied to pin 2 (TRIG). Pin 8 (VCC) and pin 4 (RST) tied to VCC, pin 1 "
        "to GND, output is pin 3."
    ),
    "sch": '''(kicad_sch
  (version 20250114)
  (generator "hand")
  (uuid "30000000-0000-0000-0000-000000000001")
  (paper "A4")
  (title_block (title "NE555 Astable"))
  (lib_symbols
    (symbol "Timer:NE555" (property "Reference" "U" (at 0 0 0)) (property "Value" "NE555" (at 0 0 0)))
    (symbol "Device:R" (property "Reference" "R" (at 0 0 0)) (property "Value" "R" (at 0 0 0)))
    (symbol "Device:C" (property "Reference" "C" (at 0 0 0)) (property "Value" "C" (at 0 0 0)))
  )
  (symbol
    (lib_id "Timer:NE555")
    (at 120 80 0)
    (uuid "30000000-0000-0000-0000-000000000U01")
    (property "Reference" "U1" (at 120 70 0))
    (property "Value" "NE555" (at 120 90 0))
    (property "Footprint" "Package_DIP:DIP-8_W7.62mm" (at 120 80 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 100 50 0)
    (uuid "30000000-0000-0000-0000-000000000R01")
    (property "Reference" "R1" (at 100 45 0))
    (property "Value" "10k" (at 100 55 0))
    (property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 100 50 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 100 70 0)
    (uuid "30000000-0000-0000-0000-000000000R02")
    (property "Reference" "R2" (at 100 65 0))
    (property "Value" "47k" (at 100 75 0))
    (property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 100 70 0))
  )
  (symbol
    (lib_id "Device:C")
    (at 100 90 0)
    (uuid "30000000-0000-0000-0000-000000000C01")
    (property "Reference" "C1" (at 100 85 0))
    (property "Value" "10nF" (at 100 95 0))
    (property "Footprint" "Capacitor_SMD:C_0603_1608Metric" (at 100 90 0))
  )
  (label "VCC" (at 100 40 0))
  (label "DIS" (at 100 60 0))
  (label "THR" (at 100 80 0))
  (label "OUT" (at 140 80 0))
  (label "GND" (at 100 100 0))
)''',
    "ground_truth": {
        "components": [
            {"ref": "U1", "value": "NE555", "footprint": "Package_DIP:DIP-8_W7.62mm"},
            {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0805_2012Metric"},
            {"ref": "R2", "value": "47k", "footprint": "Resistor_SMD:R_0805_2012Metric"},
            {"ref": "C1", "value": "10nF", "footprint": "Capacitor_SMD:C_0603_1608Metric"},
        ],
        "nets": [
            {"name": "VCC", "pins": ["R1.1", "U1.8", "U1.4"]},
            {"name": "DIS", "pins": ["R1.2", "R2.1", "U1.7"]},
            {"name": "THR", "pins": ["R2.2", "C1.1", "U1.6", "U1.2"]},
            {"name": "OUT", "pins": ["U1.3"]},
            {"name": "GND", "pins": ["C1.2", "U1.1"]},
        ],
    },
}

# ---------------------------------------------------------------------------
# Template 4 : Op-amp non-inverting amplifier (gain ~11)
# ---------------------------------------------------------------------------
TPL_OPAMP = {
    "id": "opamp_noninv",
    "prompt": (
        "Generate a KiCad 10 schematic for a non-inverting op-amp amplifier: "
        "U1 is a TL072 (single-supply OK), input VIN goes to the +input pin 3, "
        "output is pin 1 labelled VOUT. R1 (1k) is the feedback resistor "
        "between VOUT and pin 2 (-input), R2 (100 ohm) ties pin 2 to GND. "
        "Power on pin 8 (V+) tied to VCC, pin 4 (V-) tied to GND."
    ),
    "sch": '''(kicad_sch
  (version 20250114)
  (generator "hand")
  (uuid "40000000-0000-0000-0000-000000000001")
  (paper "A4")
  (title_block (title "Op-amp Non-inverting"))
  (lib_symbols
    (symbol "Amplifier_Operational:TL072" (property "Reference" "U" (at 0 0 0)) (property "Value" "TL072" (at 0 0 0)))
    (symbol "Device:R" (property "Reference" "R" (at 0 0 0)) (property "Value" "R" (at 0 0 0)))
  )
  (symbol
    (lib_id "Amplifier_Operational:TL072")
    (at 120 80 0)
    (uuid "40000000-0000-0000-0000-000000000U01")
    (property "Reference" "U1" (at 120 70 0))
    (property "Value" "TL072" (at 120 90 0))
    (property "Footprint" "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm" (at 120 80 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 100 70 0)
    (uuid "40000000-0000-0000-0000-000000000R01")
    (property "Reference" "R1" (at 100 65 0))
    (property "Value" "1k" (at 100 75 0))
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 100 70 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 100 90 0)
    (uuid "40000000-0000-0000-0000-000000000R02")
    (property "Reference" "R2" (at 100 85 0))
    (property "Value" "100" (at 100 95 0))
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 100 90 0))
  )
  (label "VIN" (at 110 75 0))
  (label "VOUT" (at 140 80 0))
  (label "FB" (at 100 80 0))
  (label "VCC" (at 120 60 0))
  (label "GND" (at 120 100 0))
)''',
    "ground_truth": {
        "components": [
            {"ref": "U1", "value": "TL072", "footprint": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"},
            {"ref": "R1", "value": "1k", "footprint": "Resistor_SMD:R_0603_1608Metric"},
            {"ref": "R2", "value": "100", "footprint": "Resistor_SMD:R_0603_1608Metric"},
        ],
        "nets": [
            {"name": "VIN", "pins": ["U1.3"]},
            {"name": "VOUT", "pins": ["U1.1", "R1.1"]},
            {"name": "FB", "pins": ["R1.2", "R2.1", "U1.2"]},
            {"name": "VCC", "pins": ["U1.8"]},
            {"name": "GND", "pins": ["R2.2", "U1.4"]},
        ],
    },
}

# ---------------------------------------------------------------------------
# Template 5 : ESP32-S3 minimal dev module (USB-UART + LDO + ESP32 + LED)
# ---------------------------------------------------------------------------
TPL_ESP32 = {
    "id": "esp32_mini",
    "prompt": (
        "Generate a KiCad 10 schematic for a minimal ESP32-S3 dev board: "
        "U1 is an ESP32-S3-WROOM-1 module, U2 is an AMS1117-3.3 LDO regulator "
        "(input from VBUS, output 3V3, with C1 22uF input cap and C2 22uF "
        "output cap), J1 is a USB-C connector providing VBUS and D+/D-, R1 "
        "(10k) is an EN pull-up to 3V3, D1 is a status LED on GPIO2 with "
        "current-limit R2 (1k) to GND. Add labels VBUS, 3V3, GND, EN, USB_DP, "
        "USB_DM."
    ),
    "sch": '''(kicad_sch
  (version 20250114)
  (generator "hand")
  (uuid "50000000-0000-0000-0000-000000000001")
  (paper "A4")
  (title_block (title "ESP32-S3 Minimal Dev Board"))
  (lib_symbols
    (symbol "RF_Module:ESP32-S3-WROOM-1" (property "Reference" "U" (at 0 0 0)) (property "Value" "ESP32-S3-WROOM-1" (at 0 0 0)))
    (symbol "Regulator_Linear:AMS1117-3.3" (property "Reference" "U" (at 0 0 0)) (property "Value" "AMS1117-3.3" (at 0 0 0)))
    (symbol "Connector:USB_C_Receptacle_USB2.0_16P" (property "Reference" "J" (at 0 0 0)) (property "Value" "USB_C" (at 0 0 0)))
    (symbol "Device:R" (property "Reference" "R" (at 0 0 0)) (property "Value" "R" (at 0 0 0)))
    (symbol "Device:C" (property "Reference" "C" (at 0 0 0)) (property "Value" "C" (at 0 0 0)))
    (symbol "Device:LED" (property "Reference" "D" (at 0 0 0)) (property "Value" "LED" (at 0 0 0)))
  )
  (symbol
    (lib_id "RF_Module:ESP32-S3-WROOM-1")
    (at 150 100 0)
    (uuid "50000000-0000-0000-0000-000000000U01")
    (property "Reference" "U1" (at 150 90 0))
    (property "Value" "ESP32-S3-WROOM-1" (at 150 110 0))
    (property "Footprint" "RF_Module:ESP32-S2-WROOM" (at 150 100 0))
  )
  (symbol
    (lib_id "Regulator_Linear:AMS1117-3.3")
    (at 100 80 0)
    (uuid "50000000-0000-0000-0000-000000000U02")
    (property "Reference" "U2" (at 100 75 0))
    (property "Value" "AMS1117-3.3" (at 100 85 0))
    (property "Footprint" "Package_TO_SOT_SMD:SOT-223-3_TabPin2" (at 100 80 0))
  )
  (symbol
    (lib_id "Connector:USB_C_Receptacle_USB2.0_16P")
    (at 60 80 0)
    (uuid "50000000-0000-0000-0000-000000000J01")
    (property "Reference" "J1" (at 60 70 0))
    (property "Value" "USB_C" (at 60 90 0))
    (property "Footprint" "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12" (at 60 80 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 130 70 0)
    (uuid "50000000-0000-0000-0000-000000000R01")
    (property "Reference" "R1" (at 130 65 0))
    (property "Value" "10k" (at 130 75 0))
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 130 70 0))
  )
  (symbol
    (lib_id "Device:R")
    (at 180 110 0)
    (uuid "50000000-0000-0000-0000-000000000R02")
    (property "Reference" "R2" (at 180 105 0))
    (property "Value" "1k" (at 180 115 0))
    (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 180 110 0))
  )
  (symbol
    (lib_id "Device:C")
    (at 90 90 0)
    (uuid "50000000-0000-0000-0000-000000000C01")
    (property "Reference" "C1" (at 90 85 0))
    (property "Value" "22uF" (at 90 95 0))
    (property "Footprint" "Capacitor_SMD:C_0805_2012Metric" (at 90 90 0))
  )
  (symbol
    (lib_id "Device:C")
    (at 110 90 0)
    (uuid "50000000-0000-0000-0000-000000000C02")
    (property "Reference" "C2" (at 110 85 0))
    (property "Value" "22uF" (at 110 95 0))
    (property "Footprint" "Capacitor_SMD:C_0805_2012Metric" (at 110 90 0))
  )
  (symbol
    (lib_id "Device:LED")
    (at 190 110 0)
    (uuid "50000000-0000-0000-0000-000000000D01")
    (property "Reference" "D1" (at 190 105 0))
    (property "Value" "LED_Status" (at 190 115 0))
    (property "Footprint" "LED_SMD:LED_0603_1608Metric" (at 190 110 0))
  )
  (label "VBUS" (at 80 80 0))
  (label "3V3" (at 120 80 0))
  (label "GND" (at 100 100 0))
  (label "EN" (at 130 80 0))
  (label "USB_DP" (at 75 75 0))
  (label "USB_DM" (at 75 85 0))
  (label "GPIO2" (at 175 110 0))
)''',
    "ground_truth": {
        "components": [
            {"ref": "U1", "value": "ESP32-S3-WROOM-1", "footprint": "RF_Module:ESP32-S2-WROOM"},
            {"ref": "U2", "value": "AMS1117-3.3", "footprint": "Package_TO_SOT_SMD:SOT-223-3_TabPin2"},
            {"ref": "J1", "value": "USB_C", "footprint": "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12"},
            {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0603_1608Metric"},
            {"ref": "R2", "value": "1k", "footprint": "Resistor_SMD:R_0603_1608Metric"},
            {"ref": "C1", "value": "22uF", "footprint": "Capacitor_SMD:C_0805_2012Metric"},
            {"ref": "C2", "value": "22uF", "footprint": "Capacitor_SMD:C_0805_2012Metric"},
            {"ref": "D1", "value": "LED_Status", "footprint": "LED_SMD:LED_0603_1608Metric"},
        ],
        "nets": [
            {"name": "VBUS", "pins": ["J1.A4", "U2.3", "C1.1"]},
            {"name": "3V3", "pins": ["U2.2", "C2.1", "R1.1", "U1.2"]},
            {"name": "GND", "pins": ["J1.A1", "U2.1", "C1.2", "C2.2", "U1.1", "D1.2"]},
            {"name": "EN", "pins": ["R1.2", "U1.3"]},
            {"name": "USB_DP", "pins": ["J1.A6", "U1.20"]},
            {"name": "USB_DM", "pins": ["J1.A7", "U1.19"]},
            {"name": "GPIO2", "pins": ["U1.10", "R2.1"]},
        ],
    },
}

TEMPLATES = [TPL_LED, TPL_VDIV, TPL_555, TPL_OPAMP, TPL_ESP32]


# ---------------------------------------------------------------------------
# Real local schematic : SPI bus 4 devices (from hypneum-lab/micro-kiki)
# ---------------------------------------------------------------------------
def load_spi_bus_template() -> dict:
    """Load the real local schematic and infer ground truth via ad-hoc parse."""
    import pathlib
    p = pathlib.Path.home() / "eu-kiki-data" / "kicad-sch-refs" / "spi_bus_4devices.kicad_sch"
    if not p.exists():
        return None
    sch = p.read_text()
    return {
        "id": "spi_bus_4devices",
        "prompt": (
            "Generate a KiCad 10 schematic for an SPI bus expansion board: "
            "J1 is a 4-CS SPI host header (SCLK, MOSI, MISO, CS1..CS4, VCC, GND), "
            "U1 through U4 are four generic SPI peripheral devices each on its "
            "own chip-select line CS1..CS4, sharing SCLK/MOSI/MISO/VCC/GND. "
            "Add 10k pull-up resistors R1..R4 from VCC to each CS line so all "
            "slaves stay deselected during reset."
        ),
        "sch": sch,
        "ground_truth": {
            "components": [
                {"ref": "J1", "value": "SPI_HOST_4CS", "footprint": ""},
                {"ref": "U1", "value": "SPI_DEVICE", "footprint": ""},
                {"ref": "U2", "value": "SPI_DEVICE", "footprint": ""},
                {"ref": "U3", "value": "SPI_DEVICE", "footprint": ""},
                {"ref": "U4", "value": "SPI_DEVICE", "footprint": ""},
                {"ref": "R1", "value": "10k", "footprint": ""},
                {"ref": "R2", "value": "10k", "footprint": ""},
                {"ref": "R3", "value": "10k", "footprint": ""},
                {"ref": "R4", "value": "10k", "footprint": ""},
            ],
            "nets": [
                {"name": "SPI_SCLK", "pins": []},
                {"name": "SPI_MOSI", "pins": []},
                {"name": "SPI_MISO", "pins": []},
                {"name": "SPI_CS1", "pins": []},
                {"name": "SPI_CS2", "pins": []},
                {"name": "SPI_CS3", "pins": []},
                {"name": "SPI_CS4", "pins": []},
                {"name": "VCC", "pins": []},
                {"name": "GND", "pins": []},
            ],
        },
    }


def all_templates() -> list[dict]:
    out = list(TEMPLATES)
    spi = load_spi_bus_template()
    if spi is not None:
        out.append(spi)
    return out


if __name__ == "__main__":
    import json
    for t in all_templates():
        print(f"== {t['id']} ==")
        print(f"  prompt[:80]: {t['prompt'][:80]}")
        print(f"  sch chars  : {len(t['sch'])}")
        print(f"  components : {len(t['ground_truth']['components'])}")
        print(f"  nets       : {len(t['ground_truth']['nets'])}")
