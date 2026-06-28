import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cost_rental_alerts.check_links import LinkFailure, active_scheme_links, find_broken_links


class CheckLinksTests(unittest.TestCase):
    def test_active_scheme_links_skips_closed_rows(self):
        csv_text = """name,status,source,link
Open Scheme,open,lda,https://example.test/open
Closed Scheme,closed,tuath,https://example.test/closed
Soon Scheme,opening soon,affordablehomes,https://example.test/soon
"""
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write(csv_text)
            csv_path = Path(handle.name)

        try:
            links = active_scheme_links(csv_path)
        finally:
            csv_path.unlink()

        self.assertEqual(
            links,
            [
                ("Open Scheme", "lda", "https://example.test/open"),
                ("Soon Scheme", "affordablehomes", "https://example.test/soon"),
            ],
        )

    def test_find_broken_links_reports_http_errors(self):
        rows = [
            ("Broken", "tuath", "https://example.test/broken"),
        ]

        with patch("cost_rental_alerts.check_links.active_scheme_links", return_value=rows):
            with patch(
                "cost_rental_alerts.check_links.check_url",
                return_value=(404, "Not Found"),
            ):
                failures = find_broken_links()

        self.assertEqual(
            failures,
            [
                LinkFailure(
                    name="Broken",
                    source="tuath",
                    url="https://example.test/broken",
                    status=404,
                    detail="Not Found",
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
