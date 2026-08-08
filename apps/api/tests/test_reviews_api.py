"""Tests for the Review Explorer endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.seed import NON_DUPLICATE_REVIEWS, TOTAL_REVIEWS


class TestListing:
    def test_returns_a_page_envelope(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/reviews").json()

        assert set(body) == {"items", "meta"}
        assert body["meta"]["total_items"] == NON_DUPLICATE_REVIEWS

    def test_duplicates_are_hidden_by_default(self, seeded_client: TestClient) -> None:
        """The table must agree with the aggregate pages.

        Gold excludes duplicates, so a Review Explorer that showed them would
        make the site contradict itself — the fastest way to lose a user's
        trust in every other number.
        """
        body = seeded_client.get("/api/v1/reviews").json()

        assert body["meta"]["total_items"] == NON_DUPLICATE_REVIEWS
        assert all(not item["is_duplicate"] for item in body["items"])

    def test_duplicates_can_be_requested(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/reviews", params={"include_duplicates": True}).json()

        assert body["meta"]["total_items"] == TOTAL_REVIEWS

    def test_pagination_splits_without_overlap(self, seeded_client: TestClient) -> None:
        """A row must appear on exactly one page.

        Without a stable tiebreaker in ORDER BY, rows sharing a sort value can
        swap between pages: one is shown twice and another never appears.
        """
        first = seeded_client.get("/api/v1/reviews", params={"page_size": 5}).json()
        second = seeded_client.get("/api/v1/reviews", params={"page_size": 5, "page": 2}).json()

        first_ids = {item["id"] for item in first["items"]}
        second_ids = {item["id"] for item in second["items"]}
        assert len(first_ids) == 5
        assert not first_ids & second_ids

    def test_page_meta_is_consistent(self, seeded_client: TestClient) -> None:
        meta = seeded_client.get("/api/v1/reviews", params={"page_size": 5}).json()["meta"]

        assert meta["page"] == 1
        assert meta["total_pages"] == 3  # 13 rows in pages of 5
        assert meta["has_next"] is True
        assert meta["has_previous"] is False

    def test_page_size_is_capped(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/reviews", params={"page_size": 100_000})

        assert response.status_code == 422


class TestFiltering:
    def test_filters_by_brand(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/reviews", params={"brand": "Nimbus Drinks"}).json()

        assert body["meta"]["total_items"] == 6
        assert {item["brand"] for item in body["items"]} == {"Nimbus Drinks"}

    def test_filters_by_sentiment(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/reviews", params={"sentiment": "negative"}).json()

        assert all(item["sentiment"] == "negative" for item in body["items"])

    def test_filters_combine_as_and(self, seeded_client: TestClient) -> None:
        body = seeded_client.get(
            "/api/v1/reviews", params={"brand": "Aurora Foods", "sentiment": "negative"}
        ).json()

        for item in body["items"]:
            assert item["brand"] == "Aurora Foods"
            assert item["sentiment"] == "negative"

    def test_repeated_filter_values_are_an_or(self, seeded_client: TestClient) -> None:
        body = seeded_client.get(
            "/api/v1/reviews", params=[("country", "GB"), ("country", "US")]
        ).json()

        assert {item["country"] for item in body["items"]} <= {"GB", "US"}

    def test_filters_by_topic(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/reviews", params={"topic": "delivery"}).json()

        assert body["meta"]["total_items"] > 0
        assert all(item["primary_topic"] == "delivery" for item in body["items"])

    def test_topic_filter_does_not_duplicate_rows(self, seeded_client: TestClient) -> None:
        """A review matching several topics must still appear once.

        A join would return it once per matching topic and inflate the total.
        """
        body = seeded_client.get(
            "/api/v1/reviews", params=[("topic", "delivery"), ("topic", "price")]
        ).json()

        ids = [item["id"] for item in body["items"]]
        assert len(ids) == len(set(ids))
        assert body["meta"]["total_items"] == len(ids)

    def test_search_matches_review_text(self, seeded_client: TestClient) -> None:
        body = seeded_client.get("/api/v1/reviews", params={"q": "packaging"}).json()

        assert body["meta"]["total_items"] > 0
        assert all("packaging" in item["original_text"] for item in body["items"])

    def test_short_search_terms_are_ignored(self, seeded_client: TestClient) -> None:
        """Below three characters a trigram index cannot help.

        Ignoring the term is honest about that, rather than quietly running a
        full scan on every keystroke.
        """
        body = seeded_client.get("/api/v1/reviews", params={"q": "ab"}).json()

        assert body["meta"]["total_items"] == NON_DUPLICATE_REVIEWS


class TestSorting:
    def test_sorts_by_rating(self, seeded_client: TestClient) -> None:
        body = seeded_client.get(
            "/api/v1/reviews", params={"sort": "rating", "order": "asc"}
        ).json()

        ratings = [item["rating"] for item in body["items"]]
        assert ratings == sorted(ratings)

    def test_unknown_sort_column_falls_back_safely(self, seeded_client: TestClient) -> None:
        """An allow-list, not a passthrough: the value never reaches SQL."""
        response = seeded_client.get(
            "/api/v1/reviews", params={"sort": "rating; DROP TABLE reviews"}
        )

        assert response.status_code == 200
        assert response.json()["meta"]["total_items"] == NON_DUPLICATE_REVIEWS


class TestDetail:
    def test_returns_processing_provenance(self, seeded_client: TestClient) -> None:
        """ "Why is this negative?" must be answerable from the response."""
        listing = seeded_client.get("/api/v1/reviews").json()
        review_id = listing["items"][0]["id"]

        detail = seeded_client.get(f"/api/v1/reviews/{review_id}").json()

        assert detail["sentiment_model_version"] == "lexicon-v1"
        assert detail["normalized_text"] is not None
        assert detail["topics"]
        assert detail["topics"][0]["matched_keywords"]

    def test_unknown_id_is_a_404(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/reviews/00000000-0000-5000-8000-000000000000")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_malformed_id_is_a_422(self, seeded_client: TestClient) -> None:
        response = seeded_client.get("/api/v1/reviews/not-a-uuid")

        assert response.status_code == 422


class TestFacets:
    def test_facets_route_is_not_shadowed_by_the_id_route(self, seeded_client: TestClient) -> None:
        """`/reviews/facets` must not parse "facets" as a review id.

        It only works because the literal path is declared first.
        """
        response = seeded_client.get("/api/v1/reviews/facets")

        assert response.status_code == 200

    def test_facets_come_from_the_data(self, seeded_client: TestClient) -> None:
        facets = seeded_client.get("/api/v1/reviews/facets").json()

        assert facets["brands"] == ["Aurora Foods", "Nimbus Drinks"]
        assert "delivery" in facets["topics"]
        assert set(facets["sentiments"]) <= {"positive", "neutral", "negative", "unknown"}
