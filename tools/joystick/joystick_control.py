#!/usr/bin/env python3
import os
import argparse
import threading
import time
import numpy as np
from inputs import UnpluggedError, get_gamepad

from cereal import messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.system.hardware import HARDWARE
from openpilot.tools.lib.kbhit import KBHit

EXPO = 0.4

try:
  from openpilot.tools.joystick import Gamepad
  GAMEPAD_AVAILABLE = True
except ImportError:
  GAMEPAD_AVAILABLE = False


class Keyboard:
  def __init__(self):
    self.kb = KBHit()
    self.axis_increment = 0.05  # 5% of full actuation each key press
    self.axes_map = {'w': 'gb', 's': 'gb',
                     'a': 'steer', 'd': 'steer'}
    self.axes_values = {'gb': 0., 'steer': 0.}
    self.axes_order = ['gb', 'steer']
    self.cancel = False

  def update(self):
    key = self.kb.getch().lower()
    self.cancel = False
    if key == 'r':
      self.axes_values = dict.fromkeys(self.axes_values, 0.)
    elif key == 'c':
      self.cancel = True
    elif key in self.axes_map:
      axis = self.axes_map[key]
      incr = self.axis_increment if key in ['w', 'a'] else -self.axis_increment
      self.axes_values[axis] = float(np.clip(self.axes_values[axis] + incr, -1, 1))
    else:
      return False
    return True


class Joystick:
  def __init__(self):
    # This class supports a PlayStation 5 DualSense controller on the comma 3X
    # TODO: find a way to get this from API or detect gamepad/PC, perhaps "inputs" doesn't support it
    self.cancel_button = 'BTN_NORTH'  # BTN_NORTH=X/triangle
    if HARDWARE.get_device_type() == 'pc':
      accel_axis = 'ABS_Z'
      steer_axis = 'ABS_RX'
      # TODO: once the longcontrol API is finalized, we can replace this with outputting gas/brake and steering
      self.flip_map = {'ABS_RZ': accel_axis}
    else:
      accel_axis = 'ABS_RX'
      steer_axis = 'ABS_Z'
      self.flip_map = {'ABS_RY': accel_axis}

    self.min_axis_value = {accel_axis: 0., steer_axis: 0.}
    self.max_axis_value = {accel_axis: 255., steer_axis: 255.}
    self.axes_values = {accel_axis: 0., steer_axis: 0.}
    self.axes_order = [accel_axis, steer_axis]
    self.cancel = False

  def update(self):
    try:
      joystick_event = get_gamepad()[0]
    except (OSError, UnpluggedError):
      self.axes_values = dict.fromkeys(self.axes_values, 0.)
      return False

    event = (joystick_event.code, joystick_event.state)

    # flip left trigger to negative accel
    if event[0] in self.flip_map:
      event = (self.flip_map[event[0]], -event[1])

    if event[0] == self.cancel_button:
      if event[1] == 1:
        self.cancel = True
      elif event[1] == 0:   # state 0 is falling edge
        self.cancel = False
    elif event[0] in self.axes_values:
      self.max_axis_value[event[0]] = max(event[1], self.max_axis_value[event[0]])
      self.min_axis_value[event[0]] = min(event[1], self.min_axis_value[event[0]])

      norm = -float(np.interp(event[1], [self.min_axis_value[event[0]], self.max_axis_value[event[0]]], [-1., 1.]))
      norm = norm if abs(norm) > 0.03 else 0.  # center can be noisy, deadzone of 3%
      self.axes_values[event[0]] = EXPO * norm ** 3 + (1 - EXPO) * norm  # less action near center for fine control
    else:
      return False
    return True


