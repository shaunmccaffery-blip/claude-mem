#!/usr/bin/env python3
"""
REAL DIFFICULTY WARNING — The code is easy. Getting non-hallucinated, non-biased
probabilities is hard. Use local 70B+ model + self-critique + calibration examples.
Paper trade for minimum 2 weeks.

Polymarket Edge-Scanner & Signal Bot (2026-safe baseline)
- Math-first, ultra-selective scanner
- Manual-review-first workflow (default)
- Optional Telegram + webhook + dry-run auto execution
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import os
import sqlite3
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

try:
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None

try:
    from telegram import Bot
except Exception:  # pragma: no cover
    Bot = None

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
    import uvicorn
except Exception:  # pragma: no cover
    FastAPI = None
    BaseModel = object
    uvicorn = None

# Optional deps only used in auto execution mode.
try:
    from polymarket import Polymarket
except Exception:  # pragma: no cover
    Polymarket = None

try:
    from web3 import Web3
except Exception:  # pragma: no cover
    Web3 = None


DEFAULT_CONFIG_PATH = "config.yaml"


@dataclass
class Position:
    condition_id: str
    side: str
    market_question: str
    entry_price: float
    stake_usd: float
    subjective_prob_yes: float
    edge: float
    timestamp_utc: str


@dataclass
class BotConfig:
    bankroll_usd: float = 5000.0
    scan_interval_minutes: int = 45
    min_markets: int = 40
    max_markets: int = 100
    edge_threshold: float = 0.08
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.25
    max_total_open_risk_pct: float = 0.55
    max_signals_per_day: int = 4
    min_signals_per_day: int = 0
    min_price: float = 0.05
    max_price: float = 0.95
    controversial_keywords: List[str] = field(
        default_factory=lambda: [
            "election",
            "war",
            "abortion",
            "immigration",
            "conflict",
            "israel",
            "gaza",
            "ukraine",
            "china",
            "trump",
            "biden",
        ]
    )

    llm_provider: str = "ollama"
    llm_model: str = "llama3.1:70b"
    llm_temperature: float = 0.0
    llm_top_p: float = 0.95
    llm_timeout_seconds: int = 45
    llm_self_critique: bool = True
    llm_enable_cot_for_controversial: bool = True
    llm_fewshot_examples: List[Dict[str, Any]] = field(default_factory=list)

    gamma_api_base: str = "https://gamma-api.polymarket.com"
    graph_api_url: str = "https://api.thegraph.com/subgraphs/name/protofire/polymarket-matic"
    request_timeout_seconds: int = 20
    cache_ttl_seconds: int = 180

    dry_run: bool = True
    execution_enabled: bool = False

    telegram_enabled: bool = False
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080

    log_jsonl_path: str = "logs/decisions.jsonl"
    db_path: str = "logs/polymarket_bot.db"


def load_config(path: str) -> BotConfig:
    load_dotenv(override=False)
    cfg = BotConfig()
    file_data: Dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        file_data = yaml.safe_load(p.read_text()) or {}

    for key, value in file_data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    # env overrides (selected)
    env_map = {
        "POLY_BANKROLL_USD": ("bankroll_usd", float),
        "POLY_EDGE_THRESHOLD": ("edge_threshold", float),
        "POLY_KELLY_FRACTION": ("kelly_fraction", float),
        "POLY_LLM_PROVIDER": ("llm_provider", str),
        "POLY_LLM_MODEL": ("llm_model", str),
        "POLY_DRY_RUN": ("dry_run", lambda x: x.lower() == "true"),
        "POLY_EXECUTION_ENABLED": ("execution_enabled", lambda x: x.lower() == "true"),
        "POLY_TELEGRAM_ENABLED": ("telegram_enabled", lambda x: x.lower() == "true"),
    }
    for env_name, (attr, caster) in env_map.items():
        v = os.getenv(env_name)
        if v is not None:
            setattr(cfg, attr, caster(v))

    return cfg


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("polymarket_bot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(h)
    return logger


class DecisionLogger:
    def __init__(self, jsonl_path: str, db_path: str):
        self.jsonl_path = Path(jsonl_path)
        self.db_path = Path(db_path)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                condition_id TEXT,
                question TEXT,
                market_price REAL,
                prob_yes REAL,
                edge REAL,
                side TEXT,
                stake_usd REAL,
                action TEXT,
                metadata_json TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pnl_resolved (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                condition_id TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stake_usd REAL NOT NULL,
                outcome_yes INTEGER NOT NULL,
                gross_pnl REAL NOT NULL,
                log_return REAL NOT NULL,
                metadata_json TEXT
            )
            """
        )
        con.commit()
        con.close()

    def log_decision(self, payload: Dict[str, Any]) -> None:
        row = dict(payload)
        row.setdefault("ts_utc", utc_now())
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO decisions (ts_utc, condition_id, question, market_price, prob_yes, edge, side, stake_usd, action, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("ts_utc"),
                row.get("condition_id"),
                row.get("question"),
                row.get("market_price"),
                row.get("prob_yes"),
                row.get("edge"),
                row.get("side"),
                row.get("stake_usd"),
                row.get("action"),
                json.dumps(row.get("metadata", {})),
            ),
        )
        con.commit()
        con.close()

    def log_resolved_position(
        self,
        condition_id: str,
        side: str,
        entry_price: float,
        stake_usd: float,
        outcome_yes: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        payoff = stake_usd * ((1.0 / entry_price) - 1.0) if side == "YES" and outcome_yes else 0.0
        if side == "NO":
            no_price = max(1e-6, 1.0 - entry_price)
            payoff = stake_usd * ((1.0 / no_price) - 1.0) if not outcome_yes else 0.0
        gross_pnl = payoff - stake_usd
        gross_return = gross_pnl / max(stake_usd, 1e-9)
        log_return = math.log1p(gross_return)

        con = sqlite3.connect(self.db_path)
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO pnl_resolved (ts_utc, condition_id, side, entry_price, stake_usd, outcome_yes, gross_pnl, log_return, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                condition_id,
                side,
                entry_price,
                stake_usd,
                1 if outcome_yes else 0,
                gross_pnl,
                log_return,
                json.dumps(metadata or {}),
            ),
        )
        con.commit()
        con.close()
        return {"gross_pnl": gross_pnl, "log_return": log_return}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DataClient:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self._cache: Dict[str, Tuple[float, Any]] = {}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        r = requests.get(url, params=params, timeout=self.cfg.request_timeout_seconds)
        r.raise_for_status()
        return r.json()

    def _from_cache(self, key: str) -> Optional[Any]:
        found = self._cache.get(key)
        if not found:
            return None
        ts, payload = found
        if time.time() - ts <= self.cfg.cache_ttl_seconds:
            return payload
        return None

    def _to_cache(self, key: str, payload: Any) -> None:
        self._cache[key] = (time.time(), payload)

    def fetch_active_markets(self, limit: int) -> List[Dict[str, Any]]:
        key = f"markets:{limit}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached

        gamma_url = f"{self.cfg.gamma_api_base}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "offset": 0,
            "archived": "false",
        }
        gamma_markets = self._get_json(gamma_url, params=params)

        graph_markets = self._fetch_graph_supplement(limit)
        graph_by_condition = {m.get("conditionId"): m for m in graph_markets}

        merged: List[Dict[str, Any]] = []
        for m in gamma_markets:
            cid = str(m.get("conditionId") or m.get("condition_id") or "")
            g = graph_by_condition.get(cid, {})
            last_price = float(
                m.get("lastTradePrice")
                or m.get("outcomePrices", [None])[0]
                or m.get("probability")
                or 0.5
            )
            market = {
                "condition_id": cid,
                "question": m.get("question") or m.get("title") or "",
                "description": m.get("description") or "",
                "category": m.get("category") or g.get("category") or "",
                "end_date": m.get("endDate") or m.get("endDateIso") or "",
                "yes_price": min(max(last_price, 0.0), 1.0),
                "volume": float(m.get("volume") or g.get("volume") or 0.0),
                "liquidity": float(m.get("liquidity") or g.get("liquidity") or 0.0),
                "url": m.get("url") or f"https://polymarket.com/event/{cid}",
            }
            if self.cfg.min_price <= market["yes_price"] <= self.cfg.max_price:
                merged.append(market)

        merged = sorted(merged, key=lambda x: (x["liquidity"], x["volume"]), reverse=True)
        merged = merged[:limit]
        self._to_cache(key, merged)
        return merged

    def fetch_market_by_condition_id(self, condition_id: str) -> Optional[Dict[str, Any]]:
        markets = self.fetch_active_markets(limit=self.cfg.max_markets)
        for m in markets:
            if str(m.get("condition_id")) == str(condition_id):
                return m
        return None

    def _fetch_graph_supplement(self, limit: int) -> List[Dict[str, Any]]:
        key = f"graph:{limit}"
        cached = self._from_cache(key)
        if cached is not None:
            return cached

        q = {
            "query": textwrap.dedent(
                f"""
                query Markets {{
                  markets(first: {limit}, orderBy: liquidity, orderDirection: desc) {{
                    id
                    conditionId
                    liquidity
                    volume
                    category
                  }}
                }}
                """
            )
        }
        try:
            r = requests.post(self.cfg.graph_api_url, json=q, timeout=self.cfg.request_timeout_seconds)
            r.raise_for_status()
            data = r.json().get("data", {}).get("markets", [])
        except Exception:
            data = []
        self._to_cache(key, data)
        return data


