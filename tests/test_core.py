import unittest
from mailtidy.core import eligible, review


def message(labels, date=1000, sender='Shop <sales@example.com>'):
    return {'id': 'a', 'labelIds': labels, 'internalDate': str(date), 'payload': {'headers': [{'name': 'From', 'value': sender}]}}


class RulesTest(unittest.TestCase):
    def test_only_old_unprotected_promotions(self):
        self.assertTrue(eligible(message(['CATEGORY_PROMOTIONS']), 2000, set()))
        for label in ['UNREAD', 'STARRED', 'IMPORTANT', 'TRASH', 'SPAM', 'DRAFT', 'SENT']:
            self.assertFalse(eligible(message(['CATEGORY_PROMOTIONS', label]), 2000, set()))
        self.assertFalse(eligible(message(['INBOX']), 2000, set()))
        self.assertFalse(eligible(message(['CATEGORY_PROMOTIONS'], 3000), 2000, set()))
        self.assertFalse(eligible(message(['CATEGORY_PROMOTIONS'], 0), 2000, set()))

    def test_keep_address_and_domain(self):
        m = message(['CATEGORY_PROMOTIONS'])
        self.assertFalse(eligible(m, 2000, {'sales@example.com'}))
        self.assertFalse(eligible(m, 2000, {'example.com'}))
        self.assertFalse(eligible(message(['CATEGORY_PROMOTIONS'], sender=''), 2000, set()))

    def test_review_groups(self):
        plan = {'messages': [{'sender': 'a@example.com', 'subject': 'One', 'one_click_available': True}, {'sender': 'a@example.com', 'subject': 'Two', 'one_click_available': False}]}
        group = review(plan)[0]
        self.assertEqual(group['count'], 2)
        self.assertEqual(group['samples'], ['One', 'Two'])
        self.assertTrue(group['one_click_available'])

if __name__ == '__main__':
    unittest.main()
