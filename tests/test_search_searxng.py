"""Tests for search_searxng.py — SearXNG search backend."""

import json
import pytest
from unittest.mock import patch, MagicMock

import requests


# ── score_source ─────────────────────────────

def test_score_source_gov_domain():
    from search_searxng import score_source
    score, tier = score_source("https://gov.sc.gov/document")
    assert score == 3
    assert tier == "primary"


def test_score_source_edu_domain():
    from search_searxng import score_source
    score, tier = score_source("https://law.stanford.edu/paper")
    assert score == 3
    assert tier == "primary"


def test_score_source_mil_domain():
    from search_searxng import score_source
    score, tier = score_source("https://www.defense.mil/report")
    assert score == 3
    assert tier == "primary"


def test_score_source_court_records():
    from search_searxng import score_source
    score, tier = score_source("https://www.courtlistener.com/case/123")
    assert score == 3
    assert tier == "primary"


def test_score_source_major_journalism():
    from search_searxng import score_source
    score, tier = score_source("https://www.reuters.com/article/something")
    assert score == 2
    assert tier == "secondary"


def test_score_source_academic_journal():
    from search_searxng import score_source
    score, tier = score_source("https://arxiv.org/abs/2301.12345")
    assert score == 2
    assert tier == "secondary"


def test_score_source_nonprofit():
    from search_searxng import score_source
    score, tier = score_source("https://www.eff.org/deeplinks/article")
    assert score == 2
    assert tier == "secondary"


def test_score_source_blog():
    from search_searxng import score_source
    score, tier = score_source("https://medium.com/@user/article")
    assert score == 1
    assert tier == "tertiary"


def test_score_source_reddit():
    from search_searxng import score_source
    score, tier = score_source("https://www.reddit.com/r/privacy/post")
    assert score == 1
    assert tier == "tertiary"


def test_score_source_unknown_domain():
    from search_searxng import score_source
    score, tier = score_source("https://randomsite.xyz/page")
    assert score == 1
    assert tier == "tertiary"


# ── search ───────────────────────────────────

def test_search_returns_scored_results():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": "https://gov.sc.gov/doc", "title": "Gov Doc", "content": "A gov document", "engine": "google"},
        {"url": "https://news.com/article", "title": "News", "content": "A news article", "engine": "google"},
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("ALPR surveillance SC", searxng_url="http://localhost:8888")
    assert len(results) == 2
    # Gov source should score higher
    gov = [r for r in results if "gov" in r["url"]][0]
    news = [r for r in results if "news" in r["url"]][0]
    assert gov["source_score"] > news["source_score"]


def test_search_empty_results():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("nonexistent topic xyz", searxng_url="http://localhost:8888")
    assert results == []


def test_search_connection_error():
    from search_searxng import search
    with patch("search_searxng.requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
        with pytest.raises(requests.exceptions.ConnectionError):
            search("test query", searxng_url="http://localhost:8888")


def test_search_http_error():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    with patch("search_searxng.requests.get", return_value=mock_resp):
        with pytest.raises(requests.exceptions.HTTPError):
            search("test query", searxng_url="http://localhost:8888")


def test_search_respects_max_results():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": f"https://example.com/page{i}", "title": f"Page {i}", "content": "", "engine": "google"}
        for i in range(20)
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("test", searxng_url="http://localhost:8888", max_results=5)
    assert len(results) == 5


def test_search_deduplicates_urls():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": "https://example.com/page", "title": "Page 1", "content": "First", "engine": "google"},
        {"url": "https://example.com/page", "title": "Page 1 Dup", "content": "Duplicate", "engine": "bing"},
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("test", searxng_url="http://localhost:8888")
    assert len(results) == 1


def test_search_sorts_by_score_descending():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": "https://medium.com/blog-post", "title": "Blog", "content": "", "engine": "google"},
        {"url": "https://www.reuters.com/article", "title": "Reuters", "content": "", "engine": "google"},
        {"url": "https://law.gov/doc", "title": "Law", "content": "", "engine": "google"},
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("test", searxng_url="http://localhost:8888")
    assert results[0]["source_quality"] == "primary"
    assert results[1]["source_quality"] == "secondary"
    assert results[2]["source_quality"] == "tertiary"


def test_search_passes_engines_param():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp) as mock_get:
        search("test", searxng_url="http://localhost:8888", engines=["google", "bing"])
    call_args = mock_get.call_args
    params = call_args[1]["params"]
    assert params["engines"] == "google,bing"


