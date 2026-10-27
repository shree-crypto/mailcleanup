import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from mailtidy.unsubscribe import endpoint, post


def msg(sender='a@example.com', url='https://example.com/unsub'):
    return {'payload': {'headers': [{'name': 'From', 'value': sender}, {'name': 'List-Unsubscribe', 'value': f'<{url}>'}, {'name': 'List-Unsubscribe-Post', 'value': 'List-Unsubscribe=One-Click'}]}}


class UnsubscribeTest(unittest.TestCase):
    def test_endpoint_requires_sender_and_one_click(self):
        self.assertEqual(endpoint(msg(), 'a@example.com').hostname, 'example.com')
        with self.assertRaises(ValueError): endpoint(msg(), 'b@example.com')
        with self.assertRaises(ValueError): endpoint(msg(url='https://user@example.com/path'), 'a@example.com')
        with self.assertRaises(ValueError): endpoint(msg(url='http://example.com/path'), 'a@example.com')
        with self.assertRaises(ValueError): endpoint({'payload': {'headers': [{'name':'From','value':'a@example.com'}]}}, 'a@example.com')

    @patch('mailtidy.unsubscribe.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))])
    def test_private_address_rejected(self, resolve):
        with self.assertRaises(ValueError): post(urlsplit('https://example.com/unsub'))

if __name__ == '__main__': unittest.main()
