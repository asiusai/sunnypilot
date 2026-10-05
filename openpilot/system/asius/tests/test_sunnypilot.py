import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from openpilot.common.params import Params
from openpilot.common.api.base import BaseApi
from openpilot.system import sentry
from openpilot.system.asius import access_policy, methods, models
from openpilot.system.manager.process_config import managed_processes
from openpilot.sunnypilot.sunnylink.api import SunnylinkApi, UNREGISTERED_SUNNYLINK_DONGLE_ID
from openpilot.sunnypilot.sunnylink.utils import sunnylink_need_register, sunnylink_ready, use_sunnylink_uploader


@pytest.fixture
def params(tmp_path, monkeypatch):
  params = Params(str(tmp_path / 'params'))
  monkeypatch.setattr(methods, 'Params', lambda: params)
  monkeypatch.setattr(models, 'Params', lambda: params)
  monkeypatch.setattr(methods.parameter_editor, 'params', lambda: params)
  return params


def test_removed_services_never_start_with_saved_settings(params):
  for key in ('SunnylinkEnabled', 'EnableSunnylinkUploader', 'EnableCopyparty', 'EnableGithubRunner'):
    params.put_bool(key, True, block=True)
  params.put('SunnylinkDongleId', 'old-account', block=True)
  params.put('NetworkMetered', False, block=True)
  assert not sunnylink_ready(params)
  assert not sunnylink_need_register(params)
  assert not use_sunnylink_uploader(params)
  for name in ('manage_athenad', 'uploader', 'manage_sunnylinkd', 'sunnylink_registration_manager',
               'statsd', 'statsd_sp', 'backup_manager', 'sunnylink_uploader', 'copyparty-sfx'):
    assert name not in managed_processes or not managed_processes[name].enabled
  for name in ('manage_relayd', 'asius_uploader', 'models_manager', 'mapd_manager'):
    assert managed_processes[name].enabled


def test_legacy_api_cannot_use_network(params, monkeypatch):
  network = Mock(side_effect=AssertionError('legacy network access'))
  monkeypatch.setattr('requests.sessions.Session.request', network)
  params.put_bool('SunnylinkEnabled', True, block=True)
  api = SunnylinkApi('old-account')
  api.params = params
  assert api.api_get('v2/pilotauth/') is None
  assert api.register_device() == UNREGISTERED_SUNNYLINK_DONGLE_ID
  with pytest.raises(RuntimeError):
    api.get_token()
  for host in ('https://api.comma.ai', 'https://overridden.invalid'):
    with pytest.raises(RuntimeError):
      BaseApi('old-account', host).api_get('device')
  assert sentry.init(sentry.SentryProject.SELFDRIVE) is False
  network.assert_not_called()


def test_local_crashes_are_kept(tmp_path, monkeypatch):
  monkeypatch.setattr(sentry, 'CRASHES_DIR', str(tmp_path))
  sentry.report_tombstone('test', 'test crash', 'local diagnostic')
  assert (tmp_path / 'error.log').read_text() == 'local diagnostic'


def test_existing_asius_identity_and_authorizations_survive_registration(params, tmp_path, monkeypatch):
  from openpilot.system.asius import identity, registration
  private = tmp_path / 'id_ed25519'
  monkeypatch.setattr(identity, 'PRIVATE_KEY_PATH', private)
  monkeypatch.setattr(identity, 'PUBLIC_KEY_PATH', tmp_path / 'id_ed25519.pub')
  monkeypatch.setattr(registration, 'Params', lambda: params)
  monkeypatch.setattr(registration, 'set_offroad_alert', lambda *args: None)
  first = identity.get_or_create_device_identity()
  original = private.read_bytes()
  params.put('AppAuthorizedKeys', {first: {'label': 'Existing app'}}, block=True)
  params.put('CloudUploadState', {'fixture': 'existing encryption state'}, block=True)
  assert registration.register() == first
  assert registration.register() == first
  assert private.read_bytes() == original
  assert params.get('AppAuthorizedKeys') == {first: {'label': 'Existing app'}}
  assert params.get('CloudUploadState') == {'fixture': 'existing encryption state'}


