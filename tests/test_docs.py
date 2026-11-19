"""The list of docs pages: order, addresses, and a template for each."""

import unittest

from parkour import config, docs


class Docs(unittest.TestCase):
    def test_every_page_has_its_own_address_and_template(self):
        slugs = [page.slug for page in docs.PAGES]
        self.assertEqual(len(slugs), len(set(slugs)))
        for page in docs.PAGES:
            self.assertTrue((config.ROOT / "templates" / page.template).exists(), page.template)

    def test_previous_and_next_follow_the_contents_order(self):
        first, last = docs.PAGES[0], docs.PAGES[-1]
        self.assertEqual(docs.find(first.slug), (first, None, docs.PAGES[1]))
        self.assertEqual(docs.find(last.slug), (last, docs.PAGES[-2], None))
        self.assertIsNone(docs.find("no-such-page"))

    def test_each_page_belongs_to_a_group(self):
        for page in docs.PAGES:
            self.assertIn(page, docs.group_of(page).pages)


if __name__ == "__main__":
    unittest.main()
