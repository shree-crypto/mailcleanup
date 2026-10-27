"""RFC 8058 one-click requests, restricted to public HTTPS endpoints."""
import email.utils
import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urlsplit

from . import core


def endpoint(message, sender):
    headers = {h['name'].lower(): h['value'] for h in message.get('payload', {}).get('headers', [])}
    if email.utils.parseaddr(headers.get('from', ''))[1].lower() != sender.lower():
        raise ValueError('Sender has changed')
    if headers.get('list-unsubscribe-post', '').strip().lower() != 'list-unsubscribe=one-click':
        raise ValueError('Sender does not advertise one-click unsubscribe')
    match = re.search(r'<(https://[^<>\s]+)>', headers.get('list-unsubscribe', ''), re.I)
    if not match:
        raise ValueError('No HTTPS one-click endpoint')
    url = urlsplit(match.group(1))
    if not url.hostname or url.username is not None or url.password is not None or url.fragment or url.port not in (None, 443):
        raise ValueError('Unsupported unsubscribe endpoint')
    return url


def post(url):
    # Resolve once, reject any private address, and connect to the validated address;
    # retain the hostname for certificate verification and SNI. Do not follow redirects.
    addresses = {entry[4][0] for entry in socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('Unsubscribe endpoint must resolve only to public addresses')
    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            raw = socket.create_connection((sorted(addresses)[0], 443), timeout=10)
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=url.hostname)
    connection = PinnedHTTPS(url.hostname, timeout=10)
    path = url.path or '/'
    if url.query:
        path += '?' + url.query
    try:
        connection.request('POST', path, body='List-Unsubscribe=One-Click', headers={'Content-Type': 'application/x-www-form-urlencoded'})
        response = connection.getresponse()
        status = response.status
        response.read(4096)
        if not 200 <= status < 300:
            raise ValueError(f'Unsubscribe endpoint returned HTTP {status}; redirects are not followed')
        return status
    finally:
        connection.close()


def unsubscribe(service, plan, sender):
    account = service.users().getProfile(userId='me').execute()['emailAddress'].lower()
    if account != plan['account']:
        raise ValueError('Plan belongs to another Gmail account')
    entries = [m for m in plan['messages'] if m['sender'].lower() == sender.lower() and m['one_click_available']]
    if not entries:
        raise ValueError('No one-click candidate for that sender in the plan')
    m = core.metadata(service, entries[0]['id'])
    return post(endpoint(m, sender))
