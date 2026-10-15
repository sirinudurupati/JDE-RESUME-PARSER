"""Where uploaded resume files live: local disk by default, a private Supabase Storage bucket when
SUPABASE_URL + SUPABASE_SERVICE_KEY are set (so a host without a persistent disk loses nothing)."""
import json
import urllib.error
import urllib.parse
import urllib.request

from . import config


def _remote():
    return config.supabase_storage()


def _call(method, path, data=None, content_type=None):
    base, key, _ = _remote()
    req = urllib.request.Request(f"{base}/storage/v1/{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("apikey", key)
    if content_type:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _object(name):
    return f"object/{urllib.parse.quote(_remote()[2])}/{urllib.parse.quote(name)}"


def init():
    if _remote():
        body = json.dumps({"id": _remote()[2], "name": _remote()[2], "public": False}).encode()
        try:
            _call("POST", "bucket", body, "application/json")        # private bucket
        except urllib.error.HTTPError:
            pass                                                     # already exists
    else:
        config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def put(name, data):
    if _remote():
        _call("POST", _object(name), data, "application/octet-stream")
    else:
        (config.UPLOAD_DIR / name).write_bytes(data)


def get(name):
    """-> bytes, or None when the file is gone."""
    if not name:
        return None
    if _remote():
        try:
            return _call("GET", _object(name))
        except urllib.error.HTTPError:
            return None
    p = (config.UPLOAD_DIR / name).resolve()
    if config.UPLOAD_DIR.resolve() not in p.parents or not p.exists():
        return None
    return p.read_bytes()


def delete(name):
    if not name:
        return
    if _remote():
        try:
            _call("DELETE", _object(name))
        except urllib.error.HTTPError:
            pass
        return
    p = (config.UPLOAD_DIR / name).resolve()
    if config.UPLOAD_DIR.resolve() in p.parents and p.exists():
        p.unlink()
