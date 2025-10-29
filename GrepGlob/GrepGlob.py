import os
import re
import glob
import logging
from pathlib import Path
from typing import Optional, List

from utils.functions_metadata import function_schema
from config import config

logger = logging.getLogger(__name__)


@function_schema(
    name="GlobTool",
    description="Fast file pattern matching tool using glob patterns.",
    required_params=["pattern"],
    optional_params=["path", "max_results"]
)
def GlobTool(
    pattern: str,
    path: Optional[str] = None,
    max_results: Optional[int] = 1000
) -> str:
    """
    Find files matching a given pattern. Results are sorted by modification time.

    Parameters:
        pattern (str): Glob pattern to match files (e.g., '*.txt' or '**/*.py').
        path (str, optional): Directory path to search in. Defaults to config.workspace_path if not provided.
        max_results (int, optional): Maximum number of file paths to return. Defaults to 1000.

    Returns:
        - Newline-separated string of matching file paths sorted by modification time (newest first),
          limited to `max_results`. Returns an empty string if no matches are found.

    Raises:
        ValueError: If `pattern` is empty or if `path` does not exist / is not a directory.
    """
    # Input validation
    if not pattern:
        error_msg = "Pattern must be a non-empty string."
        logger.error(error_msg)
        raise ValueError(error_msg)


    if isinstance(max_results, str):
        try:
            max_results = int(max_results)
        except ValueError:
            logger.warning(f"GlobTool: Could not convert max_results '{max_results}' to int; using original value")

    try:
        # Resolve search path
        search_path = (
            Path(path).expanduser().resolve()
            if path
            else Path(config.workspace_path).expanduser().resolve()
        )

        if not search_path.exists() or not search_path.is_dir():
            error_msg = f"Search path '{search_path}' does not exist or is not a directory."
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"GlobTool: Searching for pattern '{pattern}' in '{search_path}'")

        # Construct the full glob pattern
        full_pattern = str(search_path / pattern)
        matches: List[str] = glob.glob(full_pattern, recursive=True)

        if not matches:
            logger.info("GlobTool: No matching files found.")
            return ""

        # Sort by modification time descending (newest first)
        matches_sorted = sorted(
            matches,
            key=lambda filepath: Path(filepath).stat().st_mtime,
            reverse=True
        )

        # Apply max_results limit
        if max_results is not None and isinstance(max_results, int) and max_results > 0:
            matches_sorted = matches_sorted[:max_results]

        return "\n".join(matches_sorted)

    except Exception as e:
        logger.error(f"GlobTool encountered an error: {str(e)}")
        return f"Error: {str(e)}"


@function_schema(
    name="GrepTool",
    description="Search file contents using regular expressions.",
    required_params=["pattern"],
    optional_params=["include", "path", "max_results", "max_files"]
)
def GrepTool(
    pattern: str,
    include: Optional[str] = None,
    path: Optional[str] = None,
    max_results: Optional[int] = 1000,
    max_files: Optional[int] = None
) -> str:
    """
    Search files for lines matching a given regular expression.

    Parameters:
        pattern (str): Regular expression to search for.
        include (str, optional): Glob pattern for filenames to include (e.g., '*.py'). 
                                 If not provided, all files are searched.
        path (str, optional): Directory path to search in. Defaults to config.workspace_path if not provided.
        max_results (int, optional): Maximum number of total match-lines to return. Defaults to 1000.
        max_files (int, optional): Maximum number of files to scan. If None, scans all files.

    Returns:
        - Newline-separated string of matches in the form "file_path: line <lineno>",
          limited to `max_results`. Returns an empty string if no matches are found.

    Raises:
        ValueError: If `pattern` is empty or if `path` does not exist / is not a directory.
    """
    import fnmatch

    # Input validation
    if not pattern:
        error_msg = "Pattern must be a non-empty string."
        logger.error(error_msg)
        raise ValueError(error_msg)

    if isinstance(max_results, str):
        try:
            max_results = int(max_results)
        except ValueError:
            logger.warning(f"GrepTool: Could not convert max_results '{max_results}' to int; using original value")
    if isinstance(max_files, str):
        try:
            max_files = int(max_files)
        except ValueError:
            logger.warning(f"GrepTool: Could not convert max_files '{max_files}' to int; using original value")

    try:
        # Resolve base path
        base_path = (
            Path(path).expanduser().resolve()
            if path
            else Path(config.workspace_path).expanduser().resolve()
        )

        if not base_path.exists() or not base_path.is_dir():
            error_msg = f"Search path '{base_path}' does not exist or is not a directory."
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(
            f"GrepTool: Searching for pattern '{pattern}' in '{base_path}' "
            f"with include='{include}', max_results={max_results}, max_files={max_files}"
        )

        # Pre-compile the regular expression for performance
        try:
            regex = re.compile(pattern)
        except re.error as compile_err:
            error_msg = f"Invalid regex pattern: {compile_err}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        results: List[str] = []
        files_scanned = 0
        matches_found = 0

        # Walk through the directory tree
        for root, dirs, files in os.walk(base_path):
            for filename in files:
                # If max_files is set and we've scanned enough, break out
                if max_files is not None and files_scanned >= max_files:
                    logger.info(f"GrepTool: Reached max_files limit ({max_files}). Stopping scan.")
                    break

                if include and not fnmatch.fnmatch(filename, include):
                    continue

                file_path = Path(root) / filename
                files_scanned += 1

                try:
                    with file_path.open('r', encoding='utf-8', errors='replace') as f:
                        for lineno, line in enumerate(f, start=1):
                            if regex.search(line):
                                match_info = f"{str(file_path)}: line {lineno}"
                                results.append(match_info)
                                matches_found += 1

                                # If we've collected enough matches, stop entirely
                                if max_results is not None and matches_found >= max_results:
                                    logger.info(
                                        f"GrepTool: Reached max_results limit ({max_results})."
                                    )
                                    break

                        # If we hit max_results inside this file, break out of file loop
                        if max_results is not None and matches_found >= max_results:
                            break

                except (UnicodeDecodeError, PermissionError) as file_err:
                    logger.warning(
                        f"GrepTool: Skipping file '{file_path}' due to read error: {file_err}"
                    )
                    continue

                # Check again if max_results reached after finishing a file
                if max_results is not None and matches_found >= max_results:
                    break

            # Check if max_files or max_results reached to break out of the directory walk
            if (
                (max_files is not None and files_scanned >= max_files) or
                (max_results is not None and matches_found >= max_results)
            ):
                break

        if not results:
            logger.info("GrepTool: No matches found.")
            return ""

        return "\n".join(results)

    except Exception as e:
        logger.error(f"GrepTool encountered an error: {str(e)}")
        return f"Error: {str(e)}"
