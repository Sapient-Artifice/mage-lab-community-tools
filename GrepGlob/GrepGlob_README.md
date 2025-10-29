# GrepGlob Tool

## Overview

**GrepGlob** provides two powerful search utilities for file system operations:

### 1. `GlobTool`
Fast file pattern matching using glob patterns.

#### Features:
- Search files using standard glob syntax (e.g., `*.txt`, `**/*.py`)
- Results sorted by modification time (newest first)
- Limit results with `max_results`
- Set search path with `path` (defaults to workspace path)

### 2. `GrepTool`
Search file contents using regular expressions.

#### Features:
- Match content using regex patterns
- Include files by glob pattern with `include`
- Limit scans with `max_files` and total matches with `max_results`
- Set search path with `path` (defaults to workspace path)

## Functions

### `GlobTool(pattern, path=None, max_results=1000)`
Find files matching a given pattern. Results are sorted by modification time.

**Arguments:**
- `pattern` *(str)*: Glob pattern to match files.
- `path` *(str, optional)*: Directory to search in (default: workspace path).
- `max_results` *(int, optional)*: Maximum number of matches to return.

**Returns:**  
Newline-separated list of file paths matched.

---

### `GrepTool(pattern, include=None, path=None, max_results=1000, max_files=None)`
Search files for lines matching a regular expression.

**Arguments:**
- `pattern` *(str)*: Regular expression to search for.
- `include` *(str, optional)*: Glob pattern to filter files (e.g., `*.py`).
- `path` *(str, optional)*: Directory to search in (default: workspace path).
- `max_results` *(int, optional)*: Maximum number of line matches to return.
- `max_files` *(int, optional)*: Maximum number of files to scan.

**Returns:**  
Newline-separated list of matched files and line numbers.

## Examples

### Using `GlobTool`
Find all Python files recursively:
```
GlobTool(pattern="**/*.py")
```

Find the 5 most recently modified text files in a directory:
```
GlobTool(pattern="*.txt", path="/home/user/docs", max_results=5)
```

---

### Using `GrepTool`
Search for error messages in Python files:
```
GrepTool(pattern="ERROR", include="*.py")
```

Search for function definitions across a project:
```
GrepTool(pattern="^def ", include="*.py", path="/home/user/project")
```


## License

This tool inherits the MIT License from the mage lab Community Tools repository.
