import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd


def read_csv(path):
    with open(path, "r", newline="", encoding="utf-8") as in_file:
        reader = csv.reader(in_file)
        header = next(reader)

        times = []
        values = {name: [] for name in header[1:]}

        for row in reader:
            if not row:
                continue

            timestamp = int(row[0])
            times.append(
                datetime.fromtimestamp(timestamp, tz=timezone.utc)
            )

            for name, value in zip(header[1:], row[1:]):
                values[name].append(
                    float(value) if value.strip() else float("nan")
                )

    return times, values


def show_charts(
    times,
    values,
    output_path=None,
    smoothing=1,
    show_raw=False,
):
    metrics = list(values.keys())

    if len(metrics) != 9:
        raise ValueError(
            f"Expected exactly 9 metrics, found {len(metrics)}."
        )

    # Apply a consistent, clean visual style.
    plt.style.use("seaborn-v0_8-whitegrid")

    fig, axes = plt.subplots(
        3,
        3,
        figsize=(17, 12),
        sharex=True,
    )

    fig.suptitle(
        "Monthly Metrics",
        fontsize=16,
        fontweight="bold",
        y=1.02,
    )

    for axis, metric in zip(axes.flat, metrics):
        series = pd.Series(values[metric], index=pd.DatetimeIndex(times))

        # Optionally average nearby observations to reduce noise.
        if smoothing > 1:
            trend = series.rolling(
                window=smoothing,
                center=True,
                min_periods=1,
            ).mean()
        else:
            trend = series

        # Show raw data faintly if requested.
        if show_raw and smoothing > 1:
            axis.plot(
                times,
                values[metric],
                color="steelblue",
                linewidth=0.7,
                alpha=0.25,
                label="Raw data",
            )

        axis.plot(
            times,
            trend,
            color="#2563A6",
            linewidth=1.8,
            solid_capstyle="round",
            label=(
                f"{smoothing}-point moving average"
                if smoothing > 1
                else "Value"
            ),
        )

        axis.set_title(
            metric,
            fontsize=10,
            fontweight="semibold",
            pad=8,
        )
        axis.set_ylabel("Value", fontsize=9)

        # Keep the background grid subtle.
        axis.grid(
            True,
            which="major",
            linestyle="-",
            linewidth=0.5,
            alpha=0.25,
        )
        axis.grid(
            True,
            which="minor",
            linestyle=":",
            linewidth=0.4,
            alpha=0.12,
        )
        axis.set_axisbelow(True)

        # Use a limited number of date labels.
        axis.xaxis.set_major_locator(
            mdates.AutoDateLocator(minticks=3, maxticks=6)
        )
        axis.xaxis.set_major_formatter(
            mdates.DateFormatter("%Y-%m", tz=timezone.utc)
        )

        axis.tick_params(axis="both", labelsize=8)

        if show_raw and smoothing > 1:
            axis.legend(fontsize=7, frameon=False, loc="best")

    # Only label the bottom row's x-axes.
    for axis in axes[-1, :]:
        axis.set_xlabel("Month", fontsize=9)

    for axis in axes.flat:
        axis.label_outer()

    fig.tight_layout(pad=2.0)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            output_path,
            dpi=200,
            bbox_inches="tight",
            facecolor="white",
        )
        print(f"Saved plot to {output_path}")

    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Plot nine monthly metrics from an aggregated CSV."
    )
    parser.add_argument(
        "csv_path",
        help="Path to the monthly aggregation CSV file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Optional path to save the plot image "
             "(e.g. plots/metrics.png)",
    )
    parser.add_argument(
        "--smooth",
        type=int,
        default=1,
        metavar="N",
        help="Centered moving-average window in data points "
             "(default: 1, no smoothing)",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Show faint raw data behind the smoothed trend",
    )

    args = parser.parse_args()

    if args.smooth < 1:
        parser.error("--smooth must be at least 1")

    times, values = read_csv(args.csv_path)

    if not times:
        raise ValueError("The CSV contains no data rows.")

    show_charts(
        times,
        values,
        args.output,
        smoothing=args.smooth,
        show_raw=args.show_raw,
    )

if __name__ == "__main__":
    main()