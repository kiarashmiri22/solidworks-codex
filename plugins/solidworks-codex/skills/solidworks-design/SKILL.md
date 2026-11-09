---
name: solidworks-design
description: Plan, build, and inspect a SolidWorks part through the local SolidWorks MCP tools. Use when a user asks Codex to create or change CAD geometry in SolidWorks.
---

# SolidWorks design workflow

Use the local `solidworks` MCP server to make actual changes in the visible SolidWorks application.

## Before changing geometry

1. Call `sw_status` to identify the visible SolidWorks process and its active document. If multiple instances are listed, ask which window to use and only offer instances with `registered_with_com: true`; then call `sw_ensure_ready(instance_pid=...)` with that PID. If one instance is listed, call `sw_ensure_ready` and then `sw_inspect_model`. Inspection is read-only. Do not replace or close a user's active document without an explicit request.
2. Extract the dimensions, units, material, tolerances, and intended outputs from the request. Dimensions that control shape must be explicit; ask one concise question when a missing value changes the geometry or safe use. Never invent engineering dimensions or claim manufacturability without evidence.
3. State a short feature plan and build one feature at a time. The user should be able to watch each sketch, rebuild, and feature appear in SolidWorks.
4. Use millimeters by default. Every modeling tool accepts an explicit unit; SolidWorks COM uses meters internally and the bridge converts values.

## Build a part

1. If the user requested a new part, call `sw_new_part`; otherwise keep working in the active part.
2. Call `sw_start_sketch` with a plane name. For a localized or custom plane, call `sw_list_features` and use its exact reference-plane name.
3. Draw with `sw_sketch_line`, `sw_sketch_rectangle`, `sw_sketch_circle`, or `sw_sketch_arc`. Each call updates the SolidWorks view.
4. Call `sw_finish_sketch` and use the returned exact sketch name in the next feature call.
5. Create solids with `sw_extrude` or `sw_cut_extrude`. Do not rely on “latest sketch” guesses.
6. Call `sw_validate_model` after the feature. Report rebuild status, feature-tree evidence, and measured mass properties when available. A screenshot or plausible shape does not establish dimensional correctness.
7. Save only to a path the user specified or accepted. Never overwrite an existing file unless the user explicitly requested replacement; pass `overwrite=true` only then.

If a SolidWorks operation fails, stop and report the exact error and current model state before trying a different API sequence. Do not claim the part is complete until the rebuild succeeds and the feature tree matches the plan.
