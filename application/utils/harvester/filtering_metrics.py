from .models import FilteringMetrics


class FilteringMetricsCollector:
    def __init__(self):
        self.total_files = 0
        self.retained_files = 0
        self.filtered_files = 0

    def record_retained(self) -> None:
        self.total_files += 1
        self.retained_files += 1

    def record_filtered(self) -> None:
        self.total_files += 1
        self.filtered_files += 1

    def build(self) -> FilteringMetrics:
        return FilteringMetrics(
            total_files=self.total_files,
            retained_files=self.retained_files,
            filtered_files=self.filtered_files,
        )
