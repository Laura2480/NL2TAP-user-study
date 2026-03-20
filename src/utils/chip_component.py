"""G1 chip selector — Streamlit custom component.

declare_component must be called from a real Python module
(not a Streamlit page script executed via exec).
"""
import os
import streamlit.components.v1 as components

_CHIP_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "evaluation", "components", "chip_selector",
)

chip_selector = components.declare_component(
    "chip_selector", path=os.path.abspath(_CHIP_DIR)
)

_DRAWER_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "evaluation", "components", "field_drawer",
)

field_drawer = components.declare_component(
    "field_drawer", path=os.path.abspath(_DRAWER_DIR)
)

_TUTORIAL_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "evaluation", "components", "tutorial_overlay",
)

tutorial_overlay = components.declare_component(
    "tutorial_overlay", path=os.path.abspath(_TUTORIAL_DIR)
)
