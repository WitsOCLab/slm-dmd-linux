"""Put a blazed grating on the SLM found by its EDID name, and report when it was on the panel."""
from slmscreen import Display, find_output, patterns

output = find_output(edid_name="HE PLUTO-2.1")            # `python -m slmscreen` lists the connected outputs and their EDID names
with Display("slm", output) as slm:
    frame = patterns.render("blazed", output.width, output.height, period_px=16, angle_deg=45)
    info = slm.show(frame)
    print("shown on", output.connector, "at vsync", info)
