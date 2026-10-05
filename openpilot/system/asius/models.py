"""App controls for the device's sunnypilot model catalog."""
import threading
import time

from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.sunnypilot.models.fetcher import get_cached_bundles
from openpilot.sunnypilot.models.helpers import ACTIVE_BUNDLE_KEYS, get_selected_bundle
from openpilot.system.asius.access_policy import require_ignition_off

_lock = threading.RLock()
_state = None


def _source(source: str) -> str:
  if source not in ACTIVE_BUNDLE_KEYS:
    raise ValueError("Unknown model source")
  return source


def getModelState(source: str = "qcom") -> dict:
  global _state
  source = _source(source)
  params = Params()
  bundles = get_cached_bundles(params, source)
  selected = get_selected_bundle(params, source)
  pending = params.get("ModelManager_DownloadRef")
  with _lock:
    if _state is None:
      _state = messaging.SubMaster(['modelManagerSP'])
    _state.update(0)
    fresh = _state.seen['modelManagerSP'] and 0 <= (time.monotonic_ns() - _state.logMonoTime['modelManagerSP']) / 1e9 < 5
    download = None
    if fresh:
      bundle = _state['modelManagerSP'].selectedBundle
      if bundle.ref and any(b.ref == bundle.ref for b in bundles):
        progress = [m.artifact.downloadProgress.progress for m in bundle.models if m.artifact.fileName]
        download = {"id": bundle.ref, "status": str(bundle.status), "progress": sum(progress) / len(progress) if progress else 0}
  return {
    "source": source,
    "options": [{"id": b.ref, "name": b.displayName, "runner": str(b.runner)} for b in bundles if b.ref],
    "selected": selected.ref if selected else None,
    "pending": pending,
    "download": download,
    "available": bool(fresh),
  }


def selectModel(source: str, ref: str | None) -> dict:
  require_ignition_off()
  source = _source(source)
  params = Params()
  if ref is not None and (not isinstance(ref, str) or not any(b.ref == ref for b in get_cached_bundles(params, source))):
    raise ValueError("Model is not in the device catalog. Refresh the model list.")
  with _lock:
    # Only the manager accepts catalog URLs and publishes verified active bundles.
    # App requests contain a catalog reference, never an artifact or download URL.
    require_ignition_off()
    if ref is None:
      params.remove("ModelManager_DownloadRef")
      params.remove(ACTIVE_BUNDLE_KEYS[source])
    else:
      params.put("ModelManager_DownloadRef", ref, block=True)
    params.remove("ModelRunnerTypeCache")
  return {"success": True}
