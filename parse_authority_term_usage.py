#!/usr/bin/env python3
"""
Parse Vernon CMS "Authority Term Usage" reports into structured CSV rows.

This script converts a large plain-text report into a tabular format that is
easy to analyse in Excel, Power BI, pandas, or SQL.

Each output row represents one "authority term + data file" usage summary:
    - system_id: authority term numeric/system id
    - authority_term: authority term description text
    - data_file: human-readable target data file name
    - data_file_id: Vernon code for the data file
    - occurrence: "Number of times the term is used"

Important notes for maintainers:
1) The report begins with boilerplate headers (for example "Authority term ="
   with no value). Those lines are intentionally ignored.
2) We do not parse the individual record listing lines (IDs/person names). We
   only capture the summary usage count that Vernon provides per data file.
3) Parsing is line-by-line and stateful, so it handles very large files without
   loading the full report into memory.

Example source block:
    Authority term = Sports goods worker (10853)
    Data file = Person (PERSON)
    Number of times the term is used = 3
    Data file = Person: Biography Role (PE_BIO_ROLE)
    Number of times the term is used = 0
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

# Regex patterns for the three report lines we care about.
# We anchor with ^...$ so we only match complete lines in the expected format.
AUTHORITY_TERM_PATTERN = re.compile(r"^Authority term =\s*(.*?)\s*\(([^()]*)\)\s*$")
DATA_FILE_PATTERN = re.compile(r"^Data file =\s*(.*?)\s*\(([^()]*)\)\s*$")
OCCURRENCE_PATTERN = re.compile(r"^Number of times the term is used =\s*(\d+)\s*$")
# Object rows in the "Data file = ..." section are typically:
# <object_id><2+ spaces><object_description><2+ spaces><field_containing_term>
#
# Important:
# - object descriptions can contain internal double spaces, e.g. "Junior  Writer".
# - we therefore use a GREEDY middle capture so the final column split is taken
#   from the right-most "2+ spaces" separator, not the first one.
DETAIL_ROW_PATTERN = re.compile(r"^(\S+)\s{2,}(.+)\s{2,}(\S.*)\s*$")


def simplify_data_file_name(raw_name: str) -> str:
    """
    Convert Vernon "Data file" labels into a cleaner display name.

    Example:
        Person: Biography Role -> Biography Role

    Why:
    - Vernon often prefixes sub-files with a parent namespace ("Person: ...").
    - For reporting, teams usually want the specific file name only.
    - If no namespace exists, the original value is returned unchanged.
    """
    if ":" in raw_name:
        return raw_name.split(":", 1)[1].strip()
    return raw_name.strip()


def parse_summary_report(input_path: Path) -> list[dict[str, str | int]]:
    """
    Parse the text report into structured rows.

    Parsing model:
    - Read each line once.
    - Track the current authority term context.
    - Track the most recent "Data file = ..." line as pending.
    - When "Number of times..." appears, emit one output row by combining:
      current authority term + pending data file + occurrence.

    Returns:
        A list of dictionaries ready to write via csv.DictWriter.
    """
    rows: list[dict[str, str | int]] = []

    # Current authority term context for all following data file blocks until
    # the next "Authority term = ... (id)" line is found.
    current_term: str | None = None
    current_term_id: str | None = None

    # Temporary holder for "Data file = ... (id)" until we read its matching
    # "Number of times the term is used = N" line.
    pending_data_file_name: str | None = None
    pending_data_file_id: str | None = None

    with input_path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            # Trim whitespace and skip blank lines early to simplify matching.
            line = raw_line.strip()
            if not line:
                continue

            authority_match = AUTHORITY_TERM_PATTERN.match(line)
            if authority_match:
                term_name = authority_match.group(1).strip()
                term_id = authority_match.group(2).strip()

                # Skip report header placeholder: "Authority term =" (blank).
                # We only accept a real term when both name and id exist.
                if term_name and term_id:
                    current_term = term_name
                    current_term_id = term_id
                    # Clear stale pending data file state when moving to a new
                    # authority term block.
                    pending_data_file_name = None
                    pending_data_file_id = None
                continue

            # Ignore all lines until we have entered a valid authority term
            # section. This filters out report headers and separators.
            if current_term is None or current_term_id is None:
                continue

            data_file_match = DATA_FILE_PATTERN.match(line)
            if data_file_match:
                # Store data file details and wait for its occurrence line.
                pending_data_file_name = data_file_match.group(1).strip()
                pending_data_file_id = data_file_match.group(2).strip()
                continue

            occurrence_match = OCCURRENCE_PATTERN.match(line)
            if occurrence_match and pending_data_file_name and pending_data_file_id:
                # We have a complete triplet:
                #   authority term context + pending data file + occurrence
                # so we can safely emit one structured output row.
                rows.append(
                    {
                        "system_id": current_term_id,
                        "authority_term": current_term,
                        "data_file": simplify_data_file_name(pending_data_file_name),
                        "data_file_id": pending_data_file_id,
                        "occurrence": int(occurrence_match.group(1)),
                    }
                )
                # Reset pending state so the next occurrence line does not
                # incorrectly duplicate this data file block.
                pending_data_file_name = None
                pending_data_file_id = None

    return rows


def parse_detailed_report(input_path: Path) -> list[dict[str, str]]:
    """
    Parse object-level rows under each data file block.

    Detailed mode output columns:
        referenced record_authority system id,
        referenced record_authority description,
        authority term system id,
        authority term,
        referenced datafile,
        featured in field

    Notes on line wrapping:
    - Vernon sometimes wraps the object description onto the next line.
    - A wrapped line usually has leading spaces and no object id.
    - Example:
          C56149   Cenotaph; Frederick James William Stewart     Biographical Role
                    (Christchurch)
      We append "(Christchurch)" to the previous object's description.
    """
    rows: list[dict[str, str]] = []

    current_term: str | None = None
    current_term_id: str | None = None
    current_data_file_id: str | None = None

    # True while we are inside a "Data file = ..." block and before the
    # matching "Number of times the term is used = ..." line.
    in_data_file_block = False

    # Keep the index of the last detailed row so wrapped lines can be appended
    # to the correct object description.
    last_row_index: int | None = None

    with input_path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()

            authority_match = AUTHORITY_TERM_PATTERN.match(stripped)
            if authority_match:
                term_name = authority_match.group(1).strip()
                term_id = authority_match.group(2).strip()
                if term_name and term_id:
                    current_term = term_name
                    current_term_id = term_id
                in_data_file_block = False
                last_row_index = None
                continue

            if current_term is None or current_term_id is None:
                continue

            data_file_match = DATA_FILE_PATTERN.match(stripped)
            if data_file_match:
                in_data_file_block = True
                current_data_file_id = data_file_match.group(2).strip()
                last_row_index = None
                continue

            if OCCURRENCE_PATTERN.match(stripped):
                in_data_file_block = False
                current_data_file_id = None
                last_row_index = None
                continue

            if not in_data_file_block:
                continue

            # Ignore separators and other non-content lines.
            if not stripped or set(stripped) == {"-"}:
                continue

            # Parse a normal object line.
            detail_match = DETAIL_ROW_PATTERN.match(raw_line.rstrip("\n\r"))
            if detail_match:
                object_id = detail_match.group(1).strip()
                object_description = detail_match.group(2).strip()
                field_containing_term = detail_match.group(3).strip()

                rows.append(
                    {
                        "referenced record_authority system id": object_id,
                        "referenced record_authority description": object_description,
                        "authority term system id": current_term_id,
                        "authority term": current_term,
                        "referenced datafile": current_data_file_id or "",
                        "featured in field": field_containing_term,
                    }
                )
                last_row_index = len(rows) - 1
                continue

            # If the row did not match object format but we just parsed an object
            # row, treat this as a continuation of the description.
            if last_row_index is not None:
                continuation = stripped
                if continuation:
                    previous = rows[last_row_index][
                        "referenced record_authority description"
                    ]
                    rows[last_row_index]["referenced record_authority description"] = (
                        f"{previous} {continuation}".strip()
                    )

    return rows


def build_parser() -> argparse.ArgumentParser:
    """Define CLI arguments for input, output, and parse mode."""
    parser = argparse.ArgumentParser(
        description="Parse Vernon authority term usage text report into structured CSV."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the authority term usage report .txt file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the output CSV file",
    )
    parser.add_argument(
        "--mode",
        choices=["summary", "detailed"],
        default="summary",
        help=(
            "summary: one row per authority term + data file count (default). "
            "detailed: one row per object record."
        ),
    )
    return parser


def main() -> None:
    """CLI entrypoint: parse report in chosen mode and write CSV output."""
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    # Parse first, then ensure output folder exists before writing.
    if args.mode == "summary":
        rows = parse_summary_report(input_path)
        fieldnames = [
            "system_id",
            "authority_term",
            "data_file",
            "data_file_id",
            "occurrence",
        ]
    else:
        rows = parse_detailed_report(input_path)
        fieldnames = [
            "referenced record_authority system id",
            "referenced record_authority description",
            "authority term system id",
            "authority term",
            "referenced datafile",
            "featured in field",
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Parsed {len(rows)} rows in {args.mode} mode to: {output_path}")


if __name__ == "__main__":
    main()
