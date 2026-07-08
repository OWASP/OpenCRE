from dataclasses import dataclass

from .file_filter import FileFilter
from .models import FilteringMetrics


@dataclass
class FilteringBenchmarkResult:
    total_files: int
    retained_files: int
    filtered_files: int
    retention_rate: float
    filtering_rate: float


class FilteringBenchmark:
    def __init__(
        self,
        file_filter: FileFilter,
        metrics: FilteringMetrics,
    ):
        self.file_filter = file_filter
        self.metrics = metrics

    def run(self, file_paths: list[str]) -> FilteringBenchmarkResult:
        retained = self.file_filter.filter_files(file_paths)

        total = len(file_paths)
        retained_count = len(retained)
        filtered_count = total - retained_count

        return FilteringBenchmarkResult(
            total_files=total,
            retained_files=retained_count,
            filtered_files=filtered_count,
            retention_rate=(retained_count / total if total else 0.0),
            filtering_rate=(filtered_count / total if total else 0.0),
        )