def test_search_skips_empty_urls():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": [
        {"url": "", "title": "Empty URL", "content": "", "engine": "google"},
        {"url": "https://example.com/real", "title": "Real", "content": "", "engine": "google"},
    ]}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp):
        results = search("test", searxng_url="http://localhost:8888")
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com/real"


def test_search_strips_trailing_slash_from_base_url():
    from search_searxng import search
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status = MagicMock()
    with patch("search_searxng.requests.get", return_value=mock_resp) as mock_get:
        search("test", searxng_url="http://localhost:8888/")
    call_url = mock_get.call_args[0][0]
    assert call_url == "http://localhost:8888/search"


# ── format_for_pipeline ──────────────────────

def test_format_for_pipeline_output_shape():
    from search_searxng import format_for_pipeline
    results = [
        {
            "url": "https://gov.sc.gov/doc",
            "title": "Gov Doc",
            "snippet": "A government document",
            "source_score": 3,
            "source_quality": "primary",
            "engine": "google",
        },
        {
            "url": "https://news.com/article",
            "title": "News Article",
            "snippet": "A news piece",
            "source_score": 1,
            "source_quality": "tertiary",
            "engine": "duckduckgo",
        },
    ]
    formatted = format_for_pipeline(results)
    assert len(formatted) == 2

    # Check required keys match search-agent output format
    required_keys = {"url", "title", "snippet", "relevance_score", "source_quality", "reason"}
    for entry in formatted:
        assert set(entry.keys()) == required_keys


def test_format_for_pipeline_relevance_scores():
    from search_searxng import format_for_pipeline
    results = [
        {"url": "u1", "title": "t1", "snippet": "s1", "source_score": 3, "source_quality": "primary", "engine": "g"},
        {"url": "u2", "title": "t2", "snippet": "s2", "source_score": 2, "source_quality": "secondary", "engine": "g"},
        {"url": "u3", "title": "t3", "snippet": "s3", "source_score": 1, "source_quality": "tertiary", "engine": "g"},
    ]
    formatted = format_for_pipeline(results)
    # Primary (3*2+2=8) > Secondary (2*2+2=6) > Tertiary (1*2+2=4)
    assert formatted[0]["relevance_score"] == 8
    assert formatted[1]["relevance_score"] == 6
    assert formatted[2]["relevance_score"] == 4


def test_format_for_pipeline_preserves_url_title_snippet():
    from search_searxng import format_for_pipeline
    results = [{
        "url": "https://example.com/page",
        "title": "Example Page",
        "snippet": "This is the snippet",
        "source_score": 2,
        "source_quality": "secondary",
        "engine": "bing",
    }]
    formatted = format_for_pipeline(results)
    assert formatted[0]["url"] == "https://example.com/page"
    assert formatted[0]["title"] == "Example Page"
    assert formatted[0]["snippet"] == "This is the snippet"


def test_format_for_pipeline_reason_includes_engine():
    from search_searxng import format_for_pipeline
    results = [{
        "url": "https://example.com",
        "title": "Ex",
        "snippet": "",
        "source_score": 1,
        "source_quality": "tertiary",
        "engine": "duckduckgo",
    }]
    formatted = format_for_pipeline(results)
    assert "duckduckgo" in formatted[0]["reason"]
    assert "tertiary" in formatted[0]["reason"]


def test_format_for_pipeline_empty_list():
    from search_searxng import format_for_pipeline
    assert format_for_pipeline([]) == []
