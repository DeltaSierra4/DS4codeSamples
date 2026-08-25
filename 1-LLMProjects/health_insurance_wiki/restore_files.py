#!/usr/bin/env python3

"""
Reads a JSON file (as produced by dump_files_to_json.py) mapping relative
filepaths to file contents, and recreates those files/directories relative
to the current working directory.

Input format:

{
    "<filepath>": "<text within that file>",
    ...
}
"""

import json
import os
import sys


INPUT_FILENAME = "files_dump.json"


def main():
    cwd = os.getcwd()

    input_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(cwd, INPUT_FILENAME)
    )

    if not os.path.isfile(input_path):
        print(
            f"Input JSON file not found: {input_path}",
            file=sys.stderr
        )
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0

    for rel_path, content in data.items():
        # Normalize to the current OS's path separators and prevent escaping cwd
        norm_rel_path = os.path.normpath(rel_path)

        if norm_rel_path.startswith("..") or os.path.isabs(norm_rel_path):
            print(f"Skipping unsafe path: {rel_path}", file=sys.stderr)
            continue

        dest_path = os.path.join(cwd, norm_rel_path)
        dest_dir = os.path.dirname(dest_path)

        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)

        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)

        count += 1

    print(f"Recreated {count} file(s) from {input_path}")


if __name__ == "__main__":
    main()