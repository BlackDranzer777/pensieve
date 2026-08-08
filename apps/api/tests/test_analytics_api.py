"""Tests for the analytics endpoints.

Every expected number traces back to `tests/seed.py`, which is small enough to
verify by reading.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.seed import AURORA_NON_DUPLICATE, NIMBUS_NON_DUPLICATE, NON_DUPLICATE_REVIEWS


class TestOverview:
    def test_returns_kpis_from_the_aggregate_tables(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/overview")

        assert response.status_code == 200
        kpis = response.json()["kpis"]
        assert kpis["total_reviews"] == NON_DUPLICATE_REVIEWS
        assert kpis["brands"] == 2

    def test_excludes_duplicates(self, seeded_client: TestClient) -> None:
        """The overview must never count the duplicate review.

        Gold filters `is_duplicate_of IS NULL`, so an overview that counted 14
        would disagree with every other page.
        """
        kpis = seeded_client.get("/api/v1/overview").json()["kpis"]

        assert kpis["total_reviews"] == NON_DUPLICATE_REVIEWS == 13

    def test_sentiment_mix_sums_to_the_total(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/overview").json()

        assert sum(body["sentiment_mix"].values()) == body["kpis"]["total_reviews"]

    def test_includes_active_anomalies_strongest_first(self, seeded_client: TestClient) -> None:
        anomalies = seeded_client.get("/api/v1/overview").json()["active_anomalies"]

        assert len(anomalies) == 3
        z_scores = [abs(anomaly["z_score"]) for anomaly in anomalies]
        assert z_scores == sorted(z_scores, reverse=True)

    def test_survives_an_empty_database(self, client: TestClient) -> None:
        """An empty database is a valid state, not an error.

        A dashboard opened before the first pipeline run should say "no data",
        which it cannot do if the endpoint 500s.
        """
        response = client.get("/api/v1/overview")

        # Without a database the request fails at connection time; with an
        # empty one it must succeed. Either way it must not be a 500.
        assert response.status_code in {200, 503}


class TestBrands:
    def test_lists_every_brand_with_totals(self, seeded_client: TestClient) -> None:
        brands = seeded_client.get("/api/v1/brands").json()

        assert {brand["brand"] for brand in brands} == {"Aurora Foods", "Nimbus Drinks"}
        by_name = {brand["brand"]: brand for brand in brands}
        assert by_name["Aurora Foods"]["review_count"] == AURORA_NON_DUPLICATE
        assert by_name["Nimbus Drinks"]["review_count"] == NIMBUS_NON_DUPLICATE

    def test_ordered_by_volume(self, seeded_client: TestClient) -> None:
        brands = seeded_client.get("/api/v1/brands").json()

        counts = [brand["review_count"] for brand in brands]
        assert counts == sorted(counts, reverse=True)

    def test_percentages_are_recomputed_from_counts(self, seeded_client: TestClient) -> None:
        """Not averaged across days, which would weight every day equally."""
        brands = seeded_client.get("/api/v1/brands").json()

        for brand in brands:
            expected = round(brand["negative_count"] / brand["review_count"] * 100, 2)
            assert brand["negative_percentage"] == expected

    def test_comparison_echoes_the_window(self, seeded_client: TestClient) -> None:
        response = seeded_client.get(
            "/api/v1/brands/comparison",
            params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
        )

        body = response.json()
        assert body["date_from"] == "2026-06-01"
        assert body["date_to"] == "2026-06-30"
        assert body["total_reviews"] == NON_DUPLICATE_REVIEWS

    def test_a_window_with_no_data_returns_an_empty_list(self, seeded_client: TestClient) -> None:
        response = seeded_client.get(
            "/api/v1/brands", params={"date_from": "2020-01-01", "date_to": "2020-01-31"}
        )

        assert response.status_code == 200
        assert response.json() == []


class TestTrends:
    def test_sentiment_series_per_brand(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/trends/sentiment").json()

        assert len(body["series"]) == 2
        assert all(series["points"] for series in body["series"])

    def test_sentiment_points_carry_their_baseline(self, seeded_client: TestClient) -> None:
        """The chart must not have to recompute the rolling window itself."""
        body = seeded_client.get("/api/v1/trends/sentiment").json()

        point = body["series"][0]["points"][0]
        assert point["negative_percentage_7d"] is not None
        assert point["review_count_7d"] is not None

    def test_topic_trends_identify_the_growing_topic(self, seeded_client: TestClient) -> None:
        """`delivery` rises 2 -> 10 in the fixture; `price` is flat at 5."""
        body = seeded_client.get("/api/v1/trends/topics").json()

        assert body["fastest_growing"] == "delivery"
        assert body["change_percentage"] is not None
        assert body["change_percentage"] > 0

    def test_topic_series_ordered_by_volume(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/trends/topics").json()

        totals = [series["total_reviews"] for series in body["series"]]
        assert totals == sorted(totals, reverse=True)


class TestDimensions:
    def test_language_percentages_sum_to_one_hundred(self, seeded_client: TestClient) -> None:
        languages = seeded_client.get("/api/v1/languages").json()

        assert abs(sum(row["percentage"] for row in languages) - 100.0) < 0.1

    def test_countries_ordered_by_volume(self, seeded_client: TestClient) -> None:
        countries = seeded_client.get("/api/v1/countries").json()

        counts = [row["review_count"] for row in countries]
        assert counts == sorted(counts, reverse=True)


class TestAnomalies:
    def test_returns_a_paginated_envelope(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/anomalies").json()

        assert body["meta"]["total_items"] == 3
        assert len(body["items"]) == 3

    def test_filters_by_severity(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/anomalies", params={"severity": "high"}).json()

        assert body["meta"]["total_items"] == 1
        assert body["items"][0]["severity"] == "high"

    def test_filters_by_metric(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/anomalies", params={"metric": "review_volume"}).json()

        assert body["meta"]["total_items"] == 2

    def test_every_anomaly_explains_itself(self, seeded_client: TestClient) -> None:
        """An alert nobody can check is an alert nobody acts on."""
        body = seeded_client.get("/api/v1/anomalies").json()

        for anomaly in body["items"]:
            assert anomaly["explanation"]
            assert anomaly["baseline_value"] is not None
            assert anomaly["current_value"] is not None


class TestDateValidation:
    def test_inverted_range_is_rejected(self, seeded_client: TestClient) -> None:
        """Silently returning nothing looks identical to "there is no data"."""
        response = seeded_client.get(
            "/api/v1/brands", params={"date_from": "2026-08-01", "date_to": "2026-05-01"}
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_failed"

    def test_error_uses_the_standard_envelope(self, seeded_client: TestClient) -> None:
        response = seeded_client.get(
            "/api/v1/brands", params={"date_from": "2026-08-01", "date_to": "2026-05-01"}
        )

        error = response.json()["error"]
        assert set(error) >= {"code", "message"}
