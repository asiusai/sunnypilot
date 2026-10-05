"""Device identity is local. Comma registration is disabled."""
from openpilot.common.params import Params
from openpilot.system.asius.registration import register, UNREGISTERED_DONGLE_ID


def is_registered_device() -> bool:
  return Params().get("DongleId") not in (None, UNREGISTERED_DONGLE_ID)


if __name__ == '__main__':
  print(register())
