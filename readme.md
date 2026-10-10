# GReCA: Git Repository Commit Analyzer

This project was developed for the AoIR 2026 extended abstract *Blame Git: Merging Ideologies and Version Control in Software Development*.

GReCA is a Python tool that analyzes and graphs development trends that are correlated with the adoption of Git, the Version Control System.

## Metrics

The primary metrics that GReCA computes about a repository are, per month timestep:

General engagement metrics:
- Number of commits made
- Number of unique developers making commits
- Average number of files changed per commit 

Commit message standardization metrics:
- Percent of commit messages that start with an imperative verb
- Percent of commit messages with both headers and bodies
- Percent of commit messages that specify a reviewer

Scale of changes metrics:
- Average number of lines changed per file per commit
- Average standard deviation of line numbers edited
- Median standard deviation of line numbers edited

Additionally, GReCA produces TSV (Tab-Separated Values) files with raw information about every commit that was integrated into the main branch of an analyzed repository. These files are saved into the `TSVs` folder during graph generation, and can be imported into any tool that can read TSVs for further analysis.

## Requirements

### Python 3.11

GReCA primarily uses Python 3.11, which can be installed via [python.org](https://www.python.org/downloads/release/python-3110/). 

## Installation

After Python is available, the dependencies in this project can be installed via `python -m pip install -r requirements.txt`.

## Usage

### Generate the raw commit data TSV

To make the initial TSV file containing every commit's statistics, run `python generate_raw_tsv.py [repository link]` (where `[repository link]` is replaced with a link like `https://github.com/mozilla-firefox/firefox`)

- The TSV result will contain one row *per commit* with the following columns, in order: 
    - Contributor ID (number)
    - Timestamp (datetime string)
    - Commit message (string)
    - Files changed (json string)
- NOTE: If the repository contains more than 10,000 commits on the main branch, this may take a long time.

### Parse the TSV data into graphs of the core metrics

After a raw commit TSV file is made, it can be passed into `python parse_tsv.py [path to TSV]`, which will then convert it into a CSV (Comma-Separated Values) which can be directly imported into data analysis tools or spreadsheet utility.
- The CSV result will contain one row *per month* with the following columns, in order:
    - Timestamp (unix timestamp number)
    - Number of commits made (number)
    - Number of unique developers making commits (number)
    - Average number of files changed per commit  (number)
    - Percent of commit messages that start with an imperative verb (number)
    - Percent of commit messages with both headers and bodies (number)
    - Percent of commit messages that specify a reviewer (number)
    - average number of lines changed per file per commit (number)
    - average standard deviation of line numbers edited (number)
    - median standard deviation of line numbers edited (number)

### Plot the CSV data

Plots can be generated from any CSV file following the format that `parse_tsv.py` outputs. To do so, run `python make_plots.py [path to CSV]`.
- This will open an interactive multi-plot of all tracked metrics for that repository.