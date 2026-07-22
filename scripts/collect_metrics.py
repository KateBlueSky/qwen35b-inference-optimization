from __future__ import annotations

import csv
import json
import math
import re
import shutil
import statistics
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen
import os
import subprocess
import sys
import psutil
import uuid
import shutil

RESULTS_DIR = Path("results").resolve()
METRICS_URL = "http://127.0.0.1:8080/metrics"

SAMPLE_INTERVAL_SECONDS = 1.0
AGENT_TIMEOUT_SECONDS = 1800
CORRECTNESS_TIMEOUT_SECONDS = 300

ENABLE_PERF = True


PROMETHEUS_SAMPLE_RE = re.compile(
    r"""
    ^
    (?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)
    (?:
        \{
            (?P<labels>.*)
        \}
    )?
    \s+
    (?P<value>
        [-+]?
        (?:
            (?:\d+(?:\.\d*)?)
            |
            (?:\.\d+)
        )
        (?:[eE][-+]?\d+)?
        |
        NaN
        |
        [+-]?Inf
    )
    (?:
        \s+
        (?P<timestamp>\d+)
    )?
    $
    """,
    re.VERBOSE,
)

PROMETHEUS_LABEL_RE = re.compile(
    r'''
    (?P<name>[a-zA-Z_][a-zA-Z0-9_]*)
    =
    "
    (?P<value>(?:\\.|[^"\\])*)
    "
    (?:,|$)
    ''',
    re.VERBOSE,
)


def fetch_metrics() -> str:
    try:
        with urlopen(METRICS_URL, timeout=5) as response:
            return response.read().decode("utf-8")
    except Exception as exc:
        return f"# metrics unavailable: {exc}\n"


def safe_mean(values: list[float]) -> float | None:
    if not values:
        return None

    return round(statistics.fmean(values), 3)


def safe_max(values: list[float]) -> float | None:
    if not values:
        return None

    return round(max(values), 3)


