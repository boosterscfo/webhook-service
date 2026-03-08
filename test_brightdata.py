"""Bright Data Web Scraper API 테스트 - Hair Growth Products BSR Top 3"""
import asyncio
import json
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("BRIGHT_DATA_API_TOKEN")
DATASET_ID = os.getenv("BRIGHT_DATA_DATASET_ID")
BASE_URL = "https://api.brightdata.com/datasets/v3"


async def main():
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    # Step 1: Trigger collection
    trigger_url = (
        f"{BASE_URL}/trigger"
        f"?dataset_id={DATASET_ID}"
        f"&type=discover_new"
        f"&discover_by=best_sellers_url"
        f"&limit_per_input=3"
    )
    body = [{"category_url": "https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281"}]

    print("=== Step 1: Trigger ===")
    print(f"URL: {trigger_url}")
    print(f"Body: {json.dumps(body)}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(trigger_url, headers=headers, json=body)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

        if resp.status_code != 200:
            print("Trigger failed!")
            return

        result = resp.json()
        snapshot_id = result.get("snapshot_id")
        if not snapshot_id:
            print(f"No snapshot_id in response: {result}")
            return

        print(f"\nSnapshot ID: {snapshot_id}")

        # Step 2: Poll for results
        snapshot_url = f"{BASE_URL}/snapshot/{snapshot_id}?format=json"
        print(f"\n=== Step 2: Polling ({snapshot_url}) ===")

        for attempt in range(30):
            await asyncio.sleep(10)
            print(f"Poll attempt {attempt + 1}/30...")

            resp = await client.get(snapshot_url, headers=headers)
            print(f"  Status: {resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()
                print(f"\n=== Results: {len(data)} products ===")

                # Save full result
                with open("reference/brightdata_test_result.json", "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("Saved to reference/brightdata_test_result.json")

                # Print summary
                for i, product in enumerate(data):
                    print(f"\n--- Product {i+1} ---")
                    print(f"ASIN: {product.get('asin')}")
                    print(f"Title: {product.get('title', '')[:100]}")
                    print(f"Brand: {product.get('brand')}")
                    print(f"Price: {product.get('final_price')} {product.get('currency', 'USD')}")
                    print(f"Rating: {product.get('rating')}")
                    print(f"Reviews: {product.get('reviews_count')}")
                    print(f"BSR Rank: {product.get('rank')}")
                    print(f"BSR Category: {product.get('root_category')}")

                    ing = product.get("ingredients", "")
                    if ing:
                        suffix = "..." if len(ing) > 120 else ""
                        print(f"Ingredients: {ing[:120]}{suffix}")
                    else:
                        print("Ingredients: (none)")

                    features = product.get("features")
                    if features:
                        print(f"Features: {json.dumps(features, ensure_ascii=False)[:200]}")
                return

            elif resp.status_code == 202:
                print("  Still processing...")
            else:
                print(f"  Unexpected: {resp.text[:200]}")

        print("Timed out after 30 attempts")


if __name__ == "__main__":
    asyncio.run(main())
