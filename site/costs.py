"""Every paid AI call -> data/costs.jsonl, and the totals the Transparência and Apoie pages show. Stdlib only.

  costs.log("ocr", "deepseek-flash", reply["usage"])   one line: {ts, pipeline, model, in, out, usd}
  costs.totals()                                        {usd_mes, usd_total, chamadas, por: {pipeline: usd}, desde}
Prices are USD per million tokens, BIOFUT_PRICE_IN / BIOFUT_PRICE_OUT (DeepSeek Flash list price at launch).
"""
import datetime as dt, json, os, threading
from pathlib import Path

LEDGER = Path(__file__).parent / "data" / "costs.jsonl"
PRICE_IN = float(os.environ.get("BIOFUT_PRICE_IN", "0.14"))
PRICE_OUT = float(os.environ.get("BIOFUT_PRICE_OUT", "0.28"))
LOCK = threading.Lock()


def log(pipeline, model, usage, ledger=None):
    """usage: the API's {prompt_tokens, completion_tokens}. Returns the USD of this call."""
    i, o = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    usd = round((i * PRICE_IN + o * PRICE_OUT) / 1e6, 6)
    row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "pipeline": pipeline, "model": model, "in": i, "out": o, "usd": usd}
    ledger = ledger or LEDGER
    with LOCK:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    return usd


def totals(ledger=None, today=None):
    ledger = ledger or LEDGER
    month = (today or dt.date.today()).isoformat()[:7]
    out = {"usd_mes": 0.0, "usd_total": 0.0, "chamadas": 0, "por": {}, "desde": None, "preco": [PRICE_IN, PRICE_OUT]}
    if not ledger.exists():
        return out
    with LOCK, ledger.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out["chamadas"] += 1
            out["usd_total"] += r["usd"]
            out["usd_mes"] += r["usd"] if r["ts"][:7] == month else 0
            out["por"][r["pipeline"]] = out["por"].get(r["pipeline"], 0) + r["usd"]
            out["desde"] = out["desde"] or r["ts"][:10]
    for k in ("usd_mes", "usd_total"):
        out[k] = round(out[k], 4)
    out["por"] = {k: round(v, 4) for k, v in out["por"].items()}
    return out


if __name__ == "__main__":
    import tempfile
    f = Path(tempfile.mkdtemp()) / "c.jsonl"
    assert totals(f)["chamadas"] == 0
    assert log("ocr", "m", {"prompt_tokens": 1_000_000, "completion_tokens": 0}, f) == PRICE_IN
    log("wiki", "m", {"prompt_tokens": 0, "completion_tokens": 1_000_000}, f)
    t = totals(f)
    assert t["chamadas"] == 2 and t["usd_total"] == round(PRICE_IN + PRICE_OUT, 4) and t["por"]["ocr"] == PRICE_IN and t["usd_mes"] == t["usd_total"]
    assert totals(f, dt.date(2000, 1, 1))["usd_mes"] == 0
    print("selftest ok")
