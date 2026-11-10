"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. See README.md → "Endpoints" for the full list
(better_business_bureau/api.py: company_details, company_reviews,
company_complaints, companies_search, companies_autocomplete,
categories_search, categories_autocomplete, locations_autocomplete).
Params go through the same schemas as the API, so the values are the
documented ones (`sort="newest"`, `type="delivery"`, ...).
"""
import json
import os

from better_business_bureau import api, schemas

os.makedirs("output", exist_ok=True)


def run(schema_cls, impl, **params):
    """Validate params exactly like the API does, then call the endpoint."""
    return impl(**schema_cls().load(params))


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a BBB business id or any bbb.org profile link: rating, accreditation,
    # contacts, owners, licenses, hours, alerts and review / complaint stats
    save("company_amazon.json", run(schemas.CompanySchema, api.company_details,
                                     company="1296-7039385"))

    # 15 businesses per page with BBB's own filters
    save("search_plumbers_beverly_hills.json", run(schemas.CompaniesSearchSchema, api.companies_search,
                                                   query="plumber", location="Beverly Hills, CA"))

    # 10 complaints per page with the full response thread
    save("complaints_amazon_delivery.json", run(schemas.CompanyComplaintsSchema, api.company_complaints,
                                                company="1296-7039385", type="delivery"))
