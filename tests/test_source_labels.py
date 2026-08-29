import unittest

from cost_rental_alerts.source_labels import canonical_listing_url, display_source


class SourceLabelTests(unittest.TestCase):
    def test_display_source_uses_portal_name(self):
        self.assertEqual(display_source("affordablehomes"), "New Starter Homes")
        self.assertEqual(display_source("tuath"), "Tuath Housing")

    def test_canonical_listing_url_rewrites_ah_domain(self):
        self.assertEqual(
            canonical_listing_url(
                "affordablehomes",
                "https://affordablehomes.ie/rent/ancnocan1/",
            ),
            "https://newstarterhomes.ie/rent/ancnocan1/",
        )


if __name__ == "__main__":
    unittest.main()
