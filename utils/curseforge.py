"""
CurseForge API helpers.
"""

import json
import urllib.parse
import urllib.request
import urllib.error
import shutil

API_BASE = "https://api.curseforge.com/v1"


def _request_json(endpoint, api_key, params=None, timeout=20):
    url = f"{API_BASE}{endpoint}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "x-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read().decode("utf-8")
            return json.loads(data), None
    except urllib.error.HTTPError as exc:
        try:
            error_payload = exc.read().decode("utf-8")
        except Exception:
            error_payload = ""
        return None, f"HTTP {exc.code} {exc.reason} {error_payload}".strip()
    except Exception as exc:
        return None, str(exc)


def search_mods(api_key, params):
    return _request_json("/mods/search", api_key, params=params)


def get_mod(api_key, mod_id):
    return _request_json(f"/mods/{mod_id}", api_key)


def get_mod_files(api_key, mod_id, params=None):
    return _request_json(f"/mods/{mod_id}/files", api_key, params=params)


def get_mod_file(api_key, mod_id, file_id):
    return _request_json(f"/mods/{mod_id}/files/{file_id}", api_key)


def get_download_url(api_key, mod_id, file_id):
    return _request_json(f"/mods/{mod_id}/files/{file_id}/download-url", api_key)


def download_file(url, destination, timeout=60):
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response, open(destination, "wb") as handle:
        shutil.copyfileobj(response, handle)
