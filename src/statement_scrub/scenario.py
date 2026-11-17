"""Independent fictional bank ledger; no source values are inputs."""
from datetime import date, timedelta
from decimal import Decimal
import random


def money(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def generate(seed: int = 42, count: int = 8, year: int = 2025) -> dict[str, str]:
    if not 1 <= count <= 200 or not 2000 <= year <= 2099:
        raise ValueError("Use 1–200 transactions and a year between 2000 and 2099.")
    rng = random.Random(seed)  # Public fixture reproducibility, never a source-derived seed.
    opening = Decimal(rng.randrange(100000, 900000)) / 100
    balance, credits, debits = opening, Decimal(0), Decimal(0)
    values = {
        "identity.name": "FICTIEVE PERSOON", "identity.address": "Voorbeeldstraat 0",
        "identity.city": "0000 AA Teststad", "identity.account": "NL00 TEST 0000 0000 00",
        "identity.reference": "TEST-ONLY", "period.year": str(year),
        "period.start": f"01-01-{year}", "period.end": f"31-12-{year}",
        "account.opening": money(opening),
    }
    days = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    offsets = sorted(rng.sample(range(days), count))
    for i, offset in enumerate(offsets, 1):
        amount = Decimal(rng.randrange(1000, 35000)) / 100
        credit = i % 3 == 0
        balance += amount if credit else -amount
        credits += amount if credit else 0
        debits += 0 if credit else amount
        prefix = f"tx.{i}"
        values.update({
            f"{prefix}.date": (date(year, 1, 1) + timedelta(days=offset)).strftime("%d-%m-%Y"),
            f"{prefix}.description": f"TEST {'ONTVANGST' if credit else 'BETALING'} {i:03d}",
            f"{prefix}.amount": money(amount if credit else -amount),
            f"{prefix}.absolute": money(amount),
            f"{prefix}.credit": money(amount) if credit else "",
            f"{prefix}.debit": "" if credit else money(amount),
            f"{prefix}.direction": "Bij" if credit else "Af",
            f"{prefix}.balance": money(balance),
        })
    values.update({"account.closing": money(balance), "account.credits": money(credits),
                   "account.debits": money(debits)})
    assert opening + credits - debits == balance
    return values
