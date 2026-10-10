import csv
import json
import os
import re
import subprocess
import sys

from tqdm import tqdm



COMMIT_MARKER = "\x1eCOMMIT\x1f"
HUNK_RE = re.compile(
    r"^@@ (-\d+(?:,\d+)? \+\d+(?:,\d+)?) @@"
)


author_ids = {}
num_authors = 0

def index_author(author):
    global author_ids
    global num_authors

    author_id = author_ids.get(author)

    if author_id:
        return author_id
    else:
        num_authors += 1
        author_ids[author] = num_authors
        return num_authors


def run_git(*args, check=True):
    return subprocess.run(
        ["git", *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git(*args, input=None, repo_dir):
    return subprocess.check_output(
        ["git", f"--git-dir={repo_dir}", *args],
        input=input,
        stderr=subprocess.DEVNULL,
    )


def prepare_repository(url, repo_dir):
    os.makedirs(os.path.dirname(repo_dir), exist_ok=True)

    if not os.path.isdir(repo_dir):
        print(
            f"Cloning bare repository into {repo_dir}...",
            file=sys.stderr,
        )
        run_git("clone", "--bare", url, repo_dir)
    else:
        print(f"Repository already present at {repo_dir}, verifying...")
        # Ensure the existing directory is a valid bare repository.
        result = run_git(
            "--git-dir=" + repo_dir,
            "rev-parse",
            "--is-bare-repository",
            check=False,
        )

        if result.returncode != 0 or result.stdout.strip() != b"true":
            sys.exit(f"Error: {repo_dir} is not a valid bare repository.")
        print(f"Repository was correctly initialized.")

        # Fetch updates without creating a working tree.
        print(f"Checking for repository updates...")
        git("fetch", "origin", repo_dir=repo_dir)
        print(f"Repository updated.")


def unquote_git_path(value):
    """Decode a Git-quoted pathname, including octal escapes."""
    value = value.strip()

    if not value.startswith('"'):
        return value

    result = bytearray()
    i = 1

    while i < len(value):
        char = value[i]

        if char == '"':
            break

        if char != "\\":
            result.extend(char.encode("utf-8", errors="surrogateescape"))
            i += 1
            continue

        i += 1
        if i >= len(value):
            break

        char = value[i]

        escapes = {
            "a": 7,
            "b": 8,
            "t": 9,
            "n": 10,
            "v": 11,
            "f": 12,
            "r": 13,
            "\\": 92,
            '"': 34,
        }

        if char in escapes:
            result.append(escapes[char])
            i += 1
        elif char in "01234567":
            digits = value[i:i + 3]
            digits = re.match(r"[0-7]{1,3}", digits).group()
            result.append(int(digits, 8))
            i += len(digits)
        else:
            result.extend(char.encode("utf-8"))
            i += 1

    return result.decode("utf-8", errors="surrogateescape")


def parse_diff_path(line):
    """
    Extract the path from a --- or +++ patch header.
    Git quotes unusual pathnames when necessary.
    """
    value = line[4:].rstrip("\r\n")

    if value.startswith('"'):
        # Find the closing quote, respecting escaped quotes.
        escaped = False

        for i in range(1, len(value)):
            if escaped:
                escaped = False
            elif value[i] == "\\":
                escaped = True
            elif value[i] == '"':
                value = value[:i + 1]
                break

    else:
        # Ordinary filenames are not quoted; strip an optional
        # tab-separated timestamp if present.
        value = value.split("\t", 1)[0]

    return unquote_git_path(value)


def emit_commit(writer, metadata, files):
    if metadata is None:
        return

    author, date, header, body = metadata

    author = str(index_author(author))

    # Normalize tabs and newlines so each commit occupies one TSV row.
    header = header.replace("\t", " ").replace("\n", " ").strip()
    body = body.replace("\t", " ").replace("\r", "").strip()
    body = body.replace("\n", " ")

    writer.writerow([
        author,
        date,
        header,
        body,
        json.dumps(files, ensure_ascii=False),
    ])


def main():
    if len(sys.argv) < 2:
        sys.exit(
            f"Usage: {sys.argv[0]} [repository link] [revision, OPTIONAL]"
        )

    repo_url = sys.argv[1]
    revision = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    repo_dir = os.path.join("raw_git", "_".join(repo_url.split("/")[-2:]))
    raw_tsv_path = os.path.join("raw_tsv/", "_".join(repo_url.split("/")[-2:])+".tsv")

    prepare_repository(repo_url, repo_dir)

    # Stream the entire history and its patches from a single Git process.
    # The marker makes commit boundaries unambiguous.
    command = [
        "git",
        f"--git-dir={repo_dir}",
        "log",
        "--topo-order",
        "--root",
        "--diff-merges=first-parent",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",  # Avoid configured text-conversion filters
        "--no-color",
        "--unified=0",
        "--format=" + COMMIT_MARKER
        + "%ae%x1f%ad%x1f%s%x1f%b",
        "--date=format:%a %b %d %H:%M:%S %Y %z",
        "-p",
        revision,
    ]

    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        bufsize=1024 * 1024,
    )

    print("Fetching total number of commits... (this may take a while)")
    try:
        total_num_commits = int(run_git(f"--git-dir={repo_dir}", "rev-list", "--count", revision).stdout.decode())
        print(f"Found {total_num_commits} commits.")
    except:
        print("Couldn't determine total number of commits.")

    print(f"Reading every commit...")
    progress_bar = tqdm(total=total_num_commits)

    with open(raw_tsv_path, "w", encoding="utf-8") as out_file:
        writer = csv.writer(
            out_file,
            delimiter="\t",
            lineterminator="\n",
            quoting=csv.QUOTE_MINIMAL,
        )

        metadata = None
        files = {}
        current_path = None
        old_path = None

        try:
            for line in proc.stdout:
                try:
                    if line.startswith(COMMIT_MARKER):
                        # Flush the previous commit before starting the next.
                        progress_bar.update(1)
                        emit_commit(writer, metadata, files)

                        fields = line[len(COMMIT_MARKER):].rstrip("\r\n")
                        parts = fields.split("\x1f", 3)

                        if len(parts) != 4:
                            raise ValueError(
                                f"Malformed commit metadata: {fields!r}"
                            )

                        metadata = tuple(parts)
                        files = {}
                        current_path = None
                        old_path = None
                        continue

                    # Ignore patch text until the first file diff.
                    if line.startswith("diff --git "):
                        current_path = None
                        old_path = None
                        continue

                    if line.startswith("--- "):
                        old_path = parse_diff_path(line)

                        if old_path.startswith("a/"):
                            old_path = old_path[2:]

                        if old_path == "/dev/null":
                            old_path = None

                        continue

                    if line.startswith("+++ "):
                        new_path = parse_diff_path(line)

                        if new_path.startswith("b/"):
                            new_path = new_path[2:]

                        if new_path == "/dev/null":
                            new_path = None

                        # Added files use the new path; deleted files use
                        # the old path. Otherwise both paths are identical
                        # because rename detection is disabled.
                        current_path = new_path if new_path is not None else old_path

                        if current_path is not None:
                            files.setdefault(current_path, [])

                        continue

                    if current_path is not None:
                        match = HUNK_RE.match(line)

                        if match:
                            files[current_path].append(
                                "-" + match.group(1).split(" ")[0][1:]
                                + " +" + match.group(1).split(" ")[1][1:]
                            )
                except Exception as e:
                    print(e)
                    pass
            emit_commit(writer, metadata, files)

        finally:
            proc.stdout.close()

        progress_bar.close()

        return_code = proc.wait()

        if return_code != 0:
            sys.exit(f"git log failed with exit code {return_code}")


if __name__ == "__main__":
    main()