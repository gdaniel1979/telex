#!/usr/bin/env bash

# --------------------------------------------------------
# TELEX AUTOMATION SCRIPT
# RUNNING TELEX.PY + WRITING LOG + MOVING WORDCLOUD IMAGES
# --------------------------------------------------------

# ---  Base settings ---
BASE_DIR="/home/gdaniel1979/hobby_projects/Telex"
MAIN_CODE="telex.py"
TELEX_LOG="telex_automation.log"
WORDCLOUD_ARCHIVE_DIR="Wordcloud_archive"

# ---  Setting directory ---
cd "$BASE_DIR" || exit 1

# --- Setting PATH for cron ---
export PATH=/usr/bin:/bin:/usr/local/bin

# --- Running Python script and capturing output ---
LOG_FILE="$BASE_DIR/$TELEX_LOG"
DATE_STR=$(date '+%Y-%m-%d %H:%M:%S')

# --- Running Python script and saving output into variable ---
OUTPUT=$(/usr/bin/python3 "$BASE_DIR/$MAIN_CODE" 2>&1)

# --- Prepend new entry to log (newest on top) ---
TMP_LOG=$(mktemp)
{
    echo "===== $DATE_STR ====="
    echo "$OUTPUT"
    echo ""
    echo ""
    cat "$LOG_FILE" 2>/dev/null
} > "$TMP_LOG"
mv "$TMP_LOG" "$LOG_FILE"

# --- Moving wordcloud images into archive ---
ARCHIVE_DIR="$BASE_DIR/$WORDCLOUD_ARCHIVE_DIR"
mkdir -p "$ARCHIVE_DIR"

for topic in kulfold belfold gazdasag; do
    FILE="$BASE_DIR/wordcloud_${topic}_$(date +%Y-%m-%d).png"
    if [ -f "$FILE" ]; then
        mv "$FILE" "$ARCHIVE_DIR/"
    fi
done

echo "Done"