class ProbabilityEngine:
    SYSTEM_LINE = (
        "You are a perfectly calibrated, zero-bias forecasting oracle. "
        "Output ONLY a float 0.000–1.000. No explanation."
    )

    def __init__(self, cfg: BotConfig, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if OpenAI and os.getenv("OPENAI_API_KEY") else None
        self._anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) if anthropic and os.getenv("ANTHROPIC_API_KEY") else None

    def predict_yes_probability(self, market: Dict[str, Any]) -> float:
        prompt = self._build_prompt(market)
        p1 = self._call_model(prompt)

        if self.cfg.llm_self_critique:
            critique_prompt = self._build_critique_prompt(market, p1)
            p2 = self._call_model(critique_prompt)
            return clamp01((p1 + p2) / 2.0)
        return clamp01(p1)

    def _fewshot_block(self) -> str:
        if not self.cfg.llm_fewshot_examples:
            return ""
        chunks = ["Calibration examples:"]
        for ex in self.cfg.llm_fewshot_examples:
            chunks.append(
                f"Market: {ex.get('market')} | Context: {ex.get('context')} | True-ish P(YES): {ex.get('p_yes')}"
            )
        return "\n".join(chunks)

    def _is_controversial(self, q: str) -> bool:
        ql = q.lower()
        return any(k in ql for k in self.cfg.controversial_keywords)

    def _build_prompt(self, market: Dict[str, Any]) -> str:
        cot_flag = self.cfg.llm_enable_cot_for_controversial and self._is_controversial(market.get("question", ""))
        cot_hint = (
            "Internally reason step-by-step; do not reveal reasoning. "
            if cot_flag
            else ""
        )
        return textwrap.dedent(
            f"""
            {self.SYSTEM_LINE}
            {cot_hint}
            {self._fewshot_block()}
            Market question: {market.get('question')}
            Description: {market.get('description')}
            Category: {market.get('category')}
            End date: {market.get('end_date')}
            Current market P(YES): {market.get('yes_price'):.3f}
            Return only one number like 0.613
            """
        ).strip()

    def _build_critique_prompt(self, market: Dict[str, Any], first_prob: float) -> str:
        return textwrap.dedent(
            f"""
            {self.SYSTEM_LINE}
            First estimate was {first_prob:.3f}. Critique bias risks (recency, political, availability), then revise.
            Internally self-critique, output only final calibrated float.
            Market: {market.get('question')}
            Description: {market.get('description')}
            """
        ).strip()

    def _call_model(self, prompt: str) -> float:
        provider = self.cfg.llm_provider.lower().strip()
        if provider == "ollama":
            return self._call_ollama(prompt)
        if provider == "openai":
            return self._call_openai(prompt)
        if provider == "anthropic":
            return self._call_anthropic(prompt)
        raise ValueError(f"Unsupported llm_provider={provider}")

    def _extract_float(self, text: str) -> float:
        raw = text.strip().replace("%", "")
        token = raw.split()[0]
        return clamp01(float(token))

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=4))
    def _call_ollama(self, prompt: str) -> float:
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/generate"
        payload = {
            "model": self.cfg.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.cfg.llm_temperature,
                "top_p": self.cfg.llm_top_p,
            },
        }
        r = requests.post(url, json=payload, timeout=self.cfg.llm_timeout_seconds)
        r.raise_for_status()
        txt = r.json().get("response", "0.500")
        return self._extract_float(txt)

    def _call_openai(self, prompt: str) -> float:
        if not self._openai_client:
            raise RuntimeError("OPENAI_API_KEY not set or openai sdk unavailable")
        resp = self._openai_client.responses.create(
            model=self.cfg.llm_model,
            input=prompt,
            temperature=self.cfg.llm_temperature,
            top_p=self.cfg.llm_top_p,
        )
        txt = getattr(resp, "output_text", "0.500")
        return self._extract_float(txt)

    def _call_anthropic(self, prompt: str) -> float:
        if not self._anthropic_client:
            raise RuntimeError("ANTHROPIC_API_KEY not set or anthropic sdk unavailable")
        msg = self._anthropic_client.messages.create(
            model=self.cfg.llm_model,
            max_tokens=16,
            temperature=self.cfg.llm_temperature,
            top_p=self.cfg.llm_top_p,
            system=self.SYSTEM_LINE,
            messages=[{"role": "user", "content": prompt}],
        )
        txt = msg.content[0].text
        return self._extract_float(txt)


