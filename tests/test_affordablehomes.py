import unittest
from datetime import date

from cost_rental_alerts.models import Listing
from cost_rental_alerts.scrapers.affordablehomes import (
    _calendar_events,
    _parse_listing_page,
    _resolve_calendar_dates,
)


class AffordableHomesCalendarTests(unittest.TestCase):
    def test_calendar_events_preserve_explicit_year(self):
        html = """
        <section aria-labelledby="year-2025" class="calendar oh">
          <h3 class="year"><button id="year-2025">2025</button></h3>
          <article class="calendar df">
            <h4><span>24</span><span class="fwb">Jun</span></h4>
            <div class="open">
              <a href="/rent/griffin-point-0625/">Griffin Point</a>
            </div>
          </article>
          <article class="calendar df">
            <h4><span>08</span><span class="fwb">Jul</span></h4>
            <div class="close">
              <a href="/rent/griffin-point-0625/">Griffin Point</a>
            </div>
          </article>
        </section>
        """

        events = _calendar_events(html)

        self.assertEqual(events["griffin-point-0625"]["opened"], date(2025, 6, 24))
        self.assertEqual(events["griffin-point-0625"]["closed"], date(2025, 7, 8))

    def test_explicit_calendar_year_prevents_false_opening_soon(self):
        listing = Listing(
            id="affordablehomes:griffin-point-0625",
            source="affordablehomes",
            title="Griffin Point",
            location="Griffin Point, Co. Dublin",
            url="https://affordablehomes.ie/rent/griffin-point-0625/",
            status="closed",
            listed_at="2025-06-24",
        )

        open_at, close_at = _resolve_calendar_dates(
            date(2025, 6, 24),
            date(2025, 7, 8),
            listing,
            date(2026, 6, 10),
        )

        self.assertEqual(open_at, "2025-06-24")
        self.assertEqual(close_at, "2025-07-08")

    def test_yearless_calendar_events_keep_existing_fallback(self):
        html = """
        <article class="calendar df">
          <h4><span>11</span><span class="fwb">Jun</span></h4>
          <div class="close">
            <a href="/rent/mountneil1/">Mountneil</a>
          </div>
        </article>
        """

        events = _calendar_events(html)

        self.assertEqual(events["mountneil1"]["closed"], (6, 11))

    def test_parse_listing_page_reads_new_portal_cards(self):
        html = """
        <article class="property open df oh pr">
          <h3>Ballycomyn, Blessington</h3>
          <p class="price fwm">Prices starting from €1,087</p>
          <p class="status fwb mz pa ttu">Applications Open</p>
          <p class="df location fwm"><span>Blessington, Co. Wicklow</span></p>
          <footer>
            <p class="link mz"><a class="button" href="blessingtondemesne/">Read More</a></p>
            <p class="date fsi">Listed: 25/08/2026</p>
          </footer>
        </article>
        """

        listings = _parse_listing_page(html)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].title, "Ballycomyn, Blessington")
        self.assertEqual(listings[0].id, "affordablehomes:blessingtondemesne")
        self.assertEqual(listings[0].status, "open")
        self.assertEqual(
            listings[0].url,
            "https://affordablehomes.ie/rent/blessingtondemesne/",
        )


if __name__ == "__main__":
    unittest.main()
