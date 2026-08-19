import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import pandas_ta as ta

from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    DecimalParameter,
)
from freqtrade.enums import RunMode


class QuantumMomentumStrategy(IStrategy):

    INTERFACE_VERSION = 3

    timeframe = "15m"

    can_short = True

    startup_candle_count = 100

    # ---------------------------------------------------------
    # Hyperopt parametreleri
    # ---------------------------------------------------------

    buy_rsi = IntParameter(
        35,
        55,
        default=45,
        space="buy"
    )

    short_rsi = IntParameter(
        45,
        65,
        default=55,
        space="buy"
    )

    trend_adx = IntParameter(
        20,
        40,
        default=30,
        space="buy"
    )

    sl_multiplier = DecimalParameter(
        1.2,
        4.0,
        decimals=3,
        default=2.2,
        space="sell"
    )

    tp_multiplier = DecimalParameter(
        2.5,
        8.0,
        decimals=3,
        default=5.0,
        space="sell"
    )

    # ---------------------------------------------------------
    # ROI / acil stop
    # ---------------------------------------------------------

    minimal_roi = {
        "0": 100.0
    }

    stoploss = -0.99

    use_custom_stoploss = False

    # ---------------------------------------------------------
    # Dosyalar
    # ---------------------------------------------------------

    PARAM_FILE = Path(
        "data/pair_params.json"
    )

    DEFAULT_PARAMS = {
        "buy_rsi": 45,
        "short_rsi": 55,
        "trend_adx": 30,
        "sl_multiplier": 2.2,
        "tp_multiplier": 5.0,
    }

    _params_cache = None

    # =========================================================
    # PARAMETRE DOSYASINI OKU
    # =========================================================

    @classmethod
    def load_pair_params(cls):

        if cls._params_cache is not None:
            return cls._params_cache

        if not cls.PARAM_FILE.exists():
            cls._params_cache = {}
            return cls._params_cache

        try:

            with open(
                cls.PARAM_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                cls._params_cache = json.load(f)

        except Exception:

            cls._params_cache = {}

        return cls._params_cache

    # =========================================================
    # COIN PARAMETRELERİ
    # =========================================================

    def get_pair_params(self, pair):

        # Hyperopt sırasında gerçek pair parametresini
        # kullanma.
        #
        # Hyperopt kendi parametrelerini optimize etmeli.

        try:
            if self.config["runmode"].value == RunMode.HYPEROPT:

                return {
                    "buy_rsi": self.buy_rsi.value,
                    "short_rsi": self.short_rsi.value,
                    "trend_adx": self.trend_adx.value,
                    "sl_multiplier": float(
                        self.sl_multiplier.value
                    ),
                    "tp_multiplier": float(
                        self.tp_multiplier.value
                    ),
                }

        except Exception:
            pass

        # -----------------------------------------------------
        # Normal / dry-run / live
        # -----------------------------------------------------

        params = self.load_pair_params()

        if pair in params:

            result = self.DEFAULT_PARAMS.copy()

            result.update(params[pair])

            return result

        # :USDT kısmını kaldırarak tekrar dene

        clean_pair = pair.replace(":USDT", "")

        if clean_pair in params:

            result = self.DEFAULT_PARAMS.copy()

            result.update(params[clean_pair])

            return result

        return self.DEFAULT_PARAMS.copy()

    # =========================================================
    # INDICATORS
    # =========================================================

    def populate_indicators(
        self,
        dataframe: pd.DataFrame,
        metadata: dict
    ) -> pd.DataFrame:

        dataframe["ema_50"] = ta.ema(
            dataframe["close"],
            length=50
        )

        dataframe["ema_100"] = ta.ema(
            dataframe["close"],
            length=100
        )

        macd = ta.macd(
            dataframe["close"]
        )

        dataframe["macd"] = macd[
            "MACD_12_26_9"
        ]

        dataframe["macdsignal"] = macd[
            "MACDs_12_26_9"
        ]

        dataframe["rsi"] = ta.rsi(
            dataframe["close"],
            length=14
        )

        adx = ta.adx(
            dataframe["high"],
            dataframe["low"],
            dataframe["close"]
        )

        dataframe["adx"] = adx[
            "ADX_14"
        ]

        dataframe["atr"] = ta.atr(
            dataframe["high"],
            dataframe["low"],
            dataframe["close"],
            length=14
        )

        return dataframe

    # =========================================================
    # ENTRY
    # =========================================================

    def populate_entry_trend(
        self,
        dataframe: pd.DataFrame,
        metadata: dict
    ) -> pd.DataFrame:

        pair = metadata["pair"]

        params = self.get_pair_params(pair)

        buy_rsi = float(
            params["buy_rsi"]
        )

        short_rsi = float(
            params["short_rsi"]
        )

        trend_adx = float(
            params["trend_adx"]
        )

        # -----------------------------------------------------
        # LONG
        # -----------------------------------------------------

        long_condition = (
            (dataframe["ema_50"] > dataframe["ema_100"])
            &
            (dataframe["macd"] > dataframe["macdsignal"])
            &
            (dataframe["rsi"] < buy_rsi)
            &
            (dataframe["adx"] > trend_adx)
        )

        dataframe.loc[
            long_condition,
            "enter_long"
        ] = 1

        dataframe.loc[
            long_condition,
            "enter_tag"
        ] = "Long_Quantum"

        # -----------------------------------------------------
        # SHORT
        # -----------------------------------------------------

        short_condition = (
            (dataframe["ema_50"] < dataframe["ema_100"])
            &
            (dataframe["macd"] < dataframe["macdsignal"])
            &
            (dataframe["rsi"] > short_rsi)
            &
            (dataframe["adx"] > trend_adx)
        )

        dataframe.loc[
            short_condition,
            "enter_short"
        ] = 1

        dataframe.loc[
            short_condition,
            "enter_tag"
        ] = "Short_Quantum"

        return dataframe

    # =========================================================
    # EXIT SIGNAL
    # =========================================================

    def populate_exit_trend(
        self,
        dataframe: pd.DataFrame,
        metadata: dict
    ) -> pd.DataFrame:

        dataframe["exit_long"] = 0

        dataframe["exit_short"] = 0

        return dataframe

    # =========================================================
    # ATR EXIT
    # =========================================================

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ):

        params = self.get_pair_params(pair)

        sl_multiplier = float(
            params["sl_multiplier"]
        )

        tp_multiplier = float(
            params["tp_multiplier"]
        )

        dataframe, _ = self.dp.get_analyzed_dataframe(
            pair,
            self.timeframe
        )

        if dataframe is None:
            return None

        if dataframe.empty:
            return None

        entry_candles = dataframe[
            dataframe["date"] <= trade.open_date_utc
        ]

        if entry_candles.empty:
            return None

        entry_candle = entry_candles.iloc[-1]

        entry_atr = entry_candle["atr"]

        if pd.isna(entry_atr):
            return None

        if entry_atr <= 0:
            return None

        entry_price = trade.open_rate

        # -----------------------------------------------------
        # SHORT
        # -----------------------------------------------------

        if trade.is_short:

            stop_price = (
                entry_price
                +
                entry_atr * sl_multiplier
            )

            target_price = (
                entry_price
                -
                entry_atr * tp_multiplier
            )

            if current_rate >= stop_price:

                return "Short_ATR_SL"

            if current_rate <= target_price:

                return "Short_ATR_TP"

        # -----------------------------------------------------
        # LONG
        # -----------------------------------------------------

        else:

            stop_price = (
                entry_price
                -
                entry_atr * sl_multiplier
            )

            target_price = (
                entry_price
                +
                entry_atr * tp_multiplier
            )

            if current_rate <= stop_price:

                return "Long_ATR_SL"

            if current_rate >= target_price:

                return "Long_ATR_TP"

        return None
