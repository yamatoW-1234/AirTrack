"""test_client_failures.py - checks that ogd_client fails gracefully.

Run from the repo root:
    python ingestion/test_client_failures.py

Case 1 (no key)       needs no network.
Case 2 (bad key)      needs internet: it sends a FAKE key to the real API.
Case 3 (no internet)  is simulated by pointing the client at a dead local address.
Your real key is never used, printed or changed on disk.
"""
import os

import ogd_client as c

STATION = "Anand Vihar, Delhi - DPCC"
FAKE_KEY = "this_is_a_fake_key_123"


def show(title, exc):
    print(" ", title, "->", type(exc).__name__ + ":", exc)


def test_no_key():
    os.environ.pop("OGD_API_KEY", None)          # remove the key for this process only
    try:
        c.fetch_station(STATION)
    except c.MissingApiKeyError as e:
        show("no key", e)
        print("PASS: no key")
        return
    raise AssertionError("expected MissingApiKeyError")


def test_bad_key():
    os.environ["OGD_API_KEY"] = FAKE_KEY
    try:
        c.fetch_station(STATION)
    except c.ApiRejectedError as e:
        show("bad key", e)
        assert FAKE_KEY not in str(e), "key must not appear in the error text"
        print("PASS: bad key")
        return
    except c.ApiUnavailableError as e:
        # The gateway answered 5xx for a bad key instead of 4xx. Still a graceful failure.
        show("bad key (gateway gave 5xx)", e)
        print("PASS (but note the status): bad key")
        return
    raise AssertionError("a fake key must not return data")


def test_api_down():
    os.environ["OGD_API_KEY"] = FAKE_KEY
    real_url, real_sleep = c.URL, c.time.sleep
    c.URL = "http://127.0.0.1:9/resource"        # nothing listens here -> connection refused
    c.time.sleep = lambda seconds: None          # skip the 5 s / 10 s waits so the test is fast
    try:
        c.fetch_station(STATION)
    except c.ApiUnavailableError as e:
        show("API down", e)
        assert FAKE_KEY not in str(e) and "127.0.0.1" not in str(e)
        print("PASS: API down")
        return
    finally:
        c.URL, c.time.sleep = real_url, real_sleep
    raise AssertionError("expected ApiUnavailableError")


if __name__ == "__main__":
    test_no_key()
    test_bad_key()
    test_api_down()
    print("\nALL FAILURE TESTS PASSED")
