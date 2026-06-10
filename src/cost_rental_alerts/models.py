from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Listing:
    id: str
    source: str
    title: str
    location: str
    url: str
    status: str  # open | closed | opening soon
    category: str = "rent"
    price_from: Optional[float] = None
    bedrooms: Optional[str] = None
    quantity: Optional[int] = None
    income_min: Optional[float] = None
    income_max: Optional[float] = None
    applications_open_at: Optional[str] = None  # ISO date YYYY-MM-DD
    applications_close_at: Optional[str] = None
    listed_at: Optional[str] = None
    scheme_key: Optional[str] = None
    address: Optional[str] = None
