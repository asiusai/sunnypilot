import io
import json
import pickle
import shutil
import struct
import tempfile
import time
from pathlib import Path

from tinygrad import Tensor, Device

from openpilot.common.file_chunker import get_manifest_path
from openpilot.common.hardware.usb import CHESTNUT_USB_PRODUCT, USB_DEVICES_PATH, is_chestnut_usb_id

MODELS_DIR = Path(__file__).resolve().parent / 'models'
TG_INPUT_DEVICES_PATH = MODELS_DIR / 'tg_input_devices.json'
CHESTNUT_POWERED_VOLTAGE = 5000
CHESTNUT_PCIE_READY = 0x78


def tensor_from_dma_buf(ptr: int, fd: int | None, size: int, device: str) -> Tensor:
  if fd is None or device.split(':', 1)[0] != 'QCOM':
    return Tensor.from_blob(ptr, (size,), dtype='uint8', device=device)
  tensor = Tensor.empty(size, dtype='uint8', device=device)
  buffer = tensor.uop.buffer
  buffer.allocate(Device[device].iface.map(ptr, buffer.nbytes, fd))
  return tensor


def get_tg_input_devices(process_name: str, chestnut: bool):
  with open(TG_INPUT_DEVICES_PATH) as f:
    return json.load(f)[process_name]['default' if not chestnut else 'chestnut']

def modeld_pkl_path(chestnut: bool):
  prefix = 'big_' if chestnut else ''
  return MODELS_DIR / f'{prefix}driving_tinygrad.pkl'

def dump_oob(obj, f):
  with tempfile.TemporaryFile(dir=".") as tmp:
    def buffer_callback(pb: pickle.PickleBuffer):
      m = pb.raw()
      tmp.write(struct.pack('<q', m.nbytes))
      tmp.write(m)
      pb.release() # keep peak ram at ~1 buffer
    stream = io.BytesIO()
    pickle.Pickler(stream, protocol=5, buffer_callback=buffer_callback).dump(obj)
    opcodes = stream.getvalue()
    f.write(struct.pack('<q', len(opcodes)))
    f.write(opcodes)
    tmp.seek(0)
    shutil.copyfileobj(tmp, f)

def load_oob(f):
  opcodes = f.read(struct.unpack('<q', f.read(8))[0])
  def buffers():
    while (h := f.read(8)):
      pb = pickle.PickleBuffer(bytearray(struct.unpack('<q', h)[0]))
      f.readinto(pb)
      yield pb
  return pickle.load(io.BytesIO(opcodes), buffers=buffers())

def chestnut_present(timeout: float = 0.) -> bool:
  deadline = time.monotonic() + timeout
  seen = False
  while True:
    for d in USB_DEVICES_PATH.glob("*"):
      try:
        usb_id = (int((d / "idVendor").read_text(), 16), int((d / "idProduct").read_text(), 16))
        product = (d / "product").read_text().strip()
        if is_chestnut_usb_id(*usb_id) and product == CHESTNUT_USB_PRODUCT:
          seen = True
          if float((d / "speed").read_text()) >= 5000:
            return True
      except (OSError, ValueError):
        pass
    if not seen or time.monotonic() >= deadline:
      return False
    # Keep USB idle during firmware recovery, including its brief disconnect.
    # F3/GPU initialization at 480M would cancel the pending SuperSpeed retry.
    time.sleep(.1)

def chestnut_compiled() -> bool:
  return Path(get_manifest_path(modeld_pkl_path(chestnut=True))).is_file()


def chestnut_ready(state) -> bool:
  return state.supplyVoltage >= CHESTNUT_POWERED_VOLTAGE and not state.supplyFault and state.pcieLtssm == CHESTNUT_PCIE_READY
