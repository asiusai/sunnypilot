#!/usr/bin/env python3
import base64
import json
import os
from decimal import Decimal

import zmq
from datetime import datetime, date
from typing import NoReturn

from openpilot.system.loggerd.config import STATS_SOCKET


class METRIC_TYPE:
  GAUGE = 'g'
  SAMPLE = 'sa'
  RAW = 'r'


class StatLog:
  def __init__(self):
    self.pid = None
    self.zctx = None
    self.sock = None
    self.stats_socket = STATS_SOCKET

  def connect(self) -> None:
    self.zctx = zmq.Context.instance() or zmq.Context()
    self.sock = self.zctx.socket(zmq.PUSH)
    self.sock.setsockopt(zmq.LINGER, 10)
    self.sock.connect(self.stats_socket)
    self.pid = os.getpid()

  def __del__(self):
    if self.sock is not None:
      self.sock.close()
    if self.zctx is not None:
      self.zctx.term()

  def _send(self, metric: str) -> None:
    if os.getpid() != self.pid:
      self.connect()

    try:
      self.sock.send_string(metric, zmq.NOBLOCK)
    except zmq.error.Again:
      # drop :/
      pass

  def gauge(self, name: str, value: float) -> None:
    self._send(f"{name}:{value}|{METRIC_TYPE.GAUGE}")

  # Samples will be recorded in a buffer and at aggregation time,
  # statistical properties will be logged (mean, count, percentiles, ...)
  def sample(self, name: str, value: float):
    self._send(f"{name}:{value}|{METRIC_TYPE.SAMPLE}")


class StatLogSP(StatLog):
  def __init__(self, intercept=True):
    """
    Initializes the class instance with an optional parameter to determine
    if statistical logging should be configured or not.

    :param intercept: A boolean flag that indicates whether to initialize
        the `comma_statlog`. If True, the `comma_statlog` attribute is
        instantiated as a `StatLog` object. Defaults to True.
    """
    super().__init__()
    self.comma_statlog = StatLog() if intercept else None
    self.stats_socket = f"{STATS_SOCKET}_sp"

  def connect(self) -> None:
    super().connect()
    if self.comma_statlog:
      self.comma_statlog.connect()

  def __del__(self):
    super().__del__()
    if self.comma_statlog:
      self.comma_statlog.__del__()

  def _send(self, metric: str) -> None:
    super()._send(metric)
    if self.comma_statlog:
      self.comma_statlog._send(metric)

  @staticmethod
  def default_converter(obj):
    if isinstance(obj, (datetime, date)):
      return obj.isoformat()
    if isinstance(obj, set):
      return list(obj)
    if isinstance(obj, Decimal):
      return float(obj)
    return str(obj)  # fallback for unknown types

  def raw(self, name: str, value: dict) -> None:
    encoded_dict = base64.b64encode(json.dumps(value, default=self.default_converter).encode("utf-8")).decode("utf-8")
    self._send(f"{name}:{encoded_dict}|{METRIC_TYPE.RAW}")


def main() -> NoReturn:
  raise RuntimeError("This service is disabled in the Asius fork.")


if __name__ == "__main__":
  main()
else:
  statlog = StatLogSP(intercept=True)
