import unittest

from cost_rental_alerts.scrapers.oaklee import scrape_oaklee


class OakleeScraperTests(unittest.TestCase):
    def test_scrape_ignores_case_study_links(self):
        html = """
        <html><body>
          <a href="/case-studies/the-sidings-admastown">The Sidings Adamstown</a>
        </body></html>
        """

        from unittest.mock import patch

        with patch("cost_rental_alerts.scrapers.oaklee.fetch", return_value=html):
            listings = scrape_oaklee()

        self.assertEqual(listings, [])


if __name__ == "__main__":
    unittest.main()