class RiskEngine:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg

    def total_open_risk(self, open_positions: Iterable[Position]) -> float:
        return sum(p.stake_usd for p in open_positions)

    def kelly_fraction_yes(self, p_yes: float, price_yes: float) -> float:
        price_yes = clamp(price_yes, 1e-4, 1 - 1e-4)
        b = (1.0 - price_yes) / price_yes
        k = (b * p_yes - (1.0 - p_yes)) / b
        return max(0.0, k)

    def size_bet(
        self,
        p_yes: float,
        price_yes: float,
        side: str,
        open_positions: Iterable[Position],
    ) -> float:
        if side == "YES":
            kelly = self.kelly_fraction_yes(p_yes, price_yes)
        else:
            p_no = 1.0 - p_yes
            price_no = 1.0 - price_yes
            kelly = self.kelly_fraction_yes(p_no, price_no)

        raw = self.cfg.bankroll_usd * self.cfg.kelly_fraction * kelly
        per_position_cap = self.cfg.bankroll_usd * self.cfg.max_position_pct
        total_cap = self.cfg.bankroll_usd * self.cfg.max_total_open_risk_pct
        current_risk = self.total_open_risk(open_positions)
        remaining = max(0.0, total_cap - current_risk)
        return clamp(raw, 0.0, min(per_position_cap, remaining))


