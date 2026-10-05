"""Local crash diagnostics. Remote reporting is disabled."""
import os
import traceback
from datetime import datetime
from enum import Enum

from openpilot.common.hardware.hw import Paths
from openpilot.common.swaglog import cloudlog

CRASHES_DIR = Paths.crash_log_root()


class SentryProject(Enum):
  SELFDRIVE = "local"
  SELFDRIVE_NATIVE = "local-native"


def init(project: SentryProject) -> bool:
  return False


def report_tombstone(fn: str, message: str, contents: str) -> None:
  cloudlog.error({'tombstone': message})
  save_exception(contents)


def capture_exception(*args, **kwargs) -> None:
  cloudlog.error("crash", exc_info=kwargs.get('exc_info', 1))
  save_exception(traceback.format_exc())


def save_exception(content: str) -> None:
  try:
    if not os.path.exists(CRASHES_DIR):
      os.makedirs(CRASHES_DIR)

    files = [
      os.path.join(CRASHES_DIR, datetime.now().strftime("%Y-%m-%d--%H-%M-%S.log")),
      os.path.join(CRASHES_DIR, "error.log")
    ]

    for fn in files:
      with open(fn, 'w') as f:
        if fn == "error.log":
          lines = content.splitlines()[-3:]
          f.write("\n".join(lines))
        else:
          f.write(content)

    cloudlog.error(f"logged crash to {files}")
  except Exception:
    cloudlog.exception("error when attempting to save exception")


def capture_fingerprint_mock() -> None:
  cloudlog.warning("car does not match any fingerprints")


def capture_fingerprint(candidate: str, car_name: str) -> None:
  cloudlog.info("Fingerprinted %s (%s)", candidate, car_name)


def set_tag(key: str, value: str) -> None:
  pass


def set_user() -> None:
  pass
