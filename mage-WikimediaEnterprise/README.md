# Wikimedia Enterprise mage lab integration - Community Tool

## Overview
- Purpose: Fetch Wikimedia Enterprise articles on-demand by name and return article bodies plus useful metadata.
- How to use
  - Download `wikimedia_enterprise_api.py` and place it in `~/Mage/Tools/`
  - Configure credentials - instructions below
  - Restart mage lab & navigate to `Settings -> Tools`, then toggle the new Wikimedia Enterprise tools on

## Features
- **Search by name**: `wme_search_articles(name, limit=5, fields=None, filters=None, language=None, project=None)`
- **Get article**: `wme_get_article(name, fields=None, filters=None, language=None, project=None, max_chars=12000)`

## Requirements
- mage lab desktop application (`https://magelab.ai/downloads`)
- Wikimedia Enterprise account credentials or access token. Make your account here: https://enterprise.wikimedia.com/ 

## Credential Setup
This tool authenticates with Wikimedia Enterprise using username/password or a pre-issued access token.
It reads the following environment variables:
- `WME_USERNAME`: Your Wikimedia Enterprise username (email)
- `WME_PASSWORD`: Your Wikimedia Enterprise password
- `WME_ACCESS_TOKEN`: Optional. If provided, this is used instead of username/password.
- `WME_API_BASE`: Optional. Defaults to `https://api.enterprise.wikimedia.com/v2`
- `WME_AUTH_BASE`: Optional. Defaults to `https://auth.enterprise.wikimedia.com/v1`

### Where to put env vars
- By default, mage lab loads env vars from `~/.config/magelab/.env`.
- You can also open and edit the env file directly in the mage app via `Setting -> Paths` then choose "edit configuration file".
- Add the following as separate lines (adjust values as needed):

  WME_USERNAME=you@company.com
  WME_PASSWORD=your_password_here

  # Optional direct token override
  WME_ACCESS_TOKEN=your_access_token_here

## Usage Notes
- Article bodies: The API can return `article_body.wikitext` or `article_body.html`. Use `fields` to choose.
  - Example fields: `["name","url","abstract","article_body.wikitext"]`
- Filters: Provide filters as JSON or use the convenience params:
  - `language="en"` maps to `in_language.identifier`
  - `project="enwiki"` maps to `is_part_of.identifier`
  - Example JSON filters:
    `[{"field": "in_language.identifier", "value": "fr"}]`
- Truncation: `wme_get_article` trims the article body to `max_chars` (default 12000) to keep input sizes manageable.

## Common Troubleshooting
- Invalid credentials or 401/403:
  - Verify `WME_USERNAME` and `WME_PASSWORD`, or provide `WME_ACCESS_TOKEN`.
  - Ensure your account is enabled for the Enterprise API.
- Empty results:
  - Try specifying `language` or `project` filters to narrow results.
  - Check the article name spelling and capitalization.

## Security Best Practices
- Never commit `.env` files or tokens to version control.
- Rotate credentials periodically.

## Reference: Available Functions
- `wme_search_articles(name, limit=5, fields=None, filters=None, language=None, project=None)`
- `wme_get_article(name, fields=None, filters=None, language=None, project=None, max_chars=12000)`

License
This tool inherits the MIT License from the mage lab Community Tools repository.
