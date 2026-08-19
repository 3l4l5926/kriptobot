import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import pandas_ta as ta

from freqtrade.strategy import IStrategy


class QuantumMomentumStrategy(IStrategy):

    INTERFACE_VERSION = 3

    timeframe = "15m"

    can_short = True

    startup_candle_count = 100

    # ============================================================
    # GENEL GÜVENLİK AYARLARI
    # ============================================================

    # ROI'yi bilinçli olarak devre dışı bırakıyoruz.
    # Çıkışları ATR tabanlı custom_exit yönetecek.
    minimal_roi = {
        "0": 100.0
    }

    # Acil durum stoploss.
    # Asıl SL daha sonra ATR sistemi tarafından hesaplanacak.
    stoploss = -0.99

    use_custom_stoploss = False

    # ============================================================
    # PARAMETRE DOSYASI
    # ============================================================

    PARAM_FILE = Path(
        os.environ.get(
            "QUANTUM_PARAMS_FILE",
            "user_data/configs/pair_params.json"
        )
    )

    DEFAULT_PARAMS = {
        "buy_rsi": 41,
        "short_rsi": 56,
        "trend_adx": 32,
        "sl_multiplier": 2.228,
        "tp_multiplier": 6.036
    }

    _pair_params_cache = None

    # ============================================================
    # PARAMETRELERİ YÜKLE
    # ============================================================

    @classmethod
    def load_pair_params(cls):

        if cls._pair_params_cache is not None:
            return cls._pair_params_cache

        try:

            if cls.PARAM_FILE.exists():

                with open(cls.PARAM_FILE, "r", encoding="utf-8") as f:
                    cls._pair_params_cache = json.load(f)

            else:

                cls._pair_params_cache = {}

        except Exception as e:

            print(
                f"[QuantumMomentumStrategy] "
                f"Parametre dosyası okunamadı: {e}"
            )

            cls._pair_params_cache = {}

        return cls._pair_params_cache

    # ============================================================
    # COIN'E ÖZEL PARAMETRE
    # ============================================================

    def get_params(self, pair):

        all_params = self.load_pair_params()

        # --------------------------------------------------------
        # Önce tam pair ismini ara
        # Örn:
        # ETH/USDT:USDT
        # --------------------------------------------------------

        if pair in all_params:

            params = all_params[pair]

            return {
                **self.DEFAULT_PARAMS,
                **params
            }

        # --------------------------------------------------------
        # :USDT kısmı olmadan da kontrol et
        # --------------------------------------------------------

        clean_pair = pair.replace(":USDT", "")

        if clean_pair in all_params:

            params = all_params[clean_pair]

            return {
                **self.DEFAULT_PARAMS,
                **params
            }

        # --------------------------------------------------------
        # Coin için özel parametre yoksa default kullan
        # --------------------------------------------------------

        return self.DEFAULT_PARAMS.copy()

    # ============================================================
    # GÖSTERGELER
    # ============================================================

    def populate_indicators(
        self,
        dataframe: pd.DataFrame,
        metadata: dict
    ) -> pd.DataFrame:

        # EMA
        dataframe["ema_50"] = ta.ema(
            dataframe["close"],
            length=50
        )

        dataframe["ema_100"] = ta.ema(
            dataframe["close"],
            length=100
        )

        # MACD
        macd = ta.macd(
            dataframe["close"]
        )

        dataframe["macd"] = macd["MACD_12_26_9"]

        dataframe["macdsignal"] = macd[
            "MACDs_12_26_9"
        ]

        # RSI
        dataframe["rsi"] = ta.rsi(
            dataframe["close"],
            length=14
        )

        # ADX
        adx = ta.adx(
            dataframe["high"],
            dataframe["low"],
            dataframe["close"]
        )

        dataframe["adx"] = adx["ADX_14"]

        # ATR
        dataframe["atr"] = ta.atr(
            dataframe["high"],
            dataframe["low"],
            dataframe["close"],
            length=14
        )

        return dataframe

    # ============================================================
    # LONG / SHORT GİRİŞLERİ
    # ============================================================

    def populate_entry_trend(
        self,
        dataframe: pd.DataFrame,
        metadata: dict
    ) -> pd.DataFrame:

        pair = metadata["pair"]

        params = self.get_params(pair)

        buy_rsi = params["buy_rsi"]

        short_rsi = params["short_rsi"]

        trend_adx = params["trend_adx"]

        # --------------------------------------------------------
        # LONG
        # --------------------------------------------------------

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
            ["enter_long", "enter_tag"]
        ] = (
            1,
            "Long_Sinyali"
        )

        # --------------------------------------------------------
        # SHORT
        # --------------------------------------------------------

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
            ["enter_short", "enter_tag"]
        ] = (
            1,
            "Short_Sinyali"
        )

        return dataframe

    # ============================================================
    # NORMAL EXIT SİNYALİ
    # ============================================================

    def populate_exit_trend(
        self,
        dataframe: pd.DataFrame,
        metadata: dict
    ) -> pd.DataFrame:

        dataframe["exit_long"] = 0

        dataframe["exit_short"] = 0

        return dataframe

    # ============================================================
    # ATR TABANLI TP / SL
    # ============================================================

    def custom_exit(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ):

        params = self.get_params(pair)

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

        if dataframe is None or dataframe.empty:
            return None

        # --------------------------------------------------------
        # İşleme giriş yapılan zamana en yakın mumu bul
        # --------------------------------------------------------

        entry_candles = dataframe[
            dataframe["date"] <= trade.open_date_utc
        ]

        if entry_candles.empty:
            return None

        entry_candle = entry_candles.iloc[-1]

        entry_atr = entry_candle["atr"]

        if pd.isna(entry_atr) or entry_atr <= 0:
            return None

        entry_price = trade.open_rate

        # ========================================================
        # SHORT
        # ========================================================

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

        # ========================================================
        # LONG
        # ========================================================

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
