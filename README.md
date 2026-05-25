# Report Cleaner

Convert Vernon CMS **Authority Term Usage** text reports into structured CSV outputs.

## What this script does

The parser reads report blocks like:

- `Authority term = <term> (<system_id>)`
- `Data file = <file_name> (<file_id>)`
- `Number of times the term is used = <count>`

and supports two parse modes:

### 1) `summary` mode

One CSV row per **authority term + data file** combination.

Output columns:

- `system_id`
- `authority_term`
- `data_file`
- `data_file_id`
- `occurrence`

### 2) `detailed` mode

One CSV row per **object record** (the individual lines under each `Data file = ...` block).

Output columns:

- `object_id`
- `object_description`
- `system_id`
- `authority_term`
- `data_file`

## Requirements

- Python 3.9+ (or any recent Python 3)

No third-party packages are required.

## How to run

From this folder (`report_cleaner`), run summary mode:

```powershell
py -3 parse_authority_term_usage.py --mode summary --input "Person_Biography Role Authority Term Report.txt" --output "output\authority_term_usage_structured_summary.csv"
```

Run detailed mode:

```powershell
py -3 parse_authority_term_usage.py --mode detailed --input "Person_Biography Role Authority Term Report.txt" --output "output\authority_term_usage_structured_detailed.csv"
```

You can also use absolute paths in either mode:

```powershell
py -3 parse_authority_term_usage.py --mode detailed --input "C:\path\to\Authority Term Report.txt" --output "C:\path\to\output.csv"
```

## Notes

- The script skips report headers/boilerplate automatically.
- In `summary` mode, it captures summary usage counts.
- In `detailed` mode, it captures individual record lines.
- In `summary` mode, labels like `Person: Biography Role` are simplified so `data_file` becomes `Biography Role`, while `data_file_id` is preserved.
- In `detailed` mode, `data_file` is the report's "Field Containing Term" value (for example `Biographical Role`).
- Detailed mode handles wrapped descriptions, for example:
  - `C56149 ... Frederick James William Stewart ...`
  - next line: `(Christchurch)`
  - output description becomes `Cenotaph; Frederick James William Stewart (Christchurch)`.

## Expected output example

If `summary` mode parsing works correctly, the CSV will look like this:

```csv
system_id,authority_term,data_file,data_file_id,occurrence
10853,Sports goods worker,Person,PERSON,3
10853,Sports goods worker,Biography Role,PE_BIO_ROLE,0
```

If `detailed` mode parsing works correctly, the CSV will look like this:

```csv
object_id,object_description,system_id,authority_term,data_file
105545,Cenotaph; Finlay James Parkinson (Auckland),10853,Sports goods worker,Biographical Role
123195,Cenotaph; Donald Francis Cederwall (Gisborne),10853,Sports goods worker,Biographical Role
130778,Cenotaph; Percy Leonard Cowsill (Auckland),10853,Sports goods worker,Biographical Role
```
