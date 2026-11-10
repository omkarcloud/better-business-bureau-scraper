# 🏢 Better Business Bureau Scraper

Better Business Bureau Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Better Business Bureau data for free.

## ✨ What Can I Get?

- 🏢 **Full BBB profiles of 6.3M+ businesses** — rating, accreditation, owners, phones, websites, licenses & hours
- 💬 **Every review and complaint, word for word** — star ratings, complaint type & status, and the business's replies
- 🎯 **Lead lists for any trade, anywhere** — plumbers in Beverly Hills, roofers near any ZIP: phones, addresses & service areas
- ✅ **380K+ BBB Accredited Businesses, one filter away** — A+ to F grades, accreditation dates, government actions & alerts

## 🎥 Example: A Full BBB Business Profile

```json
{
  "id": "1296-7039385",
  "name": "Amazon.com",
  "link": "https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385",
  "rating": { "grade": "A+", "is_rated": true },
  "accreditation": { "is_accredited": true, "since": "1996-08-01" },
  "entity_type": "Corporation",
  "years_in_business": 31,
  "number_of_employees": 1300000,
  "categories": { "primary": { "id": "65974-000", "name": "Ecommerce" } },
  "contact": {
    "phone": "(888) 280-4331",
    "fax_numbers": [{ "value": "(206) 266-1838", "label": "Primary Fax" }],
    "websites": ["https://www.amazon.com/contact", "https://www.amazonfresh.com"]
  },
  "people": [
    { "name": "Mr. Jeff Bezos", "title": "Founder", "is_principal": true },
    { "name": "Mr. Andy Jassy", "title": "CEO", "is_principal": true }
  ],
  "address": { "street": "202 Westlake Ave N Ste 2", "city": "Seattle", "state": "WA", "postal_code": "98109-5264" },
  "location": { "latitude": 47.620049, "longitude": -122.338104 },
  "licenses": { "items": [{ "number": "601720490", "agency": { "name": "Washington Secretary of State" } }] },
  "social_media": [{ "type": "linkedin", "link": "https://www.linkedin.com/company/amazon" }],
  "reviews_summary": { "count": 4696, "average_rating": 1.1 },
  "complaints_summary": { "count": 10000, "closed_last_3_years": 61402, "closed_last_12_months": 17753 },
  "locations": { "count": 20 },
  "bbb_office": { "name": "BBB Great West + Pacific", "link": "https://www.bbb.org/local-bbb/bbb-great-west-pacific" }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Better Business Bureau Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/better-business-bureau-scraper
cd better-business-bureau-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/companies/details?company=1296-7039385"
```

```json
{
  "id": "1296-7039385",
  "name": "Amazon.com",
  "link": "https://www.bbb.org/us/wa/seattle/profile/ecommerce/amazoncom-1296-7039385",
  "rating": { "grade": "A+", "is_rated": true },
  "accreditation": { "is_accredited": true, "since": "1996-08-01" },
  "years_in_business": 31,
  "number_of_employees": 1300000,
  "contact": { "phone": "(888) 280-4331", "websites": ["https://www.amazon.com/contact", "https://www.amazonfresh.com"] },
  "people": [
    { "name": "Mr. Jeff Bezos", "title": "Founder" },
    { "name": "Mr. Andy Jassy", "title": "CEO" }
  ],
  "address": { "street": "202 Westlake Ave N Ste 2", "city": "Seattle", "state": "WA", "postal_code": "98109-5264" },
  "reviews_summary": { "count": 4696, "average_rating": 1.1 },
  "complaints_summary": { "count": 10000, "closed_last_12_months": 17753 }
}
```

All 8 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

8 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Company Details | `/companies/details` | Everything BBB knows about one business, in a single call |
| Company Reviews | `/companies/reviews` | Customer reviews with stars, full text and replies, 10 per page |
| Company Complaints | `/companies/complaints` | Complaints with type, status and the full response thread, 10 per page |
| Search Companies | `/companies/search` | 15 businesses per page; filter by grade, city, category, accreditation |
| Company Autocomplete | `/companies/autocomplete` | Typeahead for business names with id, link and address |
| Search by Category | `/categories/search` | Every business in a category near any city, 15 per page |
| Category Autocomplete | `/categories/autocomplete` | Typeahead for BBB categories with code and slug |
| Location Autocomplete | `/locations/autocomplete` | Typeahead for cities, states and ZIP codes with coordinates |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-better-business-bureau-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-better-business-bureau-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-better-business-bureau-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/companies/details",
    params={"company": "1296-7039385"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Better Business Bureau Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/better-business-bureau-scraper-github-whatsapp)

[![Ask Us by Email about Better Business Bureau Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Better%20Business%20Bureau%20Scraper%20API&body=I%20need%20help%20using%20the%20Better%20Business%20Bureau%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**Yelp Scraper**](https://www.omkar.cloud/tools/yelp-scraper) — Yelp businesses, reviews, photos & menus
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/better-business-bureau-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/better-business-bureau-scraper)
