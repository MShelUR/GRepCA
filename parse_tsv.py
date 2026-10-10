import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tqdm import tqdm

def set_csv_field_limit():
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            break
        except OverflowError:
            limit //= 10

set_csv_field_limit()

HUNK_RE = re.compile(
    r"-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?"
)

SECTION_RE = re.compile(r"^\s*[^:\n]+:\s*(.*)$")

REVIEWER_RE = re.compile(
    r"\b(?:reviewer|reviewed[- ]by|reviewed[- ]by:|"
    r"reviewers|r=)\s*[:=]?\s*\S+",
    re.IGNORECASE,
)


def load_imperatives(path):
    with open(path, encoding="utf-8") as f:
        return {
            line.strip().lower()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        }


def is_imperative(message, imperatives):
    """Check the first word, optionally after a section prefix."""
    text = message.strip()

    match = SECTION_RE.match(text)
    if match:
        text = match.group(1).strip()

    word_match = re.match(r"[^\W_]+(?:[-'][^\W_]+)*", text)
    if not word_match:
        return False

    return word_match.group(0).lower() in imperatives


def has_body(header, body):
    return (len(header) > 0 and len(body) > 0)


def specifies_reviewer(message):
    return bool(REVIEWER_RE.search(message))


def parse_hunks(hunks):
    """
    Return estimated total changed lines and the standard deviation
    of edited line positions for each file/commit.

    Hunk ranges are estimates: unified-diff headers may include
    context lines, not just changed lines.
    """
    positions = []
    changed_lines = 0

    for hunk in hunks:
        match = HUNK_RE.search(hunk)
        if not match:
            continue

        old_start = int(match.group(1))
        old_count = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_count = int(match.group(4) or 1)

        changed_lines += old_count + new_count

        # Approximate edited positions on both sides of the diff.
        positions.extend(range(old_start, old_start + old_count))
        positions.extend(range(new_start, new_start + new_count))

    stddev = statistics.pstdev(positions) if positions else None
    return changed_lines, stddev


def read_commits(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != 5:
                raise ValueError(
                    f"Expected 5 TSV columns, got {len(row)}: {row!r}"
                )

            developer_id, timestamp, header, body, files_json = row

            yield {
                "developer": developer_id.strip(),
                "timestamp": datetime.strptime(
                    timestamp.strip(), "%a %b %d %H:%M:%S %Y %z"
                ),
                "header": header,
                "body": body,
                "files": json.loads(files_json),
            }


def aggregate(input_path, output_path, imperatives_path):
    imperatives = load_imperatives(imperatives_path)
    months = defaultdict(
        lambda: {
            "commits": 0,
            "developers": set(),
            "files_per_commit": [],
            "imperative": 0,
            "messages_with_body": 0,
            "reviewer": 0,
            "message_count": 0,
            "lines_per_file_commit": [],
            "stddevs": [],
        }
    )

    with open(input_path, "rb") as f:
        num_lines = sum(1 for _ in f)
    
    pbar = tqdm(total = num_lines)

    for commit in read_commits(input_path):
        pbar.update(1)
        
        timestamp = commit["timestamp"].astimezone(timezone.utc)

        month = timestamp.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            tzinfo=timezone.utc,
        )
        data = months[month]
        header = commit["header"]
        body = commit["body"]
        files = commit["files"]

        data["commits"] += 1
        data["developers"].add(commit["developer"])
        data["files_per_commit"].append(len(files))
        data["message_count"] += 1

        data["imperative"] += (is_imperative(header, imperatives) or is_imperative(body, imperatives))
        data["messages_with_body"] += has_body(header, body)
        data["reviewer"] += (specifies_reviewer(header) or specifies_reviewer(body))

        for hunks in files.values():
            line_count, stddev = parse_hunks(hunks)
            data["lines_per_file_commit"].append(line_count)

            if stddev is not None:
                data["stddevs"].append(stddev)

    pbar.close()

    columns = [
        "Timestamp",
        "Number of commits made",
        "Number of unique developers making commits",
        "Average number of files changed per commit",
        "Percent of commit messages that start with an imperative verb",
        "Percent of commit messages with both headers and bodies",
        "Percent of commit messages that specify a reviewer",
        "Average number of lines changed per file per commit",
        "Average standard deviation of line numbers edited",
        "Median standard deviation of line numbers edited",
    ]

    def mean_or_blank(values):
        return statistics.mean(values) if values else ""

    def median_or_blank(values):
        return statistics.median(values) if values else ""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)

        for month in sorted(months):

            data = months[month]
            count = data["message_count"]

            percentage = lambda n: 100 * n / count if count else 0

            timestamp = int(month.timestamp())

            writer.writerow([
                timestamp,
                data["commits"],
                len(data["developers"]),
                mean_or_blank(data["files_per_commit"]),
                percentage(data["imperative"]),
                percentage(data["messages_with_body"]),
                percentage(data["reviewer"]),
                mean_or_blank(data["lines_per_file_commit"]),
                mean_or_blank(data["stddevs"]),
                median_or_blank(data["stddevs"]),
            ])


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate commit TSV data by calendar month."
    )
    parser.add_argument("input_tsv", help="Path to the input commit TSV")
    parser.add_argument(
        "-o", "--output",
        help="Output TSV path (default: ./parsed_tsv/<input filename>)",
    )
    parser.add_argument(
        "-i", "--imperatives",
        default="imperatives.txt",
        help="Imperative word list (default: imperatives.txt)",
    )
    args = parser.parse_args()

    input_path = Path(args.input_tsv)
    output_path = (
        Path(args.output)
        if args.output
        else Path("./parsed_csv") / input_path.name.replace(".tsv",".csv")
    )

    aggregate(input_path, output_path, args.imperatives)
    print(f"Wrote monthly summary to {output_path}")


if __name__ == "__main__":
    main()