def parse_number(value: str) -> float | None:
    cleaned = value.strip()

    if not cleaned or cleaned.lower() in {
        "n/a",
        "[not supported]",
        "not supported",
    }:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def perf_is_available() -> bool:
    if not ENABLE_PERF or shutil.which("perf") is None:
        return False

    try:
        completed = subprocess.run(
            [
                "perf",
                "stat",
                "-e",
                "task-clock",
                "--",
                "true",
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return completed.returncode == 0


def parse_prometheus_value(value: str) -> float | None:
    normalized = value.strip().lower()

    if normalized == "nan":
        return None

    if normalized in {"inf", "+inf"}:
        return math.inf

    if normalized == "-inf":
        return -math.inf

    try:
        return float(value)
    except ValueError:
        return None


def unescape_prometheus_label(value: str) -> str:
    return (
        value.replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
    )


def parse_prometheus_labels(
    labels_text: str | None,
) -> dict[str, str]:
    if not labels_text:
        return {}

    labels: dict[str, str] = {}
    position = 0

    while position < len(labels_text):
        match = PROMETHEUS_LABEL_RE.match(
            labels_text,
            position,
        )

        if match is None:
            break

        labels[match.group("name")] = unescape_prometheus_label(
            match.group("value")
        )

        position = match.end()

    return labels


def metric_sample_key(
    name: str,
    labels: dict[str, str],
) -> str:
    if not labels:
        return name

    label_string = ",".join(
        f'{key}="{value}"'
        for key, value in sorted(labels.items())
    )

    return f"{name}{{{label_string}}}"


def find_metric_metadata_name(
    sample_name: str,
    metadata: dict[str, dict[str, str]],
) -> str:
    if sample_name in metadata:
        return sample_name

    for suffix in (
        "_bucket",
        "_sum",
        "_count",
        "_created",
    ):
        if sample_name.endswith(suffix):
            base_name = sample_name[: -len(suffix)]

            if base_name in metadata:
                return base_name

    return sample_name


def parse_prometheus_metrics(text: str) -> dict[str, Any]:
    metadata: dict[str, dict[str, str]] = {}
    samples: dict[str, dict[str, Any]] = {}
    parse_errors: list[str] = []

    for line_number, raw_line in enumerate(
        text.splitlines(),
        start=1,
    ):
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("# HELP "):
            parts = line.split(" ", 3)

            if len(parts) == 4:
                metric_name = parts[2]
                metadata.setdefault(metric_name, {})["help"] = parts[3]

            continue

        if line.startswith("# TYPE "):
            parts = line.split()

            if len(parts) >= 4:
                metric_name = parts[2]
                metric_type = parts[3]

                metadata.setdefault(metric_name, {})[
                    "type"
                ] = metric_type

            continue

        if line.startswith("#"):
            continue

        match = PROMETHEUS_SAMPLE_RE.match(line)

        if match is None:
            parse_errors.append(
                f"Line {line_number}: could not parse: {raw_line}"
            )
            continue

        name = match.group("name")
        labels = parse_prometheus_labels(
            match.group("labels")
        )
        value = parse_prometheus_value(
            match.group("value")
        )
        timestamp_text = match.group("timestamp")

        metadata_name = find_metric_metadata_name(
            name,
            metadata,
        )
        metric_type = metadata.get(
            metadata_name,
            {},
        ).get("type", "untyped")

        key = metric_sample_key(name, labels)

        samples[key] = {
            "name": name,
            "labels": labels,
            "value": value,
            "timestamp": (
                int(timestamp_text)
                if timestamp_text is not None
                else None
            ),
            "type": metric_type,
        }

    return {
        "metadata": metadata,
        "samples": samples,
        "parse_errors": parse_errors,
    }


def finite_difference(
    after: float | None,
    before: float | None,
) -> float | None:
    if after is None or before is None:
        return None

    if not math.isfinite(after) or not math.isfinite(before):
        return None

    return after - before


def compare_prometheus_metrics(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_samples = before.get("samples", {})
    after_samples = after.get("samples", {})

    comparison: dict[str, dict[str, Any]] = {}

    all_keys = sorted(
        set(before_samples) | set(after_samples)
    )

    for key in all_keys:
        before_sample = before_samples.get(key)
        after_sample = after_samples.get(key)
        sample = after_sample or before_sample

        if sample is None:
            continue

        before_value = (
            before_sample.get("value")
            if before_sample is not None
            else None
        )
        after_value = (
            after_sample.get("value")
            if after_sample is not None
            else None
        )

        name = sample["name"]
        metric_type = sample.get("type", "untyped")

        is_counter_like = (
            metric_type == "counter"
            or name.endswith("_total")
            or name.endswith("_count")
            or name.endswith("_sum")
        )

        delta = (
            finite_difference(
                after_value,
                before_value,
            )
            if is_counter_like
            else None
        )

        counter_reset = (
            is_counter_like
            and delta is not None
            and delta < 0
        )

        if counter_reset:
            delta = None

        comparison[key] = {
            "name": name,
            "labels": sample.get("labels", {}),
            "type": metric_type,
            "before": before_value,
            "after": after_value,
            "delta": delta,
            "counter_reset_detected": counter_reset,
        }

    return comparison


def summarize_prometheus_comparison(
    comparison: dict[str, Any],
) -> dict[str, Any]:
    counter_deltas: dict[str, float] = {}
    gauges_after: dict[str, float] = {}

    for key, metric in comparison.items():
        delta = metric.get("delta")
        after = metric.get("after")
        metric_type = metric.get("type")

        if (
            isinstance(delta, (int, float))
            and math.isfinite(delta)
        ):
            counter_deltas[key] = round(
                float(delta),
                6,
            )

        if (
            metric_type == "gauge"
            and isinstance(after, (int, float))
            and math.isfinite(after)
        ):
            gauges_after[key] = round(
                float(after),
                6,
            )

    return {
        "counter_deltas": counter_deltas,
        "gauges_after": gauges_after,
    }


class SystemMonitor:
    def __init__(
        self,
        output_path: Path,
        interval_seconds: float = 1.0,
    ) -> None:
        self.output_path = output_path
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.rows: list[dict[str, float]] = []

    def start(self) -> None:
        psutil.cpu_percent(interval=None)

        self.thread = threading.Thread(
            target=self._run,
            name="system-monitor",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

        if self.thread is not None:
            self.thread.join(
                timeout=self.interval_seconds + 5
            )

        self._write_csv()

    def _run(self) -> None:
        start_time = time.perf_counter()

        while not self.stop_event.is_set():
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            self.rows.append(
                {
                    "elapsed_seconds": round(
                        time.perf_counter() - start_time,
                        3,
                    ),
                    "cpu_percent": psutil.cpu_percent(
                        interval=None
                    ),
                    "ram_used_gib": memory.used / (1024**3),
                    "ram_available_gib": (
                        memory.available / (1024**3)
                    ),
                    "ram_percent": memory.percent,
                    "swap_used_gib": swap.used / (1024**3),
                    "swap_percent": swap.percent,
                }
            )

            self.stop_event.wait(
                self.interval_seconds
            )

    def _write_csv(self) -> None:
        fieldnames = [
            "elapsed_seconds",
            "cpu_percent",
            "ram_used_gib",
            "ram_available_gib",
            "ram_percent",
            "swap_used_gib",
            "swap_percent",
        ]

        with self.output_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(self.rows)

    def summary(self) -> dict[str, float | None]:
        return {
            "cpu_average_percent": safe_mean(
                [
                    row["cpu_percent"]
                    for row in self.rows
                ]
            ),
            "cpu_peak_percent": safe_max(
                [
                    row["cpu_percent"]
                    for row in self.rows
                ]
            ),
            "ram_average_used_gib": safe_mean(
                [
                    row["ram_used_gib"]
                    for row in self.rows
                ]
            ),
            "ram_peak_used_gib": safe_max(
                [
                    row["ram_used_gib"]
                    for row in self.rows
                ]
            ),
            "ram_peak_percent": safe_max(
                [
                    row["ram_percent"]
                    for row in self.rows
                ]
            ),
            "swap_peak_used_gib": safe_max(
                [
                    row["swap_used_gib"]
                    for row in self.rows
                ]
            ),
        }


class NvidiaMonitor:
    QUERY_FIELDS = [
        "timestamp",
        "index",
        "name",
        "utilization.gpu",
        "utilization.memory",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
    ]

    def __init__(
        self,
        output_path: Path,
        interval_seconds: float = 1.0,
    ) -> None:
        self.output_path = output_path
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.rows: list[dict[str, Any]] = []
        self.error: str | None = None

    def start(self) -> None:
        if shutil.which("nvidia-smi") is None:
            self.error = "nvidia-smi was not found"
            return

        self.thread = threading.Thread(
            target=self._run,
            name="nvidia-monitor",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

        if self.thread is not None:
            self.thread.join(
                timeout=self.interval_seconds + 10
            )

        self._write_csv()

    def _sample(self) -> None:
        command = [
            "nvidia-smi",
            f"--query-gpu={','.join(self.QUERY_FIELDS)}",
            "--format=csv,noheader,nounits",
        ]

        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                completed.stderr.strip()
                or (
                    "nvidia-smi exited with "
                    f"{completed.returncode}"
                )
            )

        for line in completed.stdout.splitlines():
            values = [
                value.strip()
                for value in line.split(",")
            ]

            if len(values) != len(self.QUERY_FIELDS):
                continue

            raw = dict(
                zip(
                    self.QUERY_FIELDS,
                    values,
                )
            )

            self.rows.append(
                {
                    "sample_time_unix": time.time(),
                    "gpu_timestamp": raw["timestamp"],
                    "gpu_index": raw["index"],
                    "gpu_name": raw["name"],
                    "gpu_utilization_percent": parse_number(
                        raw["utilization.gpu"]
                    ),
                    "memory_utilization_percent": parse_number(
                        raw["utilization.memory"]
                    ),
                    "vram_used_mib": parse_number(
                        raw["memory.used"]
                    ),
                    "vram_total_mib": parse_number(
                        raw["memory.total"]
                    ),
                    "temperature_c": parse_number(
                        raw["temperature.gpu"]
                    ),
                    "power_draw_watts": parse_number(
                        raw["power.draw"]
                    ),
                }
            )

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._sample()
            except Exception as exc:
                self.error = str(exc)

            self.stop_event.wait(
                self.interval_seconds
            )

    def _write_csv(self) -> None:
        fieldnames = [
            "sample_time_unix",
            "gpu_timestamp",
            "gpu_index",
            "gpu_name",
            "gpu_utilization_percent",
            "memory_utilization_percent",
            "vram_used_mib",
            "vram_total_mib",
            "temperature_c",
            "power_draw_watts",
        ]

        with self.output_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(self.rows)

    def numeric_values(
        self,
        field: str,
    ) -> list[float]:
        values: list[float] = []

        for row in self.rows:
            value = row.get(field)

            if isinstance(value, (int, float)):
                values.append(float(value))

        return values

    def summary(self) -> dict[str, Any]:
        peak_vram_mib = safe_max(
            self.numeric_values("vram_used_mib")
        )
        average_vram_mib = safe_mean(
            self.numeric_values("vram_used_mib")
        )

        return {
            "gpu_monitor_error": self.error,
            "gpu_average_utilization_percent": safe_mean(
                self.numeric_values(
                    "gpu_utilization_percent"
                )
            ),
            "gpu_peak_utilization_percent": safe_max(
                self.numeric_values(
                    "gpu_utilization_percent"
                )
            ),
            "gpu_average_memory_utilization_percent": safe_mean(
                self.numeric_values(
                    "memory_utilization_percent"
                )
            ),
            "gpu_peak_vram_mib": peak_vram_mib,
            "gpu_peak_vram_gib": (
                round(peak_vram_mib / 1024, 3)
                if peak_vram_mib is not None
                else None
            ),
            "gpu_average_vram_mib": average_vram_mib,
            "gpu_average_power_watts": safe_mean(
                self.numeric_values(
                    "power_draw_watts"
                )
            ),
            "gpu_peak_power_watts": safe_max(
                self.numeric_values(
                    "power_draw_watts"
                )
            ),
            "gpu_peak_temperature_c": safe_max(
                self.numeric_values(
                    "temperature_c"
                )
            ),
        }


def run_command(
    command: list[str],
    cwd: Path,
    perf_output_path: Path | None = None,
    timeout_seconds: int = AGENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    actual_command = command
    perf_enabled = perf_output_path is not None

    if perf_enabled:
        actual_command = [
            "perf",
            "stat",
            "-o",
            str(perf_output_path),
            "-e",
            (
                "task-clock,"
                "context-switches,"
                "cpu-migrations,"
                "page-faults,"
                "cycles,"
                "instructions,"
                "branches,"
                "branch-misses"
            ),
            "--",
            *command,
        ]

    start = time.perf_counter()

    try:
        completed = subprocess.run(
            actual_command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )

        return {
            "exit_code": completed.returncode,
            "wall_time_seconds": (
                time.perf_counter() - start
            ),
            "output": completed.stdout,
            "timed_out": False,
            "perf_enabled": perf_enabled,
        }

    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""

        if isinstance(output, bytes):
            output = output.decode(
                "utf-8",
                errors="replace",
            )

        return {
            "exit_code": -1,
            "wall_time_seconds": (
                time.perf_counter() - start
            ),
            "output": output,
            "timed_out": True,
            "perf_enabled": perf_enabled,
        }


def run_correctness_check(
    command: list[str],
    cwd: Path,
    timeout_seconds: int = CORRECTNESS_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )

        return {
            "passed": completed.returncode == 0,
            "exit_code": completed.returncode,
            "output": completed.stdout,
            "timed_out": False,
        }

    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""

        if isinstance(output, bytes):
            output = output.decode(
                "utf-8",
                errors="replace",
            )

        return {
            "passed": False,
            "exit_code": -1,
            "output": output,
            "timed_out": True,
        }


def reset_working_directory(working_directory: Path) -> None:
    if working_directory.exists():
        shutil.rmtree(working_directory)

    working_directory.mkdir(parents=True, exist_ok=True)


def benchmark_task(
    name: str,
    agent_command: list[str],
    correctness_command: list[str],
    working_directory: Path,
    use_perf: bool,
) -> dict[str, Any]:
    working_directory = working_directory.resolve()

    if not working_directory.exists():
        raise FileNotFoundError(
            "Working directory does not exist: "
            f"{working_directory}"
        )

    reset_working_directory(working_directory)

    task_dir = RESULTS_DIR / name
    task_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    system_monitor = SystemMonitor(
        task_dir / "system.csv",
        SAMPLE_INTERVAL_SECONDS,
    )
    gpu_monitor = NvidiaMonitor(
        task_dir / "gpu.csv",
        SAMPLE_INTERVAL_SECONDS,
    )

    metrics_before_raw = fetch_metrics()
    metrics_before_parsed = parse_prometheus_metrics(
        metrics_before_raw
    )

    system_monitor.start()
    gpu_monitor.start()

    try:
        agent_result = run_command(
            command=agent_command,
            cwd=working_directory,
            perf_output_path=(
                task_dir / "perf.txt"
                if use_perf
                else None
            ),
        )
    finally:
        gpu_monitor.stop()
        system_monitor.stop()

    metrics_after_raw = fetch_metrics()
    metrics_after_parsed = parse_prometheus_metrics(
        metrics_after_raw
    )

    metrics_comparison = compare_prometheus_metrics(
        metrics_before_parsed,
        metrics_after_parsed,
    )
    metrics_summary = summarize_prometheus_comparison(
        metrics_comparison
    )

    correctness = run_correctness_check(
        correctness_command,
        working_directory,
    )

    (task_dir / "agent.log").write_text(
        agent_result["output"],
        encoding="utf-8",
    )

    (task_dir / "correctness.log").write_text(
        correctness["output"],
        encoding="utf-8",
    )

    (task_dir / "metrics-before.prom").write_text(
        metrics_before_raw,
        encoding="utf-8",
    )

    (task_dir / "metrics-after.prom").write_text(
        metrics_after_raw,
        encoding="utf-8",
    )

    (task_dir / "metrics-before.json").write_text(
        json.dumps(
            metrics_before_parsed,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    (task_dir / "metrics-after.json").write_text(
        json.dumps(
            metrics_after_parsed,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    (task_dir / "metrics-comparison.json").write_text(
        json.dumps(
            metrics_comparison,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    result = {
        "task": name,
        "wall_time_seconds": round(
            agent_result["wall_time_seconds"],
            3,
        ),
        "agent_exit_code": agent_result["exit_code"],
        "agent_timed_out": agent_result["timed_out"],
        "correctness_passed": correctness["passed"],
        "correctness_exit_code": correctness["exit_code"],
        "correctness_timed_out": correctness["timed_out"],
        "perf_enabled": agent_result["perf_enabled"],
        "prometheus_metrics": metrics_summary,
        "prometheus_parse_errors_before": len(
            metrics_before_parsed["parse_errors"]
        ),
        "prometheus_parse_errors_after": len(
            metrics_after_parsed["parse_errors"]
        ),
        **system_monitor.summary(),
        **gpu_monitor.summary(),
    }

    (task_dir / "result.json").write_text(
        json.dumps(
            result,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    return result


def flatten_result(
    result: dict[str, Any],
) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    for key, value in result.items():
        if isinstance(value, dict):
            flattened[key] = json.dumps(
                value,
                sort_keys=True,
            )
        else:
            flattened[key] = value

    return flattened


def write_summary(
    results: list[dict[str, Any]],
) -> None:
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    flattened_results = [
        flatten_result(result)
        for result in results
    ]

    fieldnames: list[str] = []
    seen_fields: set[str] = set()

    for result in flattened_results:
        for field in result:
            if field not in seen_fields:
                seen_fields.add(field)
                fieldnames.append(field)

    with (RESULTS_DIR / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(flattened_results)

    (RESULTS_DIR / "summary.json").write_text(
        json.dumps(
            results,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def main() -> None:
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    use_perf = perf_is_available()

    if ENABLE_PERF and not use_perf:
        print(
            "Warning: perf is unavailable or permission was denied. "
            "Benchmarks will run without perf stat."
        )

    tasks = [
         {
            "name": "hello-world",
            "agent_command": [
                "openclaw",
                "agent",
                "--agent",
                "main",
                "--session-id",
                str(uuid.uuid4()),
                "--message",
                (
                    "Create hello.py that prints Hello World and save "
                    "it in "
                    "current-directory/hello-world/hello.py"
                ),
            ],
            "correctness_command": [
                "bash",
                "-lc",
                'python hello.py | grep -qx "Hello World"',
            ],
            "working_directory": Path(
                "tasks/hello-world"
            ),
        },
        {
            "name": "two-sum",
            "agent_command": [
                "openclaw",
                "agent",
                "--agent",
                "main",
                "--session-id",
                str(uuid.uuid4()),
                "--message",
                (
                    "Create twoSum.py containing a function that finds "
                    "two numbers in a list that sum to a target. Also "
                    "create testTwoSum.py containing six pytest tests. "
                    "Save both files in the directory "
                    "current-directory/two-sum"
                ),
            ],
            "correctness_command": [
                sys.executable,
                "-m",
                "pytest",
                "testTwoSum.py",
                "-q",
            ],
            "working_directory": Path(
                "tasks/two-sum"
            ),
        }, 
        {
            "name": "refactor-test",
            "agent_command": [
                "openclaw",
                "agent",
                "--agent",
                "main",
                "--session-id",
                str(uuid.uuid4()),
                "--message",
                (   
                    "Can you refactor this code "
                    "def process_orders(orders): "
                    "total = 0 "
                    "for order in orders: "
                    "total += order['price'] * order['quantity'] "
                    "return total / len(orders) "
                    "make sure to handle edge cases "
                    "and create 6 pytest for the code. "
                    "place the code in a python file named calculator.py "
                    "in the directory current-directory/refactor"
                ),
            ],
            "correctness_command": [
                sys.executable,
                "-m",
                "pytest",
                "-q",
            ],
            "working_directory": Path(
                "tasks/refactor"
            ),
        }, 
    ]

    results: list[dict[str, Any]] = []
    print("tasks type:", type(tasks))
    print("tasks:", tasks)

    for task in tasks:
        print(
            f"Running benchmark: {task['name']}"
        )

        result = benchmark_task(
            name=task["name"],
            agent_command=task["agent_command"],
            correctness_command=task[
                "correctness_command"
            ],
            working_directory=task[
                "working_directory"
            ],
            use_perf=use_perf,
        )

        results.append(result)

        print(
            f"Finished {result['task']}: "
            f"{result['wall_time_seconds']} seconds, "
            f"correct={result['correctness_passed']}"
        )

    write_summary(results)

    print(
        f"Results written to {RESULTS_DIR}"
    )


if __name__ == "__main__":
    main()
