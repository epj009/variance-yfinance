import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "scripts")))

try:
    from check_all_api_fields import check_all_fields
except ImportError:
    # Fallback if scripts not in path or import fails
    print("Could not import check_all_fields. Copying logic...")
    import pprint

    from variance.tastytrade_client import TastytradeClient

    def check_all_fields(symbols: list[str] | None = None) -> None:
        if symbols is None:
            symbols = []
        client = TastytradeClient()
        token = client._ensure_valid_token()
        url = f"{client.api_base_url}/market-metrics"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {"symbols": ",".join(symbols)}
        data = client._fetch_api_data(url, headers, params)
        if data and "data" in data and "items" in data["data"]:
            for item in data["data"]["items"]:
                print(f"\n--- {item.get('symbol')} ---")
                pprint.pprint(item)


if __name__ == "__main__":
    check_all_fields(["/ES", "/CL", "/NG"])
