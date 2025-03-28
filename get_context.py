import os
import fnmatch
import sys

# --- Configuration ---
# Add directories or file patterns to exclude
# Uses Unix shell-style wildcards (fnmatch)
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "venv",
    "__pycache__",
    ".vscode",
    ".idea",
    # Add any other directories you want to skip entirely
}
EXCLUDE_FILES = {
    "*.pyc",
    "*.log",
    "*.lock",
    "*.exe", "*.dll", "*.bin", "*.obj", "*.o", "*.so",  # Binaries
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.ico", "*.webp",  # Images
    "*.zip", "*.tar.gz", "*.rar", "*.7z", "*.jar",  # Archives
    "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx",  # Documents
    "project_context.txt",  # Exclude the output file itself
    # Add any other file patterns
}

# Mapping file extensions to Markdown language hints
# Add more as needed
LANG_HINTS = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "cs": "csharp",
    "html": "html",
    "css": "css",
    "scss": "scss",
    "json": "json",
    "md": "markdown",
    "sh": "bash",
    "ps1": "powershell",
    "yaml": "yaml",
    "yml": "yaml",
    "sql": "sql",
    "dockerfile": "dockerfile",
    "txt": "text",
}
# --- End Configuration ---


def get_lang_hint(filename):
    """Gets the markdown language hint based on file extension."""
    _, ext = os.path.splitext(filename)
    return LANG_HINTS.get(ext.lower().lstrip('.'), ext.lstrip('.'))


def should_exclude(path, is_dir):
    """Checks if a file or directory should be excluded."""
    name = os.path.basename(path)
    patterns = EXCLUDE_DIRS if is_dir else EXCLUDE_FILES
    if name in patterns:
        return True
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def print_tree(start_path):
    """Prints a basic directory tree structure."""
    print("Project Directory Tree:")
    print("=======================")
    for root, dirs, files in os.walk(start_path, topdown=True):
        # Filter excluded directories *before* descending into them
        dirs[:] = [d for d in dirs if not should_exclude(
            os.path.join(root, d), True)]

        level = root.replace(start_path, '').count(os.sep)
        indent = ' ' * 4 * level
        print(f"{indent}{os.path.basename(root)}/")

        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            file_path = os.path.join(root, f)
            if not should_exclude(file_path, False):
                print(f"{sub_indent}{f}")
    print("\n")  # Add a newline


def process_files(start_path):
    """Processes and prints the content of non-excluded files."""
    print("File Contents:")
    print("==============")
    print("")  # Add a newline

    for root, dirs, files in os.walk(start_path, topdown=True):
        # Filter excluded directories again (important for the files loop)
        dirs[:] = [d for d in dirs if not should_exclude(
            os.path.join(root, d), True)]

        for filename in files:
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, start_path)

            if should_exclude(file_path, False):
                continue

            lang_hint = get_lang_hint(filename)

            # Use forward slashes for consistency
            print(f"--- File: {relative_path.replace(os.sep, '/')} ---")
            print(f"```{lang_hint}")
            try:
                # Try reading with UTF-8, fallback to latin-1 if needed
                # Add other encodings if necessary for your project
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='latin-1') as f:
                        content = f.read()
                except Exception as e:
                    content = f"[Error reading file: {e}]"
            except Exception as e:
                content = f"[Error reading file: {e}]"

            print(content)
            print("```")
            print("")  # Add a blank line for separation


# --- Main Execution ---
if __name__ == "__main__":
    project_root = os.getcwd()  # Get current working directory
    print_tree(project_root)
    process_files(project_root)
    print("=======================")
    print("--- End of Output ---")
# --- End of Script ---
