import unittest
from unittest.mock import Mock

from app.integrations.gsc.service import get_search_performance


class GetSearchPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.execution = Mock()
        self.execution.execute.return_value = {"rows": [{"clicks": 2}]}
        self.query = Mock(return_value=self.execution)
        self.service = Mock()
        self.service.searchanalytics.return_value.query = self.query

    def test_sends_requested_dimensions(self):
        rows = get_search_performance(
            service=self.service,
            site_url="https://example.com/",
            start_date="2026-10-01",
            end_date="2026-10-31",
            dimensions=["query", "page"],
        )

        self.query.assert_called_once_with(
            siteUrl="https://example.com/",
            body={
                "startDate": "2026-10-01",
                "endDate": "2026-10-31",
                "rowLimit": 25000,
                "dimensions": ["query", "page"],
            },
        )
        self.assertEqual(rows, [{"clicks": 2}])

    def test_omits_dimensions_when_not_requested(self):
        get_search_performance(
            service=self.service,
            site_url="https://example.com/",
            start_date="2026-10-01",
            end_date="2026-10-31",
        )

        self.query.assert_called_once_with(
            siteUrl="https://example.com/",
            body={
                "startDate": "2026-10-01",
                "endDate": "2026-10-31",
                "rowLimit": 25000,
            },
        )


if __name__ == "__main__":
    unittest.main()
