"""Fixed program streamed to an empty OpenShell operation sandbox. No Prime code."""
import base64
import json
import os
import re
import ssl
import sys
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    request = json.loads(sys.stdin.buffer.read(4097))
    if set(request) != {'origin', 'path', 'style'} or not re.fullmatch(r'/[A-Za-z0-9_./-]{1,240}', request['path']):
        raise ValueError()
    placeholder = os.environ['PRIME_UPSTREAM_TOKEN']
    # The provider value is the complete base64 Basic value. Header substitution
    # happens at the inspected proxy, not in this process.
    if request['style'] == 'basic':
        header = 'Basic '+placeholder
    elif request['style'] == 'bearer':
        header = 'Bearer '+placeholder
    else:
        raise ValueError()
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    message = urllib.request.Request(request['origin']+request['path'],
        headers={'Authorization': header, 'Accept': 'application/json', 'User-Agent': 'Prime-Connections/2'})
    with opener.open(message, timeout=10) as response:
        if (response.status != 200 or response.headers.get('Content-Encoding', 'identity') != 'identity'
                or response.headers.get_content_type() != 'application/json'):
            raise ValueError()
        raw = response.read(1024*1024+1)
    if len(raw) > 1024*1024:
        raise ValueError()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError()
    print(json.dumps(data), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No traceback, response body or environment in sandbox/host logs.
        raise SystemExit(1)
