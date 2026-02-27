import os
import json
import requests
from urllib.parse import urljoin
from jira import JIRA
from jira.exceptions import JIRAError
from utils.functions_metadata import function_schema
from pathlib import Path
import logging 

from config import config

logger = logging.getLogger(__name__)

# Get environment variables
JIRA_ENDPOINT = os.getenv("JIRA_ENDPOINT")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_KEY = os.getenv("JIRA_API_KEY")

# Only create JIRA client if all required variables are set
jira = None

if JIRA_ENDPOINT and JIRA_EMAIL and JIRA_API_KEY:
    try:
        jira = JIRA(JIRA_ENDPOINT, basic_auth=(JIRA_EMAIL, JIRA_API_KEY))
        logger.info("Successfully connected to JIRA.")
    except JIRAError as e:
        logger.error(f"JIRA API error: {e.status_code} - {e.text}")
    except Exception as e:
        logger.error(f"Failed to connect to JIRA: {e}")
else:
    logger.info("JIRA environment variables are missing. Skipping JIRA client initialization.")

@function_schema(
    name="jira_create_issue",
    description="Create an issue. Optional args: description, issue_type, fields.",
    required_params=["project", "summary"],
    optional_params=["description", "issue_type", "fields"],
)
def jira_create_issue(
    project: str,
    summary: str,
    description: str = None,
    issue_type: str = 'Task',
    fields: dict = None,
) -> str:
    """
    Create a new JIRA issue.
    """
    try:
        issue_dict = {
            'project': {'key': project.upper()},
            'summary': summary,
            'description': description or '',
            'issuetype': {'name': issue_type},
        }
        if fields:
            issue_dict.update(fields)
        new_issue = jira.create_issue(fields=issue_dict)
        return f"Issue {new_issue.key} created successfully."
    except JIRAError as e:
        return f"An error occurred while creating the issue: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@function_schema(
    name="jira_edit_issue",
    description="Edit an issue using json fields.",
    required_params=["issue_key", "update_fields"],
)
def jira_edit_issue(
    issue_key: str,
    update_fields: str,
) -> str:
    """
    Edit an existing JIRA issue by parsing update_fields from a JSON string.
    """
    try:
        # Parse the JSON string into a dictionary
        fields_dict = json.loads(update_fields)
        issue = jira.issue(issue_key)
        issue.update(fields=fields_dict)
        return f"Issue {issue_key} updated successfully."
    except json.JSONDecodeError:
        return "Error: 'update_fields' must be a valid JSON string."
    except JIRAError as e:
        return f"An error occurred while editing the issue: {e.text.strip() or 'error'}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e) or 'error'}"

@function_schema(
    name="jira_transition_status",
    description="Transition an issue to the given status.",
    required_params=["issue_key", "status"],
    # optional_params=[],
)
def jira_transition_status(
    issue_key: str,
    status: str,
) -> str:
    """
    Transition an existing JIRA issue to a different status.
    """
    try:
        issue = jira.issue(issue_key)
        transitions = jira.transitions(issue)
        transition_id = None
        for t in transitions:
            if t['name'].lower() == status.lower():
                transition_id = t['id']
                break
        if not transition_id:
            available_statuses = [t['name'] for t in transitions]
            return (
                f"Transition to status '{status}' is not available for issue {issue_key}. "
                f"Available statuses: {', '.join(available_statuses)}."
            )
        jira.transition_issue(issue, transition_id)
        return f"Issue {issue_key} successfully transitioned to '{status}'."
    except JIRAError as e:
        return f"An error occurred while transitioning the issue: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@function_schema(
    name="jira_get_issue_details",
    description="Get details of an issue.",
    required_params=["issue_key"],
    # optional_params=[],
)
def jira_get_issue_details(issue_key: str) -> str:
    """
    Retrieve detailed information about a JIRA issue.
    """
    try:
        issue = jira.issue(issue_key)
        # Extract issue details
        key = issue.key
        summary = issue.fields.summary
        status = issue.fields.status.name
        assignee = issue.fields.assignee.displayName if issue.fields.assignee else "Unassigned"
        description = issue.fields.description or "No description provided."
        # Retrieve subtasks
        subtasks = issue.fields.subtasks
        subtask_lines = []
        if subtasks:
            subtask_lines.append("Subtasks:")
            for subtask in subtasks:
                subtask_key = subtask.key
                subtask_summary = subtask.fields.summary
                subtask_status = subtask.fields.status.name
                subtask_lines.append(f"- {subtask_key}: {subtask_summary} (Status: {subtask_status})")
        else:
            subtask_lines.append("No subtasks associated with this issue.")
        # Prepare the result
        result = (
            f"Issue Details:\n"
            f"- Key: {key}\n"
            f"- Summary: {summary}\n"
            f"- Status: {status}\n"
            f"- Assignee: {assignee}\n"
            f"- Description:\n{description}\n\n"
            + "\n".join(subtask_lines)
        )
        return result
    except JIRAError as e:
        return f"An error occurred while retrieving issue details: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@function_schema(
    name="jira_add_attachment",
    description="Add an attachment to an issue.",
    required_params=["issue_key", "attachment_path"],
    # optional_params=[],
)
def jira_add_attachment(issue_key: str, attachment_path: str) -> str:
    """
    Add an attachment to a JIRA issue.
    """
    target_dir = Path(config.workspace_path).expanduser().resolve()
    os.chdir(target_dir)
    try:
        resolved_path = Path(attachment_path).expanduser().resolve()
        issue = jira.issue(issue_key)
        if not resolved_path.is_file():
            return f"The attachment file '{resolved_path}' was not found."
        with resolved_path.open('rb') as file:
            jira.add_attachment(issue=issue, attachment=file)
        return f"Attachment '{resolved_path.name}' added to issue {issue_key}."
    except JIRAError as e:
        return f"An error occurred while adding the attachment: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@function_schema(
    name="jira_run_jql",
    description="Use a JQL query with the modern REST API.",
    required_params=["query"],
)
def jira_run_jql(query: str) -> str:
    """
    Execute a JQL query using the modern Atlassian REST API v3 via POST.
    """
    JIRA_ENDPOINT = os.getenv("JIRA_ENDPOINT")
    JIRA_EMAIL = os.getenv("JIRA_EMAIL")
    JIRA_API_KEY = os.getenv("JIRA_API_KEY")

    if not all([JIRA_ENDPOINT, JIRA_EMAIL, JIRA_API_KEY]):
        return "Error: Missing JIRA credentials (JIRA_ENDPOINT, JIRA_EMAIL, or JIRA_API_KEY)."

    # Prepare headers
    auth = (JIRA_EMAIL, JIRA_API_KEY)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Build the correct URL
    url = f"{JIRA_ENDPOINT.rstrip('/')}/rest/api/3/search/jql"

    # Payload
    payload = {
        "jql": query,
        "maxResults": 50,
        "fields": ["key", "summary", "status", "assignee"]
    }

    try:
        response = requests.post(url, json=payload, headers=headers, auth=auth)
        if response.status_code == 400:
            try:
                post_error = response.json().get("errorMessages", [])
            except Exception:
                post_error = []
            if any("Invalid request payload" in msg for msg in post_error):
                response = requests.get(
                    url,
                    params={
                        "jql": query,
                        "maxResults": 50,
                        "fields": ["key", "summary", "status", "assignee"],
                    },
                    headers={"Accept": "application/json"},
                    auth=auth,
                )

        response.raise_for_status()
        data = response.json()

        if "issues" not in data or not data["issues"]:
            return "No issues found for the provided JQL query."

        result_lines = ["Matching issues:"]
        for issue in data["issues"]:
            key = issue["key"]
            summary = issue["fields"].get("summary", "No summary")
            status = issue["fields"]["status"]["name"]
            assignee = issue["fields"]["assignee"]["displayName"] if issue["fields"].get("assignee") else "Unassigned"
            result_lines.append(f"- {key}: {summary} (Status: {status}, Assignee: {assignee})")

        return "\n".join(result_lines)

    except requests.exceptions.HTTPError as e:
        error_detail = "Unknown error"
        try:
            error_json = e.response.json()
            error_detail = error_json.get("errorMessages", [str(e)])[0]
        except:
            error_detail = e.response.text[:200]
        return f"HTTP error occurred: {e.response.status_code} - {error_detail}"
    except requests.exceptions.RequestException as e:
        return f"An error occurred while querying JIRA: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
