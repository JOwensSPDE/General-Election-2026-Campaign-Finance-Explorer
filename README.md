# Spotlight Delaware 2026 General Election Campaign Finance Explorer

A dependency-free static site for exploring Delaware's 2026 general-election candidates, candidate-committee reports, PAC activity and third-party advertising. It can be hosted directly on GitHub Pages.

The database includes every qualified candidate on the Delaware Department of Elections' general-election candidate list. Candidates without a supplied candidate-committee report remain visible and are labeled **No report available** rather than displayed with a misleading $0 total.

## Preview locally

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## Publish on GitHub Pages

1. Create a GitHub repository and add everything in this folder.
2. Open **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Choose the default branch and `/ (root)`, then save.

No build command or third-party JavaScript service is required.

## Rebuild the database

The rebuild requires Poppler's `pdftotext`. Save the official candidate-list HTML locally, then run:

```bash
PYTHONPATH=. python3 tools/build_general_database.py \
  "/path/to/30-Day" \
  "/path/to/genl_fcddt_2026.html" \
  data/campaign-finance.json \
  data/outside-spending.json
```

The builder:

- uses the official qualified-candidate roster;
- selects the latest amendment when multiple reports cover the same account and period;
- publishes PAC and political-committee profiles only when expenditures exceed $0;
- separates direct PAC contributions from independent spending;
- strips street addresses and ZIP codes from contributor locations; and
- reports unmatched candidate accounts and outside-spending review issues for editorial review.

The source archive used for this edition contains 30-day general-election filings. Candidate pages identify the exact period covered by each supplied report. PAC profiles combine supplied filings covering August 17 through October 4, 2026. Third-party advertiser data includes supplied reports through October 12, 2026. Candidate-level amounts from grouped expenditures are published only when the filing prints those allocations and they reconcile to the payment total.
