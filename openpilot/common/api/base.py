import os
import unicodedata
from openpilot.common.hardware.hw import Paths

# name: jwt signature algorithm
KEYS = {"id_rsa": "RS256",
        "id_ecdsa": "ES256"}


class BaseApi:
  def __init__(self, dongle_id, api_host, user_agent="openpilot-"):
    self.dongle_id = dongle_id
    self.api_host = api_host
    self.user_agent = user_agent
    self.jwt_algorithm, self.private_key, _ = self.get_key_pair()

  def get(self, *args, **kwargs):
    return self.request('GET', *args, **kwargs)

  def post(self, *args, **kwargs):
    return self.request('POST', *args, **kwargs)

  def request(self, method, endpoint, timeout=None, access_token=None, **params):
    return self.api_get(endpoint, method=method, timeout=timeout, access_token=access_token, **params)

  def _get_token(self, payload_extra=None, expiry_hours=1, **extra_payload):
    raise RuntimeError("Legacy cloud services are disabled in the Asius fork.")

  def get_token(self, payload_extra=None, expiry_hours=1):
    return self._get_token(payload_extra, expiry_hours)

  def remove_non_ascii_chars(self, text):
    normalized_text = unicodedata.normalize('NFD', text)
    ascii_encoded_text = normalized_text.encode('ascii', 'ignore')
    return ascii_encoded_text.decode()

  def api_get(self, endpoint, method='GET', timeout=None, access_token=None, session=None, json=None, **params):
    raise RuntimeError("Legacy cloud services are disabled in the Asius fork.")

  @staticmethod
  def get_key_pair() -> tuple[str, str, str] | tuple[None, None, None]:
    for key in KEYS:
      if os.path.isfile(Paths.persist_root() + f'/comma/{key}') and os.path.isfile(Paths.persist_root() + f'/comma/{key}.pub'):
        with open(Paths.persist_root() + f'/comma/{key}') as private, open(Paths.persist_root() + f'/comma/{key}.pub') as public:
          return KEYS[key], private.read(), public.read()
    return None, None, None