def test_sunny_settings_work_but_service_and_model_metadata_are_blocked(params):
  assert methods.saveParams({'Mads': False, 'CameraOffset': 0.1}) == {'Mads': 'ok', 'CameraOffset': 'ok'}
  assert methods.getAllParams()['Mads'] is False
  for name in ('SunnylinkEnabled', 'EnableCopyparty', 'EnableGithubRunner', 'ModelManager_ModelsCache', 'ModelManager_ActiveBundle'):
    assert methods.saveParams({name: True})[name] == 'error: blocked'
    assert name not in methods.getAllParams()
    entry, _ = methods.parameter_editor._value(params, name)
    assert entry['readOnlyReason']


def test_model_selection_uses_device_catalog_and_fresh_ignition(params, monkeypatch):
  monkeypatch.setattr(models, 'get_cached_bundles', lambda p, source: [SimpleNamespace(ref='known-model')])
  for ignition in (True, None):
    monkeypatch.setattr(access_policy, 'ignition_state', lambda ignition=ignition: ignition)
    with pytest.raises(PermissionError):
      models.selectModel('qcom', 'known-model')
    assert params.get('ModelManager_DownloadRef') is None
  monkeypatch.setattr(access_policy, 'ignition_state', lambda: False)
  with pytest.raises(ValueError):
    models.selectModel('qcom', 'https://untrusted.invalid/model')
  with pytest.raises(ValueError):
    models.selectModel('unknown', 'known-model')
  assert models.selectModel('qcom', 'known-model')['success']
  assert params.get('ModelManager_DownloadRef') == 'known-model'
  params.put('ModelManager_ActiveBundle', {'ref': 'known-model'}, block=True)
  assert models.selectModel('qcom', None)['success']
  assert params.get('ModelManager_DownloadRef') is None
  assert params.get('ModelManager_ActiveBundle') is None


def test_app_dispatcher_has_fork_identity_and_model_controls():
  assert methods.getVersion()['fork'] == 'sunnypilot'
  assert 'getModelState' in methods.dispatcher_for_peer('test')
  assert 'selectModel' in methods.dispatcher_for_peer('test')
  for name in ('startLocalProxy', 'uploadFilesToUrls'):
    response = json.loads(methods.handle({'jsonrpc': '2.0', 'method': name, 'id': 1}, methods.dispatcher_for_peer('test')))
    assert response['error']['code'] == -32601


def test_updater_cannot_select_unmodified_upstream(params, monkeypatch):
  from openpilot.system.updated.updated import Updater
  params.put('UpdaterTargetBranch', 'upstream', block=True)
  updater = Updater.__new__(Updater)
  updater.params = params
  assert updater.target_branch == 'master'
  monkeypatch.setattr(access_policy, 'ignition_state', lambda: False)
  assert methods.setUpdateBranch('upstream')['success'] == 0
  assert methods.setUpdateBranch('master')['success'] == 1


def test_model_choices_and_progress_come_from_device(params, monkeypatch):
  import time
  bundle = SimpleNamespace(ref='catalog-model', displayName='Device model', runner='tinygrad', status='downloading',
                           models=[SimpleNamespace(artifact=SimpleNamespace(fileName='model', downloadProgress=SimpleNamespace(progress=42)))])
  monkeypatch.setattr(models, 'get_cached_bundles', lambda p, source: [bundle])
  monkeypatch.setattr(models, 'get_selected_bundle', lambda p, source: bundle)
  sm = Mock()
  sm.seen = {'modelManagerSP': True}
  sm.logMonoTime = {'modelManagerSP': time.monotonic_ns()}
  sm.__getitem__ = Mock(return_value=SimpleNamespace(selectedBundle=bundle))
  monkeypatch.setattr(models, '_state', sm)
  state = models.getModelState('qcom')
  assert state['options'] == [{'id': 'catalog-model', 'name': 'Device model', 'runner': 'tinygrad'}]
  assert state['selected'] == 'catalog-model'
  assert state['download'] == {'id': 'catalog-model', 'status': 'downloading', 'progress': 42}
  assert state['available']
  sm.logMonoTime['modelManagerSP'] = time.monotonic_ns() - 10_000_000_000
  assert models.getModelState()['download'] is None
  assert not models.getModelState()['available']
