from code_parsing.parser import safe_parse_with_tail_drop, extract_used_filter_codes_semantic
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
code="""
if (parseInt(GreenLightSignal.co2Level.Co2LevelValue) <= 50) {
  Lifx.color.skip('CO2 level is not above 50');
} else {
  Lifx.color.setColorIfOff('#FF0000'); // Set color to red (RGB: #FF0000) if device is off
}
Lifx.color.setAdvancedOptions('duration:1s; delay:0s');
"""
parsed_dict, cleaned, err = safe_parse_with_tail_drop(code)

true_getters, used_namespaces, used_setters, outcomes = extract_used_filter_codes_semantic(parsed_dict)

print(true_getters, used_setters)