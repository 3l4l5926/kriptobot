import pandas as pd
import pandas_ta as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from datetime import datetime

class QuantumMomentumStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '15m'
    can_short: bool = True  # Vadeli Short desteği aktif

    # Alış & Satış Parametreleri
    buy_rsi = IntParameter(40, 70, default=55, space='buy')
    short_rsi = IntParameter(30, 60, default=45, space='buy')
    trend_adx = IntParameter(20, 45, default=25, space='buy')

    # OCO Zarar Kes / Kâr Al Çarpanları
    sl_multiplier = DecimalParameter(1.0, 4.0, default=2.0, space='sell')
    tp_multiplier = DecimalParameter(2.0, 7.0, default=4.0, space='sell')

    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    use_custom_stoploss = False

    startup_candle_count: int = 100

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe['ema_50'] = ta.ema(dataframe['close'], length=50)
        dataframe['ema_100'] = ta.ema(dataframe['close'], length=100)
        
        macd = ta.macd(dataframe['close'])
        dataframe['macd'] = macd['MACD_12_26_9']
        dataframe['macdsignal'] = macd['MACDs_12_26_9']

        dataframe['rsi'] = ta.rsi(dataframe['close'], length=14)
        adx = ta.adx(dataframe['high'], dataframe['low'], dataframe['close'])
        dataframe['adx'] = adx['ADX_14']
        dataframe['atr'] = ta.atr(dataframe['high'], dataframe['low'], dataframe['close'], length=14)

        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        # LONG SİNYALİ
        dataframe.loc[
            (
                (dataframe['ema_50'] > dataframe['ema_100']) &
                (dataframe['macd'] > dataframe['macdsignal']) &
                (dataframe['rsi'] < self.buy_rsi.value) &
                (dataframe['adx'] > self.trend_adx.value)
            ),
            ['enter_long', 'enter_tag']] = (1, 'Long_Sinyali')

        # SHORT SİNYALİ (Düşüşte Kâr)
        dataframe.loc[
            (
                (dataframe['ema_50'] < dataframe['ema_100']) &
                (dataframe['macd'] < dataframe['macdsignal']) &
                (dataframe['rsi'] > self.short_rsi.value) &
                (dataframe['adx'] > self.trend_adx.value)
            ),
            ['enter_short', 'enter_tag']] = (1, 'Short_Sinyali')

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0
        return dataframe

    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        giris_mumu = dataframe.loc[dataframe['date'] == trade.open_date_utc]
        
        if not giris_mumu.empty:
            mevcut_atr = giris_mumu['atr'].iloc[0]
            giris_fiyati = trade.open_rate
            
            if trade.is_short:
                # SHORT İŞLEMİ: Fiyat düştükçe kâr, yükseldikçe zarar
                zarar_kes_fiyati = giris_fiyati + (mevcut_atr * self.sl_multiplier.value)
                kar_al_fiyati = giris_fiyati - (mevcut_atr * self.tp_multiplier.value)
                
                if current_rate >= zarar_kes_fiyati:
                    return "Short_SL"
                if current_rate <= kar_al_fiyati:
                    return "Short_TP"
            else:
                # LONG İŞLEMİ: Fiyat yükseldikçe kâr, düştükçe zarar
                zarar_kes_fiyati = giris_fiyati - (mevcut_atr * self.sl_multiplier.value)
                kar_al_fiyati = giris_fiyati + (mevcut_atr * self.tp_multiplier.value)
                
                if current_rate <= zarar_kes_fiyati:
                    return "Long_SL"
                if current_rate >= kar_al_fiyati:
                    return "Long_TP"
                    
        return None