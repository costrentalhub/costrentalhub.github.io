import sqlite3
import unittest

from cost_rental_alerts.db import (
    close_all_open_for_source,
    close_unseen_open_listings,
    init_db,
    reconcile_stale_source_listings,
    upsert_listings,
)
from cost_rental_alerts.models import Listing


class StaleListingTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def _listing(self, listing_id: str, source: str, *, status: str = "open") -> Listing:
        return Listing(
            id=listing_id,
            source=source,
            title=listing_id,
            location="Dublin",
            url=f"https://example.test/{listing_id}",
            status=status,
            category="rent",
        )

    def test_close_unseen_open_listings(self):
        upsert_listings(
            self.conn,
            [
                self._listing("affordablehomes:open", "affordablehomes"),
                self._listing("affordablehomes:stale", "affordablehomes"),
            ],
        )

        closed = close_unseen_open_listings(
            self.conn,
            "affordablehomes",
            {"affordablehomes:open"},
        )
        self.conn.commit()

        self.assertEqual(closed, 1)
        row = self.conn.execute(
            "SELECT status FROM listings WHERE id = ?",
            ("affordablehomes:stale",),
        ).fetchone()
        self.assertEqual(row["status"], "closed")

    def test_close_all_open_for_source(self):
        upsert_listings(
            self.conn,
            [self._listing("oaklee:sidings", "oaklee")],
        )

        closed = close_all_open_for_source(self.conn, "oaklee")
        self.conn.commit()

        self.assertEqual(closed, 1)

    def test_reconcile_skips_failed_sources(self):
        upsert_listings(self.conn, [self._listing("tuath:balmoston", "tuath")])

        reconciled = reconcile_stale_source_listings(
            self.conn,
            successful_sources={"affordablehomes"},
            listings_by_source={"affordablehomes": {"affordablehomes:new"}},
        )

        self.assertEqual(reconciled, {})
        row = self.conn.execute(
            "SELECT status FROM listings WHERE id = ?",
            ("tuath:balmoston",),
        ).fetchone()
        self.assertEqual(row["status"], "open")


if __name__ == "__main__":
    unittest.main()
