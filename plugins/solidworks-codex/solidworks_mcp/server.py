from __future__ import annotations

import atexit
from typing import Literal

from mcp.server import MCPServer

from .bridge import SolidWorksBridge


server = MCPServer(
    "solidworks-codex",
    instructions=(
        "Controls the locally installed SolidWorks application. All geometry lengths passed to tools "
        "are in millimeters unless a unit is specified. Each tool call is executed visibly in SolidWorks. "
        "Build one feature at a time, use the feature tree and rebuild/mass-property inspection to verify "
        "geometry, use component tools only in an assembly, and save or export only to explicit paths."
    ),
)
bridge = SolidWorksBridge()
atexit.register(bridge.close)


@server.tool()
def sw_status() -> dict:
    """Read the SolidWorks version and active document without launching SolidWorks."""
    return bridge.status()


@server.tool()
def sw_ensure_ready(instance_pid: int | None = None) -> dict:
    """Attach to one selected SolidWorks process, or launch a visible instance if none is running."""
    return bridge.ensure_ready(instance_pid)


@server.tool()
def sw_new_part() -> dict:
    """Create a new part using SolidWorks' configured default part template."""
    return bridge.new_document("part")


@server.tool()
def sw_new_assembly() -> dict:
    """Create a blank assembly using SolidWorks' configured default assembly template."""
    return bridge.new_document("assembly")


@server.tool()
def sw_new_drawing() -> dict:
    """Create a drawing using SolidWorks' configured default drawing template."""
    return bridge.new_document("drawing")


@server.tool()
def sw_open_document(path: str) -> dict:
    """Open a native .SLDPRT, .SLDASM, or .SLDDRW from an absolute path."""
    return bridge.open_document(path)


@server.tool()
def sw_list_open_documents() -> dict:
    """List open SolidWorks documents, their types, paths, and the active document."""
    return bridge.list_open_documents()


@server.tool()
def sw_start_sketch(plane: str = "Front") -> dict:
    """Start a sketch on Front, Top, Right, or an exact reference-plane name from the feature tree."""
    return bridge.start_sketch(plane)


@server.tool()
def sw_start_sketch_on_selected_face() -> dict:
    """Start a part sketch on the single model face currently selected in SolidWorks."""
    return bridge.start_sketch_on_selected_face()


@server.tool()
def sw_sketch_line(
    x1: float, y1: float, x2: float, y2: float, unit: Literal["mm", "cm", "m", "in", "ft"] = "mm"
) -> dict:
    """Draw one line in the active sketch. Lengths default to millimeters."""
    return bridge.draw_line(x1, y1, x2, y2, unit)


@server.tool()
def sw_sketch_rectangle(
    x1: float, y1: float, x2: float, y2: float, unit: Literal["mm", "cm", "m", "in", "ft"] = "mm"
) -> dict:
    """Draw a corner rectangle in the active sketch. Lengths default to millimeters."""
    return bridge.draw_rectangle(x1, y1, x2, y2, unit)


@server.tool()
def sw_sketch_circle(
    cx: float,
    cy: float,
    radius: float,
    unit: Literal["mm", "cm", "m", "in", "ft"] = "mm",
) -> dict:
    """Draw a circle by center and radius. Lengths default to millimeters."""
    return bridge.draw_circle(cx, cy, radius, unit)


@server.tool()
def sw_sketch_arc(
    x1: float,
    y1: float,
    xm: float,
    ym: float,
    x2: float,
    y2: float,
    unit: Literal["mm", "cm", "m", "in", "ft"] = "mm",
) -> dict:
    """Draw an arc through start, midpoint, and end coordinates. Lengths default to millimeters."""
    return bridge.draw_arc(x1, y1, xm, ym, x2, y2, unit)


@server.tool()
def sw_sketch_polygon(
    cx: float,
    cy: float,
    radius: float,
    sides: int,
    unit: Literal["mm", "cm", "m", "in", "ft"] = "mm",
) -> dict:
    """Draw a closed regular polygon from its center, circumradius, and side count (3–100)."""
    return bridge.draw_polygon(cx, cy, radius, sides, unit)


@server.tool()
def sw_finish_sketch() -> dict:
    """Close and rebuild the active sketch; returns its exact feature-tree name."""
    return bridge.finish_sketch()


@server.tool()
def sw_extrude(
    sketch_name: str,
    depth: float,
    direction: Literal["forward", "backward", "both"] = "forward",
    unit: Literal["mm", "cm", "m", "in", "ft"] = "mm",
) -> dict:
    """Create a boss extrusion from an explicitly named sketch. Depth defaults to millimeters."""
    return bridge.extrude(sketch_name, depth, unit, direction)


@server.tool()
def sw_cut_extrude(
    sketch_name: str,
    depth: float = 10,
    through_all: bool = False,
    reverse_direction: bool = False,
    unit: Literal["mm", "cm", "m", "in", "ft"] = "mm",
) -> dict:
    """Create a blind or through-all cut from a named sketch, optionally reversing its normal direction."""
    return bridge.cut_extrude(sketch_name, depth, unit, through_all, reverse_direction)


@server.tool()
def sw_list_features() -> dict:
    """List the feature names and SolidWorks feature types in the active document."""
    return bridge.features()


@server.tool()
def sw_inspect_model() -> dict:
    """Read the active document, feature tree, and available mass properties without rebuilding."""
    return bridge.inspect()


@server.tool()
def sw_validate_model() -> dict:
    """Force a SolidWorks rebuild and report the feature tree and mass properties as validation evidence."""
    return bridge.validate()


@server.tool()
def sw_mass_properties() -> dict:
    """Read mass, volume, surface area, and center of mass from the active solid model."""
    return bridge.mass_properties()


@server.tool()
def sw_list_components(include_nested: bool = False) -> dict:
    """List components of the active assembly, optionally including nested subassembly components."""
    return bridge.list_components(include_nested)


@server.tool()
def sw_insert_component(
    path: str,
    x: float = 0,
    y: float = 0,
    z: float = 0,
    unit: Literal["mm", "cm", "m", "in", "ft"] = "mm",
) -> dict:
    """Insert a native part or subassembly at an explicit assembly-origin position (no mates are created)."""
    return bridge.insert_component(path, x, y, z, unit)


@server.tool()
def sw_set_view(view: Literal["isometric", "front", "top", "right"]) -> dict:
    """Set a standard view and fit the active model in the SolidWorks window."""
    return bridge.set_view(view)


@server.tool()
def sw_save(path: str = "", overwrite: bool = False) -> dict:
    """Save the active document; a new path must be absolute. Existing targets need overwrite=true."""
    return bridge.save(path or None, overwrite)


@server.tool()
def sw_export_neutral(path: str, overwrite: bool = False) -> dict:
    """Export the full active part or assembly as STEP, IGES, or STL to an absolute path."""
    return bridge.export_neutral(path, overwrite)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
