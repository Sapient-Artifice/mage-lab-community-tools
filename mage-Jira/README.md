# Jira mage lab integration - Community Tool

## Overview
- Purpose: Simple, ready-to-use mage integration for Jira Cloud - create, edit, transition, assign, comment on issues, run JQL, and add attachments using the `jira` Python library.
- How to use 
   - Download `jira_api-py` and place it in `~/Mage/Tools/`
   - Configure credentials - instructions below
   - Restart mage lab & navigate to `Settings -> Tools`, then toggle new Jira tools on

## Features
- **Create issues**: `jira_create_issue(project, summary, description?, issue_type?, fields?)`
- **Edit issues**: `jira_edit_issue(issue_key, update_fields_json)`
- **Transition status**: `jira_transition_status(issue_key, status)`
- **Get details**: `jira_get_issue_details(issue_key)`
- **Add attachment**: `jira_add_attachment(issue_key, attachment_path)`
- **Run JQL**: `jira_run_jql(query)`
- **Comments**: `jira_comments(action, issue_key, content?)` where action is `add_comment` or `read_comments`
- **Assign issue**: `jira_assign_issue(issue_key, assignee)`

## Requirements
- mage lab desktop application (`https://magelab.ai/downloads`)
- Jira: Atlassian Jira Cloud (recommended). Works with a Jira account that has permissions to browse projects, create and edit issues, transition issues, add comments, assign, and add attachments in the target projects.

## Credential Setup
This tool authenticates with Jira using Basic Auth (email + API token). It reads three environment variables:
- `JIRA_ENDPOINT`: Your site base URL, e.g. `https://your-domain.atlassian.net`
- `JIRA_EMAIL`: Your Atlassian account email, e.g. `you@company.com`
- `JIRA_API_KEY`: Your Atlassian API token (generated from your Atlassian account) 

### How to get a Jira API token (Atlassian Cloud)
  1) Sign in to https://id.atlassian.com/manage-profile/security/api-tokens
  2) Click “Create API token”, give it a label, and create it.
  3) Copy the token and paste it into `JIRA_API_KEY` in your `.env`.
  4) Ensure the Atlassian user tied to the token has the necessary project permissions (e.g., Browse Projects, Create Issues, Edit Issues, Transition Issues, Add Comments, Assign Issues, and Add Attachments) in the target projects. 

For more info `https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/`

### Where to put env vars
- By default, mage lab loads env vars from `~/.config/magelab/.env`.
- You can also open and edit the env file from directly in the mage app via `Setting -> Paths` then choose "edit configuration file"
- Add the following as three separate lines, like below - adjust values to your instance/account:
   JIRA_ENDPOINT=https://your-domain.atlassian.net
   JIRA_EMAIL=you@company.com
   JIRA_API_KEY=your_api_token_here


## Usage Notes
- Attachment paths: `jira_add_attachment` resolves paths relative to mage lab’s `WORKSPACE_PATH` (default `~/Mage/Workspace`). You can pass an absolute path or a path inside that workspace.
- Issue types: The default is `Task`. For company-managed projects with custom issue types, pass `issue_type` explicitly or include in `fields`.
- Editing fields: `jira_edit_issue` expects a JSON string for `update_fields`. Example:

  update_fields = '{"priority": {"name": "High"}, "labels": ["api", "automation"]}'
  jira_edit_issue("ABC-123", update_fields)

- Transitions: `jira_transition_status` matches transition name (case-insensitive). If a transition is not available, the function returns the list of valid statuses for that issue.
- Comments: Use `jira_comments("add_comment", "ABC-123", content="Hello from API")` or `jira_comments("read_comments", "ABC-123")`.
- Assigning: Use either the user’s username (in Server/DC) or the Atlassian account identifier (email works for Cloud tenants with appropriate directory settings). Example: `jira_assign_issue("ABC-123", "you@company.com")`.

## Common Troubleshooting
- Invalid credentials or 401/403:
  - Re-check `JIRA_ENDPOINT` hostname and protocol (must be your site root, e.g. `https://your-domain.atlassian.net`).
  - Confirm `JIRA_EMAIL` is the same account used to create the API token.
  - Regenerate the API token if unsure and update `.env`.
- Transition not available:
  - The issue’s current status and workflow may not allow that transition.
  - Ensure the user has “Transition issues” permission and the workflow includes the target status.
- Attachments fail:
  - Confirm the file exists and is readable; use an absolute path to be sure.
  - Ensure the project allows attachments and that the user has “Create attachments” permission.

## Security Best Practices
- Never commit `.env` files or tokens to version control.
- Restrict token permissions via project roles and permission schemes.
- Rotate tokens periodically and revoke unused tokens.

## Reference: Available Functions
- `jira_create_issue(project, summary, description=None, issue_type='Task', fields=None)`
- `jira_edit_issue(issue_key, update_fields)`  # `update_fields` is a JSON string
- `jira_transition_status(issue_key, status)`
- `jira_get_issue_details(issue_key)`
- `jira_add_attachment(issue_key, attachment_path)`
- `jira_run_jql(query)`
- `jira_comments(action, issue_key, content=None)`
- `jira_assign_issue(issue_key, assignee)`

## Notes for Contributors
- This module depends on mage lab’s `config` to load `.env` via `python-dotenv`. If you run it outside mage lab, ensure your environment variables are exported or a compatible dotenv loader is used before import.
- Library: https://github.com/pycontribs/jira

License
This tool inherits the MIT License from the mage lab Community Tools repository.

