# scripts/context_manager.py

import os
import subprocess
import argparse
import re
import sys
# import pyperclip  # REMOVED
from datetime import datetime
import logging

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, 'data', 'context_logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE_BASE = os.path.join(
    LOG_DIR, f"context_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(f"{LOG_FILE_BASE}.log"), logging.StreamHandler()])

ALWAYS_INCLUDE_FILES = [
    'config/settings.py',
    'config/config.yaml',
    # 'src/main_trader.py', # Optionally add key files for old workflow
    'scripts/context_manager.py'  # Include itself
]
TREE_IGNORE_PATTERNS = ['.venv', '__pycache__', 'data', '.git',
                        # Exclude SSoT/context from tree
                        '*.db', '*.log', '*.sqlite3', 'node_modules', 'dist', 'build', 'SSOT.md', 'context_for_llm.*']
# --- End Configuration ---


class ContextManager:
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.handover_content = None  # Can be None if using file-based workflow
        self.parsed_info = {'modified': [], 'next_step_files': set(
        ), 'phase': '?', 'module': '?'}  # Default empty
        self.is_ssot_update_mode = False  # Flag to track mode

    def set_handover_content(self, text):
        """Sets the handover content and triggers parsing (for old workflow)."""
        if not text:
            logging.warning("Handover text provided is empty.")
            self.handover_content = ""
            return  # Don't parse if empty
        self.handover_content = text
        self.parsed_info = self._parse_handover()

    def _read_file(self, file_path):
        """Safely reads a file's content."""
        if not os.path.isabs(file_path) and not file_path.startswith(self.project_root):
            full_path = os.path.join(self.project_root, file_path)
        else:
            full_path = file_path

        try:
            if not os.path.exists(full_path):
                logging.warning(
                    f"File specified for inclusion/reading not found, skipping: {full_path}")
                return None

            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logging.warning(f"File not found during read attempt: {full_path}")
            return None
        except Exception as e:
            logging.error(f"Error reading file {full_path}: {e}")
            return None

    def _parse_handover(self):
        """Parses key information from the handover document content (for old workflow)."""
        if self.handover_content is None:
            logging.warning("Handover content not set, cannot parse.")
            return self.parsed_info
        if not self.handover_content:
            logging.warning("Cannot parse empty handover content.")
            return self.parsed_info

        # --- Parsing logic remains the same ---
        parsed = {'modified': [], 'next_step_files': set(), 'phase': '?',
                  'module': '?'}
        try:
            modified_match = re.search(r"^\s*Key Files/Modules Implemented or Modified \(Session\):?\s*\n(.*?)(?=\n\s*\n|\Z)",
                                       self.handover_content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
            if modified_match:
                modified_block = modified_match.group(1).strip()
                parsed['modified'] = [line.strip()[2:] for line in modified_block.split(
                    '\n') if line.strip().startswith('- ')]

            next_steps_match = re.search(r"^\s*Actionable Next Steps:?\s*\n(.*?)(?=\n\s*\n|\Z)",
                                         self.handover_content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
            if next_steps_match:
                next_steps_block = next_steps_match.group(1).strip()
                potential_paths = re.findall(
                    r'(?:^|\s)(src|config|scripts|notebooks|tests)/[\w/.-]+\.(?:py|yaml|sql|md|ipynb)', next_steps_block, re.IGNORECASE)
                for path in potential_paths:
                    parsed['next_step_files'].add(path.strip('`\'" '))

            roadmap_match = re.search(
                r"Phase \[?([\d.]+)\]?(?:, Module \[?([\d.]+)\]?)?", self.handover_content, re.IGNORECASE)
            if roadmap_match:
                parsed['phase'] = roadmap_match.group(1)
                if len(roadmap_match.groups()) > 1 and roadmap_match.group(2):
                    parsed['module'] = roadmap_match.group(2)

            logging.info(
                f"Parsed Handover: Modified={parsed['modified']}, NextStepsFiles={list(parsed['next_step_files'])}, Phase={parsed['phase']}, Module={parsed['module']}")
            return parsed

        except Exception as e:
            logging.error(f"Failed to parse handover document: {e}")
            return {'modified': [], 'next_step_files': set(), 'phase': '?', 'module': '?'}

    def generate_tree(self):
        """Generates a string representation of the directory tree."""
        # --- Tree generation logic remains the same ---
        lines = []
        ignore_set = set(TREE_IGNORE_PATTERNS)

        def is_ignored(name, patterns):
            if name in patterns:
                return True
            if any(pat.startswith('*') and name.endswith(pat[1:]) for pat in patterns if '*' in pat):
                return True
            if any(pat.endswith('*') and name.startswith(pat[:-1]) for pat in patterns if '*' in pat):
                return True
            return False

        lines.append("Project Structure:")
        for root, dirs, files in os.walk(self.project_root, topdown=True):
            rel_root = os.path.relpath(root, self.project_root)
            if rel_root == '.':
                rel_root = ''

            dirs[:] = [d for d in dirs if not is_ignored(d, ignore_set)]
            files = [f for f in files if not is_ignored(f, ignore_set)]

            level = rel_root.count(os.sep) if rel_root else 0
            indent = ' ' * 4 * level
            dir_name = os.path.basename(
                root) if rel_root else os.path.basename(self.project_root)

            if level == 0 and dir_name == os.path.basename(self.project_root):
                pass
            elif dir_name:
                lines.append(f"{indent}├── {dir_name}/")

            subindent = ' ' * 4 * (level + 1)
            display_files = sorted([f for f in files if f != '.gitkeep'])
            for i, f in enumerate(display_files):
                connector = "└──" if i == len(display_files) - 1 else "├──"
                lines.append(f"{subindent}{connector} {f}")

        return "\n".join(lines)

    def build_context_prompt(self):
        """Builds the final context string for the LLM (for old workflow)."""
        if self.is_ssot_update_mode:
            logging.error(
                "build_context_prompt called in SSoT update mode. This is incorrect.")
            return "Error: build_context_prompt called incorrectly."
        if self.handover_content is None:
            logging.error(
                "build_context_prompt called but handover content was never set.")
            return "Error: Handover content missing."

        context_parts = []
        context_parts.append(
            "--- Start GeminiTrader Context Block (Selective Files) ---")
        context_parts.append(
            f"Context generated on: {datetime.now().isoformat()}")
        context_parts.append(
            f"Targeting: Phase {self.parsed_info['phase']}, Module {self.parsed_info['module']}")
        context_parts.append("\n---\n")
        context_parts.append("## Last Session Handover Document:")
        context_parts.append(self.handover_content)
        context_parts.append("\n---\n")
        context_parts.append("## Project Directory Structure:")
        context_parts.append(self.generate_tree())
        context_parts.append("\n---\n")
        context_parts.append("## Relevant File Contents:")
        files_to_include = set(ALWAYS_INCLUDE_FILES) | set(
            self.parsed_info['modified']) | self.parsed_info['next_step_files']
        processed_files = set()
        for file_rel_path in sorted(list(files_to_include)):
            clean_path = file_rel_path.strip(' `\'"')
            if not clean_path:
                continue
            if not any(clean_path.startswith(prefix) for prefix in ['src/', 'config/', 'scripts/', 'notebooks/', 'tests/', 'README.md']):
                logging.warning(
                    f"Skipping potentially invalid or root path in old workflow: {clean_path}")
                continue
            if clean_path in processed_files:
                continue
            processed_files.add(clean_path)
            content = self._read_file(clean_path)
            if content is not None:
                context_parts.append(f"\n### File: {clean_path}\n")
                lang = "python"
                if clean_path.endswith(".yaml"):
                    lang = "yaml"
                elif clean_path.endswith(".sql"):
                    lang = "sql"
                elif clean_path.endswith(".md"):
                    lang = "markdown"
                elif clean_path.endswith(".ipynb"):
                    lang = "json"
                context_parts.append(f"```{lang}")
                context_parts.append(content)
                context_parts.append("```")

        context_parts.append(
            "\n--- End GeminiTrader Context Block (Selective Files) ---")
        final_context = "\n".join(context_parts)

        # Log the context (clipboard stuff removed)
        # Keep log name for differentiation
        context_log_file = f"{LOG_FILE_BASE}_context_selective.txt"
        try:
            with open(context_log_file, "w", encoding='utf-8') as f:
                f.write(final_context)
            logging.info(f"Selective context saved to {context_log_file}")
        except Exception as e:
            logging.error(
                f"Failed to save selective context log to {context_log_file}: {e}")

        return final_context  # Return context, file saving handled in main loop

    def generate_commit_message(self):
        """Generates a structured commit message."""
        if self.is_ssot_update_mode:
            timestamp_str = "latest"
            if self.handover_content:
                ts_match = re.search(
                    r'\[(\d{4}-\d{2}-\d{2}\s*~\s*\d{2}:\d{2}\s*UTC)\]', self.handover_content)
                if ts_match:
                    timestamp_str = ts_match.group(1)
                else:
                    ts_match_alt = re.search(
                        r'(\d{4}-\d{2}-\d{2}\s*~\s*\d{2}:\d{2}\s*UTC)', self.handover_content)
                    if ts_match_alt:
                        timestamp_str = ts_match_alt.group(1)
            commit_msg = f"chore(SSoT): Update with handover [{timestamp_str}]"
            logging.info(f"Generated SSoT commit message: {commit_msg}")
            return commit_msg

        if self.handover_content is None:
            logging.warning(
                "Cannot generate detailed commit message: Handover content not available.")
            return "chore: Update project state"

        # --- OLD workflow commit message generation ---
        phase = self.parsed_info.get('phase', '?')
        module = self.parsed_info.get('module', '?')
        primary_action = "Update"
        target = "context/state"
        next_steps_match = re.search(r"^\s*Actionable Next Steps:?\s*\n(.*?)(?=\n\s*\n|\Z)",
                                     self.handover_content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
        if next_steps_match:
            first_line = next_steps_match.group(
                1).strip().split('\n')[0].lower()
            keywords = {"implement": "Implement", "create": "Create", "add": "Add",
                        "refactor": "Refactor", "fix": "Fix", "update": "Update", "start": "Start", "begin": "Begin"}
            for key, action in keywords.items():
                if key in first_line:
                    primary_action = action
                    break
            paths_in_line = re.findall(
                r'(src|config|scripts|notebooks|tests)/[\w/.-]+\.(py|yaml|sql|md|ipynb)', first_line, re.IGNORECASE)
            if paths_in_line:
                first_path_match = re.search(
                    r'(?:/|\\)([\w.-]+\.(?:py|yaml|sql|md|ipynb))', first_line)
                if first_path_match:
                    target = first_path_match.group(1)
        commit_type = "feat"
        if primary_action == "Fix":
            commit_type = "fix"
        elif primary_action == "Refactor":
            commit_type = "refactor"
        elif "test" in target.lower():
            commit_type = "test"
        elif any(doc_file in target.lower() for doc_file in ["readme.md", "research.md", "prompts.md", "ssot.md"]):
            commit_type = "docs"
        elif primary_action in ["Update", "Start", "Begin"] and target == "context/state":
            commit_type = "chore"
        scope = f"Phase{phase}"
        if module != '?':
            scope += f".{module}"
        message = f"{commit_type}({scope}): {primary_action} {target}"
        message = message[:72]
        modified_files = self.parsed_info.get('modified', [])
        body = ""
        if modified_files:
            body = "\n\nFiles modified in previous session:\n" + \
                "\n".join(f"- {f}" for f in modified_files)
        full_message = message + body
        logging.info(
            f"Generated commit message (parsed handover):\n{full_message}")
        return full_message

    def run_git_commit(self, commit_message, push=False):
        """Runs git add and git commit."""
        # --- Git commit logic remains the same ---
        try:
            logging.info("Running 'git add .'...")
            subprocess.run(['git', 'add', '.'], check=True, cwd=self.project_root,
                           capture_output=True, text=True, encoding='utf-8')

            logging.info(f"Running 'git commit'...")
            commit_result = subprocess.run(['git', 'commit', '-F', '-'], input=commit_message,
                                           check=True, cwd=self.project_root, capture_output=True, text=True, encoding='utf-8')
            logging.info("Commit successful:\n%s", commit_result.stdout)

            if push:
                confirm = input("Commit successful. Push to remote? (y/N): ")
                if confirm.lower() == 'y':
                    logging.info("Running 'git push'...")
                    push_result = subprocess.run(
                        ['git', 'push'], check=True, cwd=self.project_root, capture_output=True, text=True, encoding='utf-8')
                    logging.info("Push successful:\n%s", push_result.stdout)
                else:
                    logging.info("Push skipped by user.")

        except subprocess.CalledProcessError as e:
            logging.error(f"Git command failed: {e.cmd}")
            stdout = e.stdout.decode(
                'utf-8', errors='replace') if isinstance(e.stdout, bytes) else e.stdout
            stderr = e.stderr.decode(
                'utf-8', errors='replace') if isinstance(e.stderr, bytes) else e.stderr
            logging.error(f"Return Code: {e.returncode}")
            logging.error(f"Stdout:\n{stdout}")
            logging.error(f"Stderr:\n{stderr}")
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                logging.warning(
                    "Git reported nothing to commit. Skipping commit action.")
                return
            elif "Please tell me who you are" in stderr:
                logging.error(
                    "Git user identity not configured. Please run:\n  git config --global user.email \"you@example.com\"\n  git config --global user.name \"Your Name\"")
            raise
        except FileNotFoundError as e:
            if 'git' in str(e):
                logging.error(
                    "Git command not found. Ensure Git is installed and in your system's PATH.")
            else:
                logging.error(f"File not found during Git operation: {e}")
            raise
        except Exception as e:
            logging.error(
                f"An unexpected error occurred during Git operation: {e}", exc_info=True)
            raise

# --- Helper to read multi-line input (Only for OLD workflow) ---


def get_multiline_input(prompt_message):
    """Prompts the user for multi-line input in the terminal."""
    print(prompt_message)
    print("Paste your text here. Press Enter then Ctrl+D (Unix) or Ctrl+Z+Enter (Windows) when done:")
    lines = []
    while True:
        try:
            line = input()
            lines.append(line)
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nInput cancelled.")
            sys.exit(1)
    return "\n".join(lines)

# --- Updated Function for SSoT Update Workflow ---


def update_ssot_and_generate_context(handover_file_path, ssot_file_path, output_context_file_path):
    """
    Appends handover file content to SSoT file, then generates the full context file.
    Returns the full SSoT content and the handover content read.
    REMOVED CLIPBOARD FUNCTIONALITY.
    """
    logging.info(f"Starting SSoT update process:")
    logging.info(f"  Handover file: {handover_file_path}")
    logging.info(f"  SSoT file: {ssot_file_path}")
    logging.info(f"  Output context file: {output_context_file_path}")

    # 1. Read Handover File
    handover_content = None
    try:
        with open(handover_file_path, 'r', encoding='utf-8') as f:
            handover_content = f.read()
        if not handover_content.strip():
            logging.warning(
                f"Handover file '{handover_file_path}' is empty or contains only whitespace.")
            handover_content = "\n\n------- SKIPPED APPEND: Handover file was empty -------\n\n"  # Placeholder
        logging.info(f"Successfully read handover file.")
    except FileNotFoundError:
        logging.error(f"Handover file not found: {handover_file_path}")
        raise
    except Exception as e:
        logging.error(f"Error reading handover file {handover_file_path}: {e}")
        raise

    # 2. Append to SSoT File
    try:
        if not os.path.exists(ssot_file_path):
            logging.warning(
                f"SSoT file '{ssot_file_path}' not found. Creating a new one.")
            with open(ssot_file_path, 'w', encoding='utf-8') as f:
                f.write(
                    f"# GeminiTrader SSoT - Initialized {datetime.now().isoformat()}\n\n")

        with open(ssot_file_path, 'a', encoding='utf-8') as f:
            f.write("\n\n------- SESSION HANDOVER APPENDED [{}] -------\n".format(
                datetime.now().strftime('%Y-%m-%d ~%H:%M UTC')))
            f.write(handover_content)
        logging.info(f"Successfully appended handover content to SSoT file.")
    except Exception as e:
        logging.error(f"Error appending to SSoT file {ssot_file_path}: {e}")
        raise

    # 3. Read Updated SSoT File
    full_ssot_content = None
    try:
        with open(ssot_file_path, 'r', encoding='utf-8') as f:
            full_ssot_content = f.read()
        logging.info(f"Successfully read updated SSoT file.")
    except Exception as e:
        logging.error(f"Error reading updated SSoT file {ssot_file_path}: {e}")
        raise

    # 4. Write Output Context File
    try:
        with open(output_context_file_path, 'w', encoding='utf-8') as f:
            f.write(full_ssot_content)
        logging.info(
            f"Successfully wrote full SSoT content to output file: {output_context_file_path}")
        # User confirmation
        print(
            f"Context for LLM saved to '{os.path.basename(output_context_file_path)}'.")
    except Exception as e:
        logging.error(
            f"Error writing output context file {output_context_file_path}: {e}")
        raise

    # 5. Clipboard handling REMOVED

    return full_ssot_content, handover_content


# --- Main Execution ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GeminiTrader Context Manager Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow Examples:

1. NEW SSoT Update Workflow (Recommended):
   Generate handover markdown from LLM, save it to 'handover.md'. Then run:
   python scripts/context_manager.py --update-ssot --handover-file handover.md [--commit] [--push]

   This appends 'handover.md' to 'SSOT.md', generates 'context_for_llm.md'
   (containing the full updated SSOT.md), saves it to the file,
   and optionally commits with a standard message.

2. OLD Selective Context Workflow (Legacy):
   Generate handover markdown from LLM, then run:
   python scripts/context_manager.py [--commit] [--push]
   --> Then PASTE the handover markdown into the terminal when prompted <--

   This parses the pasted handover, includes specific files mentioned + defaults,
   generates context, saves it to a log file,
   and optionally commits with a message derived from the parsed handover.
"""
    )

    # --- Arguments for BOTH Workflows ---
    parser.add_argument("--commit", action="store_true",
                        help="Automatically stage and commit changes AFTER processing context/SSoT.")
    parser.add_argument("--push", action="store_true",
                        help="Interactively prompt to push after successful commit (requires --commit).")
    # parser.add_argument("--no-clipboard", action="store_true", # REMOVED
    #                     help="Do not attempt to copy the generated context to the clipboard.")

    # --- Arguments for NEW SSoT Update Workflow ---
    ssot_group = parser.add_argument_group('SSoT Update Workflow Options')
    ssot_group.add_argument("--update-ssot", action="store_true",
                            help="Activate the SSoT update workflow (requires --handover-file).")
    ssot_group.add_argument("--handover-file", type=str, default="handover_latest.md", metavar="FILE",
                            help="Path to the handover markdown file generated by the LLM. Required for --update-ssot. Default: handover_latest.md")
    ssot_group.add_argument("--ssot-file", type=str, default="SSOT.md", metavar="FILE",
                            help="Path to the main Single Source of Truth file. Default: SSOT.md")
    ssot_group.add_argument("--output-context-file", type=str, default="context_for_llm.md", metavar="FILE",  # CHANGED default extension
                            help="Path to write the final context markdown file for the LLM. Default: context_for_llm.md")

    args = parser.parse_args()

    # --- Determine Workflow ---
    if args.update_ssot:
        # --- NEW SSoT Update Workflow ---
        logging.info("Running in SSoT Update Mode.")
        print("--- Running SSoT Update Workflow ---")
        manager = ContextManager()
        manager.is_ssot_update_mode = True

        if not args.handover_file:
            logging.error(
                "Handover file path not provided. Required for --update-ssot.")
            print("Error: Handover file path missing. Use --handover-file.")
            sys.exit(1)

        # Resolve full paths relative to project root if not absolute
        handover_path = os.path.join(PROJECT_ROOT, args.handover_file) if not os.path.isabs(
            args.handover_file) else args.handover_file
        ssot_path = os.path.join(PROJECT_ROOT, args.ssot_file) if not os.path.isabs(
            args.ssot_file) else args.ssot_file
        output_path = os.path.join(PROJECT_ROOT, args.output_context_file) if not os.path.isabs(
            args.output_context_file) else args.output_context_file

        # Check handover existence *after* resolving path
        if not os.path.exists(handover_path):
            logging.error(
                f"Handover file specified ('{args.handover_file}') not found at resolved path: {handover_path}")
            print(f"Error: Handover file '{args.handover_file}' not found.")
            sys.exit(1)

        try:
            # Perform the update and generation (clipboard removed internally)
            full_context, read_handover_content = update_ssot_and_generate_context(
                handover_path,
                ssot_path,
                output_path
            )
            manager.handover_content = read_handover_content  # For commit message

            print(f"SSoT file '{os.path.basename(ssot_path)}' updated.")
            # Confirmation message already printed inside update_ssot_and_generate_context

            # Optional Git Commit
            if args.commit:
                print("-" * 20)
                print("Attempting Git commit for SSoT update...")
                try:
                    commit_msg = manager.generate_commit_message()
                    manager.run_git_commit(commit_msg, push=args.push)
                    print("Git commit process finished.")
                except subprocess.CalledProcessError:
                    print("Git commit failed. Check log for details.")
                except Exception as git_err:
                    print(
                        f"An unexpected error occurred during Git commit: {git_err}. Check log.")

        except Exception as e:
            logging.error(
                f"Error during SSoT update process: {e}", exc_info=True)
            print(
                f"An critical error occurred during SSoT update: {e}. Check logs.")
            sys.exit(1)

    else:
        # --- OLD Selective Context Workflow ---
        logging.info("Running in Selective Context Mode (Pasted Handover).")
        print("--- Running Legacy Selective Context Workflow ---")
        try:
            # 1. Get Handover Text from User
            handover_input = get_multiline_input(
                "Please paste the full Handover Document text generated by the LLM:")
            if not handover_input.strip():
                logging.error(
                    "No handover text was provided via paste. Exiting.")
                print("Error: No handover text pasted.")
                sys.exit(1)

            # 2. Initialize Manager and Process
            manager = ContextManager()
            manager.is_ssot_update_mode = False
            manager.set_handover_content(handover_input)

            # 3. Build Selective Context and Save to Log File
            final_context = manager.build_context_prompt()
            # Confirmation message is logged internally by build_context_prompt

            # 4. Clipboard handling REMOVED

            # 5. Optional Git Commit
            if args.commit:
                print("-" * 20)
                print("Attempting Git commit for selective context session...")
                try:
                    commit_msg = manager.generate_commit_message()
                    manager.run_git_commit(commit_msg, push=args.push)
                    print("Git commit process finished.")
                except subprocess.CalledProcessError:
                    print("Git commit failed. Check log for details.")
                except Exception as git_err:
                    print(
                        f"An unexpected error occurred during Git commit: {git_err}. Check log.")

        except ValueError as e:
            logging.error(f"Input Error in old workflow: {e}")
            print(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(
                f"An unexpected error occurred in old workflow main execution: {e}", exc_info=True)
            print(f"An critical error occurred: {e}. Check logs.")
            sys.exit(1)

    # --- Final message for both workflows ---
    logging.info("Context Manager finished successfully.")
    print("-" * 20)
    print("Script finished.")

# end of scripts/context_manager.py