class BluetoothGamepad:
  """Bluetooth gamepad support using PiBorg Gamepad library (for PS4/PS5 controllers via Bluetooth)"""
  def __init__(self):
    if not GAMEPAD_AVAILABLE:
      raise ImportError("Gamepad library not available. Run: cd /data/openpilot/tools/joystick && git clone https://github.com/piborg/Gamepad && cp Gamepad/Gamepad.py . && cp Gamepad/Controllers.py .")

    self.gamepad = None
    self._connect()
    self.speed_scale = [0.33, 0.66, 1.0]
    self.speed_mode = 1
    self.axes_values = {'accel': 0., 'steer': 0.}
    self.axes_order = ['accel', 'steer']
    self.cancel = False
    self._dpad_pressed = False

  def _connect(self):
    if not Gamepad.available():
      print('Waiting for Bluetooth gamepad connection...')
      print('Make sure you have run: sudo hciattach /dev/ttyHS1 any 115200 flow')
      print('And paired your controller via bluetoothctl')
      while not Gamepad.available():
        time.sleep(1.0)
    # DualSense over Bluetooth has different axis mapping than PS4
    # Axis 0: LEFT-X, 1: LEFT-Y, 2: RIGHT-X, 3: L2, 4: R2, 5: RIGHT-Y
    self.gamepad = Gamepad.PS4()
    # Override axis names for DualSense Bluetooth mapping
    self.gamepad.axisNames = {
      0: 'LEFT-X',
      1: 'LEFT-Y',
      2: 'RIGHT-X',
      3: 'L2',
      4: 'R2',
      5: 'RIGHT-Y',
      6: 'DPAD-X',
      7: 'DPAD-Y'
    }
    self.gamepad._setupReverseMaps()
    self.gamepad.startBackgroundUpdates()
    print('Bluetooth gamepad connected!')

  def update(self):
    if not self.gamepad.isConnected():
      print('Gamepad disconnected, attempting to reconnect...')
      self._connect()
      return False

    # Left stick X for steering (full range -1 to 1)
    steer = self.gamepad.axis('LEFT-X')
    self.axes_values['steer'] = -steer  # negative because left should be negative

    # L2 for braking, R2 for acceleration
    # Triggers go from -1 (released) to 1 (fully pressed)
    r2 = self.gamepad.axis('R2')  # acceleration
    l2 = self.gamepad.axis('L2')  # brake

    # Convert from [-1, 1] to [0, 1]
    accel_amount = (r2 + 1.0) / 2.0
    brake_amount = (l2 + 1.0) / 2.0

    # accel positive = accelerate, negative = brake
    self.axes_values['accel'] = self.speed_scale[self.speed_mode] * (accel_amount - brake_amount)

    # D-pad for speed mode
    dpad_y = self.gamepad.axis('DPAD-Y')
    if abs(dpad_y) > 0.5:
      if not self._dpad_pressed:
        self._dpad_pressed = True
        if dpad_y < 0 and self.speed_mode < 2:
          self.speed_mode += 1
          print(f'Speed mode: {self.speed_mode + 1}/3')
        elif dpad_y > 0 and self.speed_mode > 0:
          self.speed_mode -= 1
          print(f'Speed mode: {self.speed_mode + 1}/3')
    else:
      self._dpad_pressed = False

    # Triangle button for cancel
    self.cancel = self.gamepad.isPressed('TRIANGLE')

    return True


def send_thread(joystick):
  pm = messaging.PubMaster(['testJoystick'])

  rk = Ratekeeper(100, print_delay_threshold=None)

  while True:
    if rk.frame % 20 == 0:
      print('\n' + ', '.join(f'{name}: {round(v, 3)}' for name, v in joystick.axes_values.items()))

    joystick_msg = messaging.new_message('testJoystick')
    joystick_msg.valid = True
    joystick_msg.testJoystick.axes = [joystick.axes_values[ax] for ax in joystick.axes_order]

    pm.send('testJoystick', joystick_msg)

    rk.keep_time()


def joystick_control_thread(joystick):
  Params().put_bool('JoystickDebugMode', True)
  threading.Thread(target=send_thread, args=(joystick,), daemon=True).start()
  while True:
    joystick.update()


def main():
  joystick_control_thread(Joystick())


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Publishes events from your joystick to control your car.\n' +
                                               'openpilot must be offroad before starting joystick_control. This tool supports ' +
                                               'USB joysticks, Bluetooth gamepads (PS4/PS5), and keyboard input.',
                                   formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--keyboard', action='store_true', help='Use your keyboard instead of a joystick')
  parser.add_argument('--bluetooth', action='store_true', help='Use Bluetooth gamepad (PS4/PS5 controller)')
  args = parser.parse_args()

  if not Params().get_bool("IsOffroad") and "ZMQ" not in os.environ:
    print("The car must be off before running joystick_control.")
    exit()

  print()
  if args.keyboard:
    print('Gas/brake control: `W` and `S` keys')
    print('Steering control: `A` and `D` keys')
    print('Buttons')
    print('- `R`: Resets axes')
    print('- `C`: Cancel cruise control')
    joystick = Keyboard()
  elif args.bluetooth:
    print('Using Bluetooth gamepad (PS4/PS5 controller)')
    print('Gas control: R2 trigger')
    print('Brake control: L2 trigger')
    print('Steering control: Left joystick')
    print('Speed modes: D-pad Up/Down')
    print('Cancel: Triangle button')
    print()
    print('Before running, make sure to:')
    print('1. sudo hciattach /dev/ttyHS1 any 115200 flow')
    print('2. Pair controller via bluetoothctl')
    joystick = BluetoothGamepad()
  else:
    print('Using USB joystick, make sure to run cereal/messaging/bridge on your device if running over the network!')
    print('If not running on a comma device, the mapping may need to be adjusted.')
    joystick = Joystick()

  joystick_control_thread(joystick)
