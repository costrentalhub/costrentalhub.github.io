import unittest
from datetime import date

from cost_rental_alerts.models import Listing
from cost_rental_alerts.export_csv import resolve_export_status
from cost_rental_alerts.scrapers.affordablehomes import (
    _calendar_events,
    _parse_coming_soon_page,
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
            "https://newstarterhomes.ie/rent/blessingtondemesne/",
        )

    def test_parse_listing_page_marks_coming_soon_cards(self):
        html = """
        <article class="property soon df oh pr">
          <h3>Ard Raithní</h3>
          <p class="status fwb mz pa ttu">Coming Soon</p>
          <p class="df location fwm"><span>Bearna, Co. Galway</span></p>
          <footer>
            <p class="link mz"><a class="button" href="ardraithni2/">Read More</a></p>
          </footer>
        </article>
        """

        listings = _parse_listing_page(html)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].status, "coming_soon")

    def test_parse_coming_soon_page_keeps_rent_listings_only(self):
        html = """
        <article class="property upcoming df oh pr">
          <h3>Coola Meadows</h3>
          <h4 class="pa ln">Category</h4>
          <p>Properties to Buy</p>
          <footer><p class="link mz"><a class="button" href="/buy/coolameadows/">Read More</a></p></footer>
        </article>
        <article class="property upcoming df oh pr">
          <h3>Ard Raithní</h3>
          <h4 class="pa ln">Category</h4>
          <p>Properties to Rent</p>
          <p class="price fwm">Prices starting from €1,380</p>
          <p class="df location fwm"><span>Bearna, Co. Galway</span></p>
          <footer><p class="link mz"><a class="button" href="/rent/ardraithni2/">Read More</a></p></footer>
        </article>
        """

        listings = _parse_coming_soon_page(html)

        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0].title, "Ard Raithní")
        self.assertEqual(listings[0].status, "coming_soon")
        self.assertEqual(listings[0].url, "https://newstarterhomes.ie/rent/ardraithni2/")

    def test_coming_soon_survives_past_close_date_in_export(self):
        status = resolve_export_status(
            "coming_soon",
            "2025-08-31",
            "2025-09-14",
            today=date(2026, 8, 29),
        )
        self.assertEqual(status, "opening soon")


if __name__ == "__main__":
    unittest.main()
