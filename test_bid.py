#!/usr/bin/env python3
"""Simple OpenRTB test client for Instigator DSP"""
import json
import httpx

SAMPLE_BID_REQUEST = {
    "id": "test-request-001",
    "imp": [{"id": "1", "banner": {"w": 300, "h": 250}}],
    "device": {
        "geo": {"country": "GE"},
        "ua": "Mozilla/5.0"
    },
    "site": {"domain": "example.com"}
}

def test_bid(url="http://localhost:8000/openrtb/bid"):
    print(f"Sending test bid request to {url}")
    print("Request:", json.dumps(SAMPLE_BID_REQUEST, indent=2))
    with httpx.Client() as client:
        resp = client.post(url, json=SAMPLE_BID_REQUEST)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print("Bid Response:", json.dumps(resp.json(), indent=2))
        elif resp.status_code == 204:
            print("No bid (expected if no matching campaign)")
        else:
            print(resp.text)

if __name__ == "__main__":
    test_bid()