def jira_comments(
    action: str,
    issue_key: str,
    content: str = None,
) -> str:
    """
    Manage comments on JIRA issues.
    """
    try:
        issue = jira.issue(issue_key)
        if action == 'add_comment':
            if not content:
                return "To add a comment, 'comment' text is required."
            jira.add_comment(issue, content)
            return f"Comment added to issue {issue_key}."
        elif action == 'read_comments':
            comments = issue.fields.comment.comments
            if not comments:
                return f"No comments found for issue {issue_key}."
            result_lines = [f"Comments for issue {issue_key}:"]
            for idx, c in enumerate(comments, 1):
                author = c.author.displayName
                created = c.created
                body = c.body
                result_lines.append(f"{idx}. {author} ({created}):\n{body}\n")
            return "\n".join(result_lines)
        else:
            return f"Invalid action '{action}'. Available actions: 'add_comment', 'read_comments'."
    except JIRAError as e:
        return f"An error occurred while managing comments: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@function_schema(
    name="jira_assign_issue",
    description="Assign a user to an issue.",
    required_params=["issue_key", "assignee"],
)
def jira_assign_issue(issue_key: str, assignee: str) -> str:
    """
    Assign a specific user to a JIRA task.

    Args:
        issue_key (str): The key of the issue to assign.
        assignee (str): The username or jira_user_email of the user to assign the issue to.

    Returns:
        str: A message indicating the result of the assignment operation.
    """
    try:
        # Assign the user to the issue
        jira.assign_issue(issue_key, assignee)
        return f"Issue {issue_key} successfully assigned to '{assignee}'."
    except JIRAError as e:
        return f"An error occurred while assigning the issue: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

@function_schema(
    name="get_jira_transitions",
    description="""
    Retrieve all available transition statuses for a specific JIRA issue, including their names and IDs.
    """,
    required_params=["issue_key"],
    optional_params=[],
)
def get_jira_transitions(issue_key: str) -> str:
    """
    Retrieve all available transition statuses for a specific JIRA issue.

    Args:
        issue_key (str): The key of the issue to retrieve transitions for.

    Returns:
        str: A formatted list of all available transitions for the issue, or an error message.
    """
    try:
        issue = jira.issue(issue_key)
        transitions = jira.transitions(issue)  # Retrieve available transitions
        if not transitions:
            return f"No transitions available for issue {issue_key}."

        result_lines = [f"Available transitions for issue {issue_key}:"]
        for transition in transitions:
            transition_id = transition['id']
            transition_name = transition['name']
            result_lines.append(f"- ID: {transition_id}, Name: {transition_name}")
        return "\n".join(result_lines)
    except JIRAError as e:
        return f"An error occurred while retrieving transitions for issue {issue_key}: {e.text.strip()}"
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"