class BayesianUpdater:
    @staticmethod
    def update_probability(prior_yes: float, likelihood_ratio: float) -> float:
        prior_yes = clamp(prior_yes, 1e-6, 1 - 1e-6)
        prior_odds = prior_yes / (1.0 - prior_yes)
        post_odds = prior_odds * likelihood_ratio
        return post_odds / (1.0 + post_odds)


class ExecutionEngine:
    def __init__(self, cfg: BotConfig, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger

    def place_order(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        if self.cfg.dry_run:
            self.logger.warning(
                "DRY_RUN=True: no order sent. Keep DRY_RUN on for first 30 days of paper trading."
            )
            return {"status": "dry_run", "signal": signal}

        if not self.cfg.execution_enabled:
            return {"status": "disabled", "signal": signal}

        if Polymarket is None or Web3 is None:
            raise RuntimeError("Install polymarket-py and web3.py for auto execution")

        # Placeholder: wire exact Polymarket client initialization from your account infra.
        # Kept explicit to force safe, deliberate setup.
        raise NotImplementedError(
            "Auto execution wiring intentionally explicit. Configure wallet, signer, and chain RPC first."
        )


class TelegramNotifier:
    def __init__(self, cfg: BotConfig, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def send_signal(self, signal: Dict[str, Any]) -> None:
        if not self.cfg.telegram_enabled:
            return
        if not self.token or not self.chat_id:
            self.logger.warning("Telegram enabled but TELEGRAM_BOT_TOKEN/CHAT_ID missing")
            return
        if Bot is None:
            self.logger.warning("python-telegram-bot not installed")
            return
        text = (
            f"📈 Polymarket Signal\n"
            f"Market: {signal['question']}\n"
            f"Side: {signal['side']}\n"
            f"Edge: {signal['edge']:.3f}\n"
            f"Size: ${signal['stake_usd']:.2f}\n"
            f"Link: {signal['url']}"
        )
        bot = Bot(token=self.token)
        bot.send_message(chat_id=self.chat_id, text=text)


class ScannerBot:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.logger = setup_logging()
        self.data = DataClient(cfg)
        self.prob = ProbabilityEngine(cfg, self.logger)
        self.risk = RiskEngine(cfg)
        self.exec_engine = ExecutionEngine(cfg, self.logger)
        self.notify = TelegramNotifier(cfg, self.logger)
        self.decisions = DecisionLogger(cfg.log_jsonl_path, cfg.db_path)
        self.open_positions: List[Position] = []

    def scan_once(self) -> List[Dict[str, Any]]:
        n = clamp_int(self.cfg.max_markets, self.cfg.min_markets, self.cfg.max_markets)
        markets = self.data.fetch_active_markets(limit=n)
        self.logger.info("Fetched %s markets", len(markets))

        signals: List[Dict[str, Any]] = []
        for m in markets:
            try:
                p_yes = self.prob.predict_yes_probability(m)
                edge = p_yes - m["yes_price"]
                side = "YES" if edge > 0 else "NO"
                abs_edge = abs(edge)

                action = "SKIP"
                stake = 0.0
                if abs_edge >= self.cfg.edge_threshold:
                    stake = self.risk.size_bet(p_yes, m["yes_price"], side, self.open_positions)
                    if stake > 0:
                        action = "SIGNAL"

                row = {
                    "condition_id": m["condition_id"],
                    "question": m["question"],
                    "market_price": m["yes_price"],
                    "prob_yes": p_yes,
                    "edge": edge,
                    "side": side,
                    "stake_usd": stake,
                    "action": action,
                    "url": m["url"],
                    "metadata": {"volume": m.get("volume"), "liquidity": m.get("liquidity")},
                }
                self.decisions.log_decision(row)

                if action == "SIGNAL":
                    signals.append(row)
            except Exception as e:
                self.logger.exception("Failed market %s: %s", m.get("condition_id"), e)

        signals = sorted(signals, key=lambda x: abs(x["edge"]), reverse=True)[: self.cfg.max_signals_per_day]
        self._print_signal_table(signals)

        for s in signals:
            self.notify.send_signal(s)
            if self.cfg.execution_enabled:
                self.exec_engine.place_order(s)

            self.open_positions.append(
                Position(
                    condition_id=s["condition_id"],
                    side=s["side"],
                    market_question=s["question"],
                    entry_price=s["market_price"],
                    stake_usd=s["stake_usd"],
                    subjective_prob_yes=s["prob_yes"],
                    edge=s["edge"],
                    timestamp_utc=utc_now(),
                )
            )

        return signals

    def _print_signal_table(self, signals: List[Dict[str, Any]]) -> None:
        if not signals:
            print("No high-edge signals. Ruthlessly skipped all markets this cycle.")
            return
        df = pd.DataFrame(
            [
                {
                    "Side": s["side"],
                    "Edge": round(s["edge"], 4),
                    "P_yes": round(s["prob_yes"], 4),
                    "Mkt": round(s["market_price"], 4),
                    "Stake$": round(s["stake_usd"], 2),
                    "Question": s["question"][:95],
                }
                for s in signals
            ]
        )
        print(df.to_string(index=False))


class UpdatePayload(BaseModel):
    condition_id: str
    news: str
    likelihood_ratio: float
    prior_yes: float


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def clamp01(v: float) -> float:
    return clamp(v, 0.0, 1.0)


def clamp_int(v: int, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, v)))


def make_app(bot: ScannerBot):
    if FastAPI is None:
        raise RuntimeError("FastAPI/uvicorn not installed")

    app = FastAPI(title="Polymarket Scanner Webhook")

    @app.get("/health")
    def health():
        return {"ok": True, "ts": utc_now()}

    @app.post("/signal")
    def post_signal(payload: UpdatePayload):
        posterior = BayesianUpdater.update_probability(payload.prior_yes, payload.likelihood_ratio)
        result = {
            "condition_id": payload.condition_id,
            "prior_yes": payload.prior_yes,
            "likelihood_ratio": payload.likelihood_ratio,
            "posterior_yes": posterior,
            "news": payload.news,
        }
        return result

    return app


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Polymarket edge scanner bot")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    p.add_argument("--scan", action="store_true", help="Run one scan cycle")
    p.add_argument("--loop", action="store_true", help="Run scanner in loop by scan_interval_minutes")
    p.add_argument("--telegram", action="store_true", help="Enable telegram for this run")

    p.add_argument("--update-market", dest="condition_id", help="Condition id to update via Bayes")
    p.add_argument("--news", default="", help="News text")
    p.add_argument("--lr", type=float, help="Likelihood ratio for Bayes update")
    p.add_argument("--prior", type=float, help="Prior probability for Bayes update")

    p.add_argument("--serve-webhook", action="store_true", help="Run FastAPI webhook")

    p.add_argument("--resolve-market", action="store_true", help="Log resolved market P&L")
    p.add_argument("--side", choices=["YES", "NO"], help="Entry side for resolve")
    p.add_argument("--entry-price", type=float, help="Entry price for resolve")
    p.add_argument("--stake", type=float, help="Stake USD for resolve")
    p.add_argument("--outcome-yes", choices=["true", "false"], help="Resolved YES/NO")

    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    if args.telegram:
        cfg.telegram_enabled = True

    bot = ScannerBot(cfg)

    if args.condition_id and args.news and args.lr:
        prior = args.prior
        if prior is None:
            m = bot.data.fetch_market_by_condition_id(args.condition_id)
            if not m:
                raise ValueError("Could not infer --prior from market data. Pass --prior explicitly.")
            prior = float(m["yes_price"])
        posterior = BayesianUpdater.update_probability(prior, args.lr)
        print(
            json.dumps(
                {
                    "condition_id": args.condition_id,
                    "prior_yes": prior,
                    "likelihood_ratio": args.lr,
                    "posterior_yes": posterior,
                    "news": args.news,
                    "ts_utc": utc_now(),
                },
                indent=2,
            )
        )
        return 0

    if args.resolve_market:
        if not all([args.condition_id, args.side, args.entry_price, args.stake, args.outcome_yes]):
            raise ValueError("--resolve-market requires --update-market --side --entry-price --stake --outcome-yes")
        result = bot.decisions.log_resolved_position(
            condition_id=args.condition_id,
            side=args.side,
            entry_price=args.entry_price,
            stake_usd=args.stake,
            outcome_yes=(args.outcome_yes == "true"),
            metadata={"source": "cli"},
        )
        print(json.dumps(result, indent=2))
        return 0

    if args.serve_webhook:
        if uvicorn is None:
            raise RuntimeError("uvicorn not installed")
        app = make_app(bot)
        uvicorn.run(app, host=cfg.webhook_host, port=cfg.webhook_port)
        return 0

    if args.scan or (args.telegram and not args.loop and not args.serve_webhook):
        bot.scan_once()
        return 0

    if args.loop:
        while True:
            bot.scan_once()
            time.sleep(max(60, int(cfg.scan_interval_minutes * 60)))

    print("No action specified. Use --scan or --loop or --serve-webhook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
