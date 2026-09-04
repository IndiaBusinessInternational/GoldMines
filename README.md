# IBI Gold Mines

Live gold price tracker for Indian cities with trend forecasts and a rule-based
**buy-the-dip signal**. Built by India Business International.

Live: https://gold.indiabusinessinternational.online/

## What it does

- **Live price** — 24K / 22K / 18K per gram, per 10 g and per sovereign (8 g), plus
  international spot and silver. Live spot from gold-api.com, USD/INR from the ECB
  (Frankfurter), calibrated to the **IBJA** benchmark (India Bullion and Jewellers
  Association) so the level matches Indian bullion.
- **Buy signal** — six standard technical checks scored out of 100 (RSI-14, distance
  from the 50/200-day averages, drawdown from the 52-week high, Bollinger position,
  20-day momentum) with a plain-English verdict, buy-zone price levels and a 10-year
  back-test of the rule.
- **Chart** — 10 years of daily history, moving averages, Bollinger band, a 3-month
  log-normal forecast cone, RSI panel, crosshair tooltip and a table view.
- **Forecast** — 1/3/6/12-month expected price with a likely range, cross-checked
  against a 6-month momentum model.
- **Coins & ornaments** — what you would pay today for coins/bars (24K) and typical
  22K pieces, and a jewellery bill calculator (weight × rate + making + GST).
- **Alerts** — target prices checked every minute while open; browser notifications.
- PWA (installable, offline shows the last saved history), light/dark themes.

## Data pipeline

`scripts/build_data.py` (stdlib only) writes `data/history.json`:

| Series | Source |
|---|---|
| `xauusd` | Yahoo Finance `GC=F`, 10 years daily |
| `usdinr` | Frankfurter (ECB reference rate) |
| `ibja` | ibjarates.com AM/PM tables, accumulated run over run |

`.github/workflows/data.yml` runs it at 13:00 and 18:00 IST on weekdays and commits
the file when it changes. Run it manually with `python scripts/build_data.py`.

## Method

Indian 24K price per gram = spot USD/oz ÷ 31.1035 × USD/INR × (1 + customs duty by
date) × IBJA calibration factor. 22K = 91.6%, 18K = 75%. Jewellers add making
charges and 3% GST — the app shows both the bullion rate and the bill.

Not investment advice.
