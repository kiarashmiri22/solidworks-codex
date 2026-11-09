from __future__ import annotations

import math
import os
import queue
import csv
import re
import subprocess
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from .units import positive_meters, to_meters


class StaExecutor:
    """Own all SolidWorks COM objects on one serialized STA thread."""

    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[Future[Any], Callable[..., Any], tuple[Any, ...]] | None] = queue.Queue()
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="SolidWorks-COM-STA", daemon=True)
        self._thread.start()
        if not self._ready.wait(15):
            raise RuntimeError("SolidWorks COM thread did not start within 15 seconds.")
        if self._startup_error:
            raise RuntimeError(f"Could not initialize the SolidWorks COM thread: {self._startup_error}")

    def _run(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            self._pythoncom = pythoncom
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    break
                future, function, args = job
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function(*args))
                    except BaseException as exc:
                        future.set_exception(exc)
                self._pythoncom.PumpWaitingMessages()
        finally:
            self._pythoncom.CoUninitialize()

    def call(self, function: Callable[..., Any], *args: Any) -> Any:
        future: Future[Any] = Future()
        self._jobs.put((future, function, args))
        return future.result()

    def close(self) -> None:
        self._jobs.put(None)
        self._thread.join(timeout=5)


class SolidWorksBridge:
    _TYPELIB_ID = "{83A33D31-27C5-11CE-BFD4-00400513BB57}"

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("SolidWorks automation is available only on Windows.")
        self._sta = StaExecutor()
        self._app: Any = None
        self._app_pid: int | None = None
        self._selected_pid: int | None = None
        self._sw_module: Any = None
        self._sketch_names_before: set[str] | None = None

    def close(self) -> None:
        self._sta.close()

    def _solidworks_processes(self) -> list[dict[str, Any]]:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["tasklist", "/nh", "/fo", "csv", "/v", "/fi", "imagename eq SLDWORKS.exe"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=flags,
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Could not inspect running SOLIDWORKS processes; refusing to start or select an ambiguous instance."
            )
        return [
            {"pid": int(row[1]), "window_title": row[8] if len(row) > 8 else None}
            for row in csv.reader(result.stdout.splitlines())
            if len(row) >= 2 and row[0].casefold() == "sldworks.exe" and row[1].isdigit()
        ]

    def _solidworks_process_ids(self) -> list[int]:
        return [process["pid"] for process in self._solidworks_processes()]

    def _registered_instances(self) -> dict[int, dict[str, Any]]:
        import pythoncom
        import win32com.client

        instances: dict[int, dict[str, Any]] = {}
        rot = pythoncom.GetRunningObjectTable()
        enum = rot.EnumRunning()
        context = pythoncom.CreateBindCtx(0)
        while True:
            entries = enum.Next(1)
            if not entries:
                break
            moniker = entries[0]
            try:
                name = moniker.GetDisplayName(context, None)
                match = re.fullmatch(r"SolidWorks_PID_(\d+)", name, re.IGNORECASE)
                if not match:
                    continue
                pid = int(match.group(1))
                unknown = rot.GetObject(moniker)
                dispatch = unknown.QueryInterface(pythoncom.IID_IDispatch)
                app = win32com.client.Dispatch(dispatch)
                doc = app.ActiveDoc
                instances[pid] = {
                    "app": app,
                    "version": str(self._value(app, "RevisionNumber")),
                    "visible": bool(app.Visible),
                    "active_document": str(self._value(doc, "GetTitle")) if doc is not None else None,
                }
            except Exception:
                continue
        return instances

    def _connect(self, launch: bool) -> Any:
        import win32com.client

        process_ids = self._solidworks_process_ids()
        if self._selected_pid is not None:
            if self._selected_pid not in process_ids:
                raise RuntimeError(
                    f"Selected SOLIDWORKS process {self._selected_pid} is no longer running. "
                    "Call sw_status and select a current instance."
                )
            target_pid = self._selected_pid
        elif len(process_ids) > 1:
            raise RuntimeError(
                "More than one SOLIDWORKS instance is running "
                f"(PIDs {', '.join(map(str, process_ids))}). Call sw_status, then "
                "sw_ensure_ready(instance_pid=...) to choose the visible instance."
            )
        elif process_ids:
            target_pid = process_ids[0]
        else:
            target_pid = None

        if self._app is not None and self._app_pid == target_pid and target_pid is not None:
            try:
                self._value(self._app, "RevisionNumber")
                app = self._app
            except Exception:
                self._app = None
                self._app_pid = None
        else:
            app = None

        if app is None and target_pid is not None:
            deadline = time.monotonic() + (30 if launch else 0)
            while True:
                instance = self._registered_instances().get(target_pid)
                if instance is not None:
                    app = instance["app"]
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"SOLIDWORKS is running as process {target_pid}, but it has no responsive "
                        "COM entry. Close modal dialogs and retry; another instance was not started."
                    )
                self._sta._pythoncom.PumpWaitingMessages()
                time.sleep(0.5)

        if app is None and target_pid is None:
            if not launch:
                raise RuntimeError("SolidWorks is not running. Use sw_ensure_ready to open it.")
            app = win32com.client.Dispatch("SldWorks.Application")
            self._app = app
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                self._sta._pythoncom.PumpWaitingMessages()
                try:
                    self._value(app, "RevisionNumber")
                    process_ids = self._solidworks_process_ids()
                    if len(process_ids) > 1:
                        raise RuntimeError(
                            "A second SOLIDWORKS instance appeared while starting. Call sw_status, "
                            "then sw_ensure_ready(instance_pid=...) to choose the visible instance."
                        )
                    self._app_pid = process_ids[0] if process_ids else None
                    break
                except RuntimeError:
                    raise
                except Exception:
                    time.sleep(0.5)
            else:
                self._app = None
                raise RuntimeError("SolidWorks did not become responsive within 90 seconds.")

        app = self._typed_application(app)
        self._app = app
        self._app_pid = target_pid or self._app_pid
        try:
            self._app.Visible = True
            self._app.UserControl = True
        except Exception as exc:
            raise RuntimeError(f"Could not make the selected SolidWorks instance visible: {exc}") from exc
        return self._app

    def _typed_application(self, app: Any) -> Any:
        import win32com.client.gencache

        revision = str(self._value(app, "RevisionNumber"))
        try:
            major = int(revision.split(".", 1)[0])
            self._sw_module = win32com.client.gencache.EnsureModule(
                self._TYPELIB_ID, 0, major, 0
            )
            dispatch = getattr(app, "_oleobj_", app)
            return self._sw_module.ISldWorks(dispatch)
        except Exception as exc:
            raise RuntimeError(
                f"Could not load the SOLIDWORKS {revision} API type library."
            ) from exc

    def _typed_document(self, doc: Any) -> Any:
        if self._sw_module is None:
            raise RuntimeError("SOLIDWORKS API bindings are not initialized.")
        dispatch = getattr(doc, "_oleobj_", doc)
        return self._sw_module.IModelDoc2(dispatch)

    def _typed_feature(self, feature: Any) -> Any:
        if feature is None:
            return None
        if self._sw_module is None:
            raise RuntimeError("SOLIDWORKS API bindings are not initialized.")
        dispatch = getattr(feature, "_oleobj_", feature)
        return self._sw_module.IFeature(dispatch)

    def _document(self, launch: bool = False) -> Any:
        app = self._connect(launch)
        doc = app.ActiveDoc
        if doc is None:
            raise RuntimeError("No active SolidWorks document. Create or open a part first.")
        return self._typed_document(doc)

    def _part_document(self) -> Any:
        doc = self._document()
        if self._doc_type(doc) != "part":
            raise RuntimeError("This operation needs an active part document; the current document is not a part.")
        return doc

    @staticmethod
    def _value(obj: Any, member: str) -> Any:
        """Read pywin32 members that SolidWorks exposes as either methods or properties."""
        value = getattr(obj, member)
        return value() if callable(value) else value

    def _features(self, doc: Any) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        feature = self._typed_feature(self._value(doc, "FirstFeature"))
        visited: set[str] = set()
        while feature is not None:
            name = str(feature.Name)
            if name in visited:
                break
            visited.add(name)
            try:
                type_name = str(self._value(feature, "GetTypeName2"))
            except Exception:
                type_name = "Unknown"
            items.append({"name": name, "type": type_name})
            feature = self._typed_feature(self._value(feature, "GetNextFeature"))
        return items

    def _sketch_features(self, doc: Any) -> list[str]:
        return [
            item["name"]
            for item in self._features(doc)
            if item["type"].lower() in {"profilefeature", "3dprofilefeature", "sketch"}
        ]

    @staticmethod
    def _active_sketch(doc: Any) -> bool:
        try:
            return doc.SketchManager.ActiveSketch is not None
        except Exception:
            try:
                return doc.GetActiveSketch2() is not None
            except Exception:
                return False

    @staticmethod
    def _rebuild(doc: Any) -> bool:
        return bool(doc.ForceRebuild3(False))

    @staticmethod
    def _mass_properties(doc: Any) -> dict[str, Any] | None:
        try:
            mass = doc.Extension.CreateMassProperty()
            if mass is None:
                return None
            center = mass.CenterOfMass
            return {
                "volume_m3": float(mass.Volume),
                "surface_area_m2": float(mass.SurfaceArea),
                "mass_kg": float(mass.Mass),
                "center_of_mass_m": [float(center[0]), float(center[1]), float(center[2])],
            }
        except Exception:
            return None

    @staticmethod
    def _doc_type(doc: Any) -> str:
        return {1: "part", 2: "assembly", 3: "drawing"}.get(
            int(SolidWorksBridge._value(doc, "GetType")), "unknown"
        )

    def status(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            processes = self._solidworks_processes()
            registered = self._registered_instances()
            instances = []
            for process in processes:
                pid = process["pid"]
                item = registered.get(pid)
                instances.append({
                    "pid": pid,
                    "window_title": process["window_title"],
                    "has_window": bool(process["window_title"] and process["window_title"] != "N/A"),
                    "registered_with_com": item is not None,
                    "visible": bool(item["visible"]) if item else None,
                    "version": item["version"] if item else None,
                    "active_document": item["active_document"] if item else None,
                })
            return {
                "running": bool(processes),
                "selected_pid": self._selected_pid,
                "instances": instances,
                "message": (
                    "Choose an instance with sw_ensure_ready(instance_pid=...) before modeling."
                    if len(processes) > 1 and self._selected_pid is None
                    else None
                ),
            }

        return self._sta.call(run)

    def ensure_ready(self, instance_pid: int | None = None) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            if instance_pid is not None:
                if instance_pid <= 0:
                    raise ValueError("instance_pid must be a positive process ID.")
                self._selected_pid = instance_pid
                self._app = None
                self._app_pid = None
            app = self._connect(True)
            doc = app.ActiveDoc
            return {
                "running": True,
                "version": str(self._value(app, "RevisionNumber")),
                "active_document": str(self._value(doc, "GetTitle")) if doc is not None else None,
                "selected_pid": self._app_pid,
            }

        return self._sta.call(run)

    def new_document(self, document_type: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            from win32com.client import constants

            app = self._connect(True)
            try:
                setting = {
                    "part": constants.swDefaultTemplatePart,
                    "assembly": constants.swDefaultTemplateAssembly,
                }[document_type]
                template = str(app.GetUserPreferenceStringValue(setting) or "")
            except Exception as exc:
                raise RuntimeError(
                    "Could not read SolidWorks' configured default template. Set the Part/Assembly "
                    "default template in SolidWorks Options, then retry."
                ) from exc
            if not template or not Path(template).is_file():
                raise RuntimeError(
                    f"SolidWorks has no usable default {document_type} template configured. "
                    "Set it in Tools > Options > Default Templates and retry."
                )
            app.NewDocument(template, 0, 0, 0)
            doc = app.ActiveDoc
            if doc is None or self._doc_type(doc) != document_type:
                raise RuntimeError(f"SolidWorks did not create a {document_type} document.")
            doc = self._typed_document(doc)
            doc.GraphicsRedraw2()
            return {
                "created": document_type,
                "title": str(self._value(doc, "GetTitle")),
                "path": str(self._value(doc, "GetPathName")),
            }

        return self._sta.call(run)

    def open_document(self, path: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            import pythoncom
            import win32com.client

            app = self._connect(True)
            target = Path(path).expanduser()
            if not target.is_absolute() or not target.is_file():
                raise ValueError("path must be an absolute path to an existing SolidWorks document.")
            type_id = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}.get(target.suffix.lower())
            if type_id is None:
                raise ValueError("Only native .sldprt, .sldasm, and .slddrw files can be opened.")
            errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            doc = app.OpenDoc6(str(target), type_id, 1, "", errors, warnings)
            if doc is None:
                raise RuntimeError(f"SolidWorks failed to open {target} (error code {errors.value}).")
            return {
                "opened": str(target),
                "type": self._doc_type(doc),
                "title": str(self._value(doc, "GetTitle")),
            }

        return self._sta.call(run)

    def start_sketch(self, plane: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._part_document()
            if self._active_sketch(doc):
                raise RuntimeError("A sketch is already being edited. Finish it before starting another.")
            available = [
                item["name"] for item in self._features(doc)
                if item["type"].lower() == "refplane"
            ]
            aliases = {
                "front": ("front plane", "front", "صفحه جلو", "صفحه جلویی", "جلو", "vorne", "plan de face"),
                "top": ("top plane", "top", "صفحه بالا", "بالا", "oben", "plan supérieur"),
                "right": ("right plane", "right", "صفحه راست", "راست", "rechts", "plan de droite"),
            }
            requested = plane.strip()
            target = next((name for name in available if name.casefold() == requested.casefold()), None)
            if target is None:
                tokens = aliases.get(requested.casefold(), (requested.casefold(),))
                target = next(
                    (name for name in available if any(token in name.casefold() for token in tokens)),
                    None,
                )
            if target is None:
                raise ValueError(
                    f"Could not find sketch plane {plane!r}. Available reference planes: "
                    f"{available or 'none'}. Use one of those exact names."
                )
            doc.ClearSelection2(True)
            selected = doc.Extension.SelectByID2(target, "PLANE", 0, 0, 0, False, 0, None, 0)
            if not selected:
                raise RuntimeError(f"SolidWorks could not select the reference plane {target!r}.")
            self._sketch_names_before = set(self._sketch_features(doc))
            doc.SketchManager.InsertSketch(True)
            if not self._active_sketch(doc):
                raise RuntimeError("SolidWorks did not enter sketch mode.")
            doc.ClearSelection2(True)
            doc.GraphicsRedraw2()
            return {"sketch_active": True, "plane": target, "units": "meters internally; tool dimensions default to mm"}

        return self._sta.call(run)

    def _draw(self, action: Callable[[Any], Any], kind: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._part_document()
            if not self._active_sketch(doc):
                raise RuntimeError("No active sketch. Call sw_start_sketch first.")
            created = action(doc.SketchManager)
            if created is None:
                raise RuntimeError(f"SolidWorks failed to create the requested {kind}.")
            doc.GraphicsRedraw2()
            return {"created": kind, "sketch_active": True}

        return self._sta.call(run)

    def draw_line(self, x1: float, y1: float, x2: float, y2: float, unit: str) -> dict[str, Any]:
        values = [to_meters(value, unit) for value in (x1, y1, x2, y2)]
        if math.dist(values[:2], values[2:]) == 0:
            raise ValueError("A line must have two different endpoints.")
        return self._draw(lambda sm: sm.CreateLine(values[0], values[1], 0, values[2], values[3], 0), "line")

    def draw_rectangle(self, x1: float, y1: float, x2: float, y2: float, unit: str) -> dict[str, Any]:
        x1, y1, x2, y2 = (to_meters(value, unit) for value in (x1, y1, x2, y2))
        if x1 == x2 or y1 == y2:
            raise ValueError("A rectangle must have nonzero width and height.")
        return self._draw(
            lambda sm: sm.CreateCornerRectangle(x1, y1, 0, x2, y2, 0), "rectangle"
        )

    def draw_circle(self, cx: float, cy: float, radius: float, unit: str) -> dict[str, Any]:
        cx, cy = to_meters(cx, unit), to_meters(cy, unit)
        radius = positive_meters(radius, unit, "radius")
        return self._draw(lambda sm: sm.CreateCircleByRadius(cx, cy, 0, radius), "circle")

    def draw_arc(
        self, x1: float, y1: float, xm: float, ym: float, x2: float, y2: float, unit: str
    ) -> dict[str, Any]:
        x1, y1, xm, ym, x2, y2 = (to_meters(value, unit) for value in (x1, y1, xm, ym, x2, y2))
        points = ((x1, y1), (xm, ym), (x2, y2))
        if len(set(points)) != 3:
            raise ValueError("A three-point arc needs three different points.")
        area2 = (xm - x1) * (y2 - y1) - (ym - y1) * (x2 - x1)
        if abs(area2) < 1e-15:
            raise ValueError("The three arc points must not be collinear.")
        return self._draw(
            lambda sm: sm.Create3PointArc(x1, y1, 0, xm, ym, 0, x2, y2, 0), "arc"
        )

    def finish_sketch(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._part_document()
            if not self._active_sketch(doc):
                raise RuntimeError("No sketch is being edited.")
            before = self._sketch_names_before or set(self._sketch_features(doc))
            doc.SketchManager.InsertSketch(True)
            if self._active_sketch(doc):
                raise RuntimeError("SolidWorks did not exit sketch mode.")
            if not self._rebuild(doc):
                raise RuntimeError("Sketch rebuild failed; inspect the SolidWorks feature tree.")
            sketches = self._sketch_features(doc)
            added = [name for name in sketches if name not in before]
            if len(added) != 1:
                raise RuntimeError(
                    "Sketch closed, but its exact feature-tree name could not be identified safely. "
                    f"New sketch features found: {added or 'none'}. Inspect the tree before continuing."
                )
            sketch = added[0]
            self._sketch_names_before = None
            doc.GraphicsRedraw2()
            return {"sketch_finished": sketch, "feature_tree_sketches": sketches}

        return self._sta.call(run)

    def extrude(self, sketch_name: str, depth: float, unit: str, direction: str) -> dict[str, Any]:
        distance = positive_meters(depth, unit, "depth")
        if direction not in {"forward", "backward", "both"}:
            raise ValueError("direction must be forward, backward, or both.")

        def run() -> dict[str, Any]:
            doc = self._part_document()
            if self._active_sketch(doc):
                raise RuntimeError("Finish the sketch before extruding it.")
            names = self._sketch_features(doc)
            if sketch_name not in names:
                raise ValueError(f"Sketch {sketch_name!r} was not found. Available sketches: {names}.")
            doc.ClearSelection2(True)
            if not doc.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, None, 0):
                raise RuntimeError(f"Could not select sketch {sketch_name!r}.")
            depth1 = distance / 2 if direction == "both" else distance
            depth2 = distance / 2 if direction == "both" else 0.0
            feature = doc.FeatureManager.FeatureExtrusion3(
                direction != "both", False, direction == "backward", 0, 0,
                depth1, depth2, False, False, False, False, 0.0, 0.0,
                False, False, False, False, True, True, True, 0, 0.0, False,
            )
            doc.ClearSelection2(True)
            if feature is None:
                raise RuntimeError("SolidWorks did not create the extrusion feature.")
            if not self._rebuild(doc):
                raise RuntimeError("Extrusion rebuild failed; inspect the SolidWorks feature tree.")
            doc.ShowNamedView2("*Isometric*", 0)
            doc.ViewZoomtofit()
            doc.GraphicsRedraw2()
            return {
                "created": str(feature.Name),
                "source_sketch": sketch_name,
                "depth": depth,
                "unit": unit,
                "direction": direction,
                "mass_properties": self._mass_properties(doc),
            }

        return self._sta.call(run)

    def cut_extrude(self, sketch_name: str, depth: float, unit: str, through_all: bool) -> dict[str, Any]:
        distance = positive_meters(depth, unit, "depth")

        def run() -> dict[str, Any]:
            doc = self._part_document()
            if self._active_sketch(doc):
                raise RuntimeError("Finish the sketch before cutting it.")
            names = self._sketch_features(doc)
            if sketch_name not in names:
                raise ValueError(f"Sketch {sketch_name!r} was not found. Available sketches: {names}.")
            doc.ClearSelection2(True)
            if not doc.Extension.SelectByID2(sketch_name, "SKETCH", 0, 0, 0, False, 0, None, 0):
                raise RuntimeError(f"Could not select sketch {sketch_name!r}.")
            blind = 0
            through_all_end = 1
            feature = doc.FeatureManager.FeatureCut4(
                True, False, False,
                through_all_end if through_all else blind,
                blind,
                0.0 if through_all else distance, 0.0,
                False, False, False, False,
                0.0, 0.0,
                False, False, False, False,
                False, False, True, False, False, False,
                0, 0.0, False, False,
            )
            doc.ClearSelection2(True)
            if feature is None:
                raise RuntimeError("SolidWorks did not create the cut feature.")
            if not self._rebuild(doc):
                raise RuntimeError("Cut rebuild failed; inspect the SolidWorks feature tree.")
            doc.ShowNamedView2("*Isometric*", 0)
            doc.ViewZoomtofit()
            doc.GraphicsRedraw2()
            return {
                "created": str(feature.Name),
                "source_sketch": sketch_name,
                "through_all": through_all,
                "depth": None if through_all else depth,
                "unit": unit,
                "mass_properties": self._mass_properties(doc),
            }

        return self._sta.call(run)

    def features(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._document()
            return {"document": str(self._value(doc, "GetTitle")), "features": self._features(doc)}

        return self._sta.call(run)

    def inspect(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._document()
            return {
                "document": {
                    "title": str(self._value(doc, "GetTitle")),
                    "type": self._doc_type(doc),
                    "path": str(self._value(doc, "GetPathName")),
                    "saved": bool(self._value(doc, "GetPathName")),
                },
                "features": self._features(doc),
                "mass_properties": self._mass_properties(doc),
                "note": "Read-only inspection. Use sw_validate_model after making geometry changes.",
            }

        return self._sta.call(run)

    def validate(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._document()
            rebuild_ok = self._rebuild(doc)
            mass_properties = self._mass_properties(doc)
            has_solid = bool(mass_properties and mass_properties["volume_m3"] > 0)
            return {
                "document": str(self._value(doc, "GetTitle")),
                "rebuild_succeeded": rebuild_ok,
                "features": self._features(doc),
                "mass_properties": mass_properties,
                "has_solid_body": has_solid,
                "validated": rebuild_ok and has_solid,
            }

        return self._sta.call(run)

    def mass_properties(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._document()
            props = self._mass_properties(doc)
            if props is None:
                raise RuntimeError("Mass properties are unavailable; the document may not contain a solid body.")
            return props

        return self._sta.call(run)

    def set_view(self, view: str) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            doc = self._document()
            names = {
                "isometric": "*Isometric*",
                "front": "*Front*",
                "top": "*Top*",
                "right": "*Right*",
            }
            doc.ShowNamedView2(names[view], 0)
            doc.ViewZoomtofit()
            doc.GraphicsRedraw2()
            return {"view": view, "fit": True}

        return self._sta.call(run)

    def save(self, path: str | None, overwrite: bool) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            import pythoncom
            import win32com.client

            doc = self._document()
            current = str(self._value(doc, "GetPathName"))
            if path is None or not path.strip():
                if not current:
                    raise ValueError("This document has no file name yet; supply an absolute .SLDPRT path.")
                errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                ok = doc.Save3(1, errors, warnings)
                if not ok or errors.value:
                    raise RuntimeError(f"SolidWorks failed to save the document (error code {errors.value}).")
                return {"saved": str(self._value(doc, "GetPathName")), "warnings": warnings.value}

            target = Path(path).expanduser()
            if not target.is_absolute():
                raise ValueError("Save path must be absolute.")
            if target.suffix.lower() not in {".sldprt", ".sldasm", ".slddrw"}:
                raise ValueError("Save path must end in .SLDPRT, .SLDASM, or .SLDDRW.")
            expected_extension = {"part": ".sldprt", "assembly": ".sldasm", "drawing": ".slddrw"}[self._doc_type(doc)]
            if target.suffix.lower() != expected_extension:
                raise ValueError(f"This {self._doc_type(doc)} document must be saved as {expected_extension}.")
            if not target.parent.is_dir():
                raise ValueError(f"Save folder does not exist: {target.parent}")
            if target.exists() and os.path.normcase(str(target)) != os.path.normcase(current) and not overwrite:
                raise FileExistsError("Target file already exists. Set overwrite=true only if replacement is intended.")
            errors = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            warnings = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            ok = doc.Extension.SaveAs3(str(target), 0, 1, None, None, errors, warnings)
            if not ok or errors.value:
                raise RuntimeError(f"SolidWorks failed to save {target} (error code {errors.value}).")
            return {"saved": str(target), "warnings": warnings.value}

        return self._sta.call(run)

