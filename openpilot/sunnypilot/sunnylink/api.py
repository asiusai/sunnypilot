import os
import time

from openpilot.common.api.base import BaseApi
from openpilot.common.params import Params
from openpilot.common.hardware import HARDWARE
from openpilot.common.hardware.hw import Paths

API_HOST = os.getenv('SUNNYLINK_API_HOST', 'https://stg.api.sunnypilot.ai')
UNREGISTERED_SUNNYLINK_DONGLE_ID = "UnregisteredDevice"
MAX_RETRIES = 6
CRASH_LOG_DIR = Paths.crash_log_root()


class SunnylinkApi(BaseApi):
  def __init__(self, dongle_id):
    super().__init__(dongle_id, API_HOST)
    self.user_agent = "sunnypilot-"
    self.spinner = None
    self.params = Params()

  def api_get(self, endpoint, method='GET', timeout=10, access_token=None, session=None, json=None, **kwargs):
    return None

  def get_token(self, payload_extra=None, expiry_hours=1):
    # Add your additional data here
    raise RuntimeError("sunnylink is disabled in the Asius fork.")

  def _status_update(self, message):
    print(message)
    if self.spinner:
      self.spinner.update(message)
      time.sleep(0.5)

  def _resolve_dongle_ids(self):
    sunnylink_dongle_id = self.params.get("SunnylinkDongleId")
    comma_dongle_id = self.dongle_id or self.params.get("DongleId")
    return sunnylink_dongle_id, comma_dongle_id

  def _resolve_imeis(self):
    imei = None
    imei_try = 0
    while imei is None and imei_try < MAX_RETRIES:
      try:
        imei = HARDWARE.get_imei()
      except Exception:
        self._status_update(f"Error getting imei, trying again... [{imei_try + 1}/{MAX_RETRIES}]")
        time.sleep(1)
      imei_try += 1
    return imei, ""

  def _resolve_serial(self):
    return (self.params.get("HardwareSerial")
            or HARDWARE.get_serial())

  def register_device(self, spinner=None, timeout=60, verbose=False):
    return UNREGISTERED_SUNNYLINK_DONGLE_ID
