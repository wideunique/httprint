import base64
import importlib.util
import json
import logging
from ipaddress import ip_network
from pathlib import Path
from types import SimpleNamespace

import tornado.web
from tornado.testing import AsyncHTTPTestCase


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    mod_path = repo_root / "httprint.py"
    spec = importlib.util.spec_from_file_location("httprint", mod_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader, "cannot load module spec"
    spec.loader.exec_module(mod)
    return mod


httprint = _load_module()


class _DummyHandler(httprint.BaseHandler):
    def get(self):
        self.write({"ok": True})


def _make_cfg(**overrides):
    defaults = dict(
        ip_whitelist_networks=[],
        auth_username='',
        auth_password='',
        demo=True,
        print_cmd='echo print %(copies)s %(sides)s %(media)s',
        queue_dir='tmp/test_queue',
        archive=False,
        archive_dir='tmp/test_archive',
        check_pdf_pages=False,
        pdf_only=False,
        max_pages=10,
        print_with_code=False,
        code_digits=4,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_app(cfg):
    logger = logging.getLogger('httprint.test')
    init_params = dict(cfg=cfg, logger=logger, listen_port=0, ssl_options=None)
    return tornado.web.Application([(r'/', _DummyHandler, init_params)])


class TestWhitelistSkipsBasicAuth(AsyncHTTPTestCase):
    def get_app(self):
        cfg = _make_cfg(
            ip_whitelist_networks=[ip_network('127.0.0.1/32')],
            auth_username='user',
            auth_password='secret'
        )
        self.cfg = cfg
        return _make_app(cfg)

    def test_whitelisted_ip_allows_request(self):
        response = self.fetch('/')
        assert response.code == 200
        body = json.loads(response.body.decode('utf-8'))
        assert body == {"ok": True}


class TestBasicAuthRequired(AsyncHTTPTestCase):
    def get_app(self):
        cfg = _make_cfg(auth_username='user', auth_password='secret')
        self.cfg = cfg
        return _make_app(cfg)

    def test_missing_credentials_rejected(self):
        response = self.fetch('/', raise_error=False)
        assert response.code == 401

    def test_invalid_credentials_rejected(self):
        token = base64.b64encode(b'user:wrong').decode('ascii')
        headers = {'Authorization': f'Basic {token}'}
        response = self.fetch('/', headers=headers, raise_error=False)
        assert response.code == 401

    def test_valid_credentials_allowed(self):
        token = base64.b64encode(b'user:secret').decode('ascii')
        headers = {'Authorization': f'Basic {token}'}
        response = self.fetch('/', headers=headers)
        assert response.code == 200
        body = json.loads(response.body.decode('utf-8'))
        assert body == {"ok": True}


class TestForwardedForWhitelist(AsyncHTTPTestCase):
    def get_app(self):
        cfg = _make_cfg(
            ip_whitelist_networks=[ip_network('192.168.5.0/24')],
            auth_username='user',
            auth_password='secret'
        )
        self.cfg = cfg
        return _make_app(cfg)

    def test_forwarded_ip_whitelisted(self):
        headers = {'X-Forwarded-For': '192.168.5.10'}
        response = self.fetch('/', headers=headers)
        assert response.code == 200
        body = json.loads(response.body.decode('utf-8'))
        assert body == {"ok": True}

    def test_forwarded_ip_requires_basic_when_not_whitelisted(self):
        token = base64.b64encode(b'user:secret').decode('ascii')
        headers = {
            'X-Forwarded-For': '10.0.0.5',
            'Authorization': f'Basic {token}'
        }
        response = self.fetch('/', headers=headers)
        assert response.code == 200

        missing_auth = {'X-Forwarded-For': '10.0.0.5'}
        rejected = self.fetch('/', headers=missing_auth, raise_error=False)
        assert rejected.code == 401
