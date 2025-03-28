#!/bin/bash

# --- Configuration ---
OUTPUT_FILE="GeminiTrader.txt"
README_FILE="README.md" # Define the README filename

# File extensions/names to include
INCLUDE_PATTERNS='\.py$|\.js$|\.jsx$|\.ts$|\.tsx$|\.html$|\.css$|\.scss$|\.md$|\.json$|\.yaml$|\.yml$|\.txt$|\.sh$|Dockerfile|Makefile'

# Directory/file patterns to exclude (uses grep -E syntax)
# Add README_FILE to the base exclusion for the main loop later
BASE_EXCLUDE_PATTERNS='/\.git/|/node_modules/|/dist/|/build/|/venv/|/\.venv/|/__pycache__/|/\.vscode/|/\.idea/|/coverage/|/\.DS_Store|^./'"${OUTPUT_FILE}"'$'

# --- Script ---
echo "Creating context file with readme and code blocks: $OUTPUT_FILE" # Updated message
# Clear the output file
> "$OUTPUT_FILE"

# --- 1. README File --- (Moved to be the first section)
if [ -f "$README_FILE" ]; then
    echo "Processing: $README_FILE (as introduction)"
    echo "--- START FILE: $README_FILE ---" >> "$OUTPUT_FILE"
    echo "\`\`\`markdown" >> "$OUTPUT_FILE"
    cat "$README_FILE" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE" # Ensure newline before fence
    echo "\`\`\`" >> "$OUTPUT_FILE"
    echo "--- END FILE: $README_FILE ---" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
else
    echo "[ $README_FILE not found in project root, starting with other files. ]" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
fi

# --- 2. Individual Files --- (Renumbered section)
echo "--- START ALL OTHER PROJECT FILES ---" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Add README_FILE to exclusions for the main find command
# Use printf for safer path construction if README_FILE had special chars
EXCLUDE_PATTERNS_FOR_FIND="${BASE_EXCLUDE_PATTERNS}"
printf -v readme_pattern '|^./%s$' "$README_FILE"
EXCLUDE_PATTERNS_FOR_FIND+="${readme_pattern}"

# Find all files, filter out excluded patterns, filter for included patterns
find . -type f -print0 | grep -zEv "$EXCLUDE_PATTERNS_FOR_FIND" | grep -zE "$INCLUDE_PATTERNS" | while IFS= read -r -d $'\0' file; do
    # Clean file path for display (remove leading ./)
    display_file="${file#./}"
    echo "Processing: $display_file"

    # --- Determine Language Hint ---
    ext_raw="${file##*.}"
    base_name=$(basename "$file")
    lang_hint="text"
    if [[ "$ext_raw" != "$base_name" ]] && [[ ! -z "$ext_raw" ]]; then
        lang_hint=$(echo "$ext_raw" | tr '[:upper:]' '[:lower:]')
        case "$lang_hint" in
            "mjs"|"jsx") lang_hint="javascript" ;;
            "tsx") lang_hint="typescript" ;;
            "yml") lang_hint="yaml" ;;
            # Add other specific mappings
        esac
    else
        case "$base_name" in
            "Dockerfile") lang_hint="dockerfile" ;;
            "Makefile") lang_hint="makefile" ;;
        esac
        if [[ "$lang_hint" == "text" ]] && [[ "$base_name" == .* ]]; then
            case "$base_name" in
                ".bashrc"|".profile") lang_hint="bash" ;;
                ".gitignore") lang_hint="gitignore" ;;
                ".env") lang_hint="dotenv" ;;
                # Add more hidden file types
            esac
        fi
    fi

    # --- Append to Output File ---
    echo "--- START FILE: $display_file ---" >> "$OUTPUT_FILE"
    echo "\`\`\`${lang_hint}" >> "$OUTPUT_FILE"
    cat "$file" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE" # Ensure newline before fence
    echo "\`\`\`" >> "$OUTPUT_FILE"
    echo "--- END FILE: $display_file ---" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

done

echo "--- END ALL OTHER PROJECT FILES ---" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

echo "Finished creating $OUTPUT_FILE"