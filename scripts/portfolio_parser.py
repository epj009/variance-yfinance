"""
Portfolio Parser Module

Handles CSV parsing, normalization, and position data extraction.
Extracted from analyze_portfolio.py to improve maintainability.
"""

import csv
import sys
from typing import Dict, List, Optional, TypedDict


class NormalizedPosition(TypedDict, total=False):
    """Type definition for a normalized position row."""
    Symbol: str
    Type: str
    Quantity: str
    Exp_Date: str
    DTE: str
    Strike_Price: str
    Call_Put: str
    Underlying_Last_Price: str
    PL_Open: str
    Cost: str
    IV_Rank: str
    beta_delta: str
    Theta: str
    Bid: str
    Ask: str
    Mark: str


class PortfolioParser:
    """
    Normalizes CSV headers from various broker exports to a standard internal format.
    """
    # Internal Key : [Possible CSV Headers]
    MAPPING = {
        'Symbol': ['Symbol', 'Sym', 'Ticker'],
        'Type': ['Type', 'Asset Class'],
        'Quantity': ['Quantity', 'Qty', 'Position', 'Size'],
        'Exp Date': ['Exp Date', 'Expiration', 'Expiry'],
        'DTE': ['DTE', 'Days To Expiration', 'Days to Exp'],
        'Strike Price': ['Strike Price', 'Strike'],
        'Call/Put': ['Call/Put', 'Side', 'C/P'],
        'Underlying Last Price': ['Underlying Last Price', 'Underlying Price', 'Current Price'],
        'P/L Open': ['P/L Open', 'P/L Day', 'Unrealized P/L'],
        'Cost': ['Cost', 'Cost Basis', 'Trade Price'],
        'IV Rank': ['IV Rank', 'IVR', 'IV Percentile'],
        'beta_delta': ['β Delta', 'Beta Delta', 'Delta Beta', 'Weighted Delta'],
        'Theta': ['Theta', 'Theta Daily', 'Daily Theta'],
        'Vega': ['Vega', '/ Vega'],
        'Gamma': ['Gamma', 'β Gamma', 'Beta Gamma'],
        'Value': ['Value', 'Mkt Value', 'Net Liq'],
        'Bid': ['Bid', 'Bid Price'],
        'Ask': ['Ask', 'Ask Price'],
        'Mark': ['Mark', 'Mark Price', 'Mid'],
        'Open Date': ['Open Date', "D's Opn", 'Days Open']
    }

    @staticmethod
    def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
        """
        Convert a raw CSV row into a normalized dictionary using MAPPING.

        Args:
            row: A single row from the CSV reader.

        Returns:
            A dictionary with standard keys (Symbol, Type, etc.) and normalized values.
        """
        normalized = {}
        for internal_key, aliases in PortfolioParser.MAPPING.items():
            found = False
            for alias in aliases:
                if alias in row:
                    val = row[alias]
                    # Canonicalize option side to keep strategy detection stable across casing
                    if internal_key == 'Call/Put' and val:
                        upper_val = str(val).strip().upper()
                        if upper_val == 'CALL':
                            val = 'Call'
                        elif upper_val == 'PUT':
                            val = 'Put'
                    normalized[internal_key] = val
                    found = True
                    break
            if not found:
                normalized[internal_key] = ""
        return normalized

    @staticmethod
    def parse(file_path: str) -> List[Dict[str, str]]:
        """
        Read and parse the CSV file at the given path.

        Args:
            file_path: Path to the CSV file.

        Returns:
            A list of normalized position rows.

        Raises:
            FileNotFoundError: If the file does not exist.
            csv.Error: If there's an error parsing the CSV.
        """
        positions = []
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    positions.append(PortfolioParser.normalize_row(row))
        except FileNotFoundError:
            print(f"Error: File not found: {file_path}", file=sys.stderr)
            raise
        except csv.Error as e:
            print(f"Error parsing CSV: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Error reading CSV: {e}", file=sys.stderr)
            raise
        return positions


def parse_currency(value: Optional[str]) -> float:
    """
    Clean and convert currency strings (e.g., '$1,234.56') to floats.

    Args:
        value: Currency string that may contain $, commas, or % symbols.

    Returns:
        Float value, or 0.0 if parsing fails.
    """
    if not value:
        return 0.0
    clean = value.replace(',', '').replace('$', '').replace('%', '').strip()
    if clean == '--':
        return 0.0
    try:
        return float(clean)
    except ValueError:
        return 0.0


def parse_dte(value: Optional[str]) -> int:
    """
    Clean and convert DTE strings (e.g., '45d') to integers.

    Args:
        value: DTE string that may contain 'd' suffix.

    Returns:
        Integer value, or 0 if parsing fails.
    """
    if not value:
        return 0
    clean = value.replace('d', '').strip()
    try:
        return int(clean)
    except ValueError:
        return 0


def get_root_symbol(raw_symbol: Optional[str]) -> str:
    """
    Extract the root symbol from a ticker, handling futures (e.g., /ESZ4 -> /ES).

    Args:
        raw_symbol: Raw symbol string that may include expiration codes.

    Returns:
        Root symbol string.
    """
    if not raw_symbol:
        return ""
    # Normalize multi-space and single-space separated symbols
    token = raw_symbol.strip().split()[0] if raw_symbol else ""

    # Handle Futures: ./CLG6 LOG6 ... -> /CL
    if token.startswith('./'):
        token = token.replace('./', '/')

    # Futures roots like /ESZ4 -> /ES
    if token.startswith('/') and len(token) >= 3:
        return token[:3]

    # Handle crypto/forex/class shares: ETH/USD -> ETH-USD, BRK/B -> BRK-B
    if '/' in token and not token.startswith('/'):
        token = token.replace('/', '-')

    return token


def is_stock_type(type_str: Optional[str]) -> bool:
    """
    Determine if a position leg is underlying stock/equity.

    Args:
        type_str: Type string from the position data.

    Returns:
        True if the type represents stock/equity, False otherwise.
    """
    if not type_str:
        return False
    normalized = type_str.strip().lower()
    return normalized in {"stock", "equity", "equities", "equity stock"}
