# core/data_handler.py

import pandas as pd
import os

class DataHandler:
    def __init__(self, csv_filepath):
        self.df = self._load_data(csv_filepath)
        if self.df is None or self.df.empty:
            raise ValueError("Data could not be loaded. Aborting.")
        self.current_index = 0

    def _load_data(self, csv_filepath):
        if not os.path.exists(csv_filepath):
            print(f"❌ ERROR: Historical data file not found at: {csv_filepath}")
            return None
        try:
            try:
                df = pd.read_csv(csv_filepath, parse_dates=['datetime'], index_col='datetime')
                print(f"✅ Data loaded successfully from standard CSV. {len(df)} bars.")
                return df
            except (ValueError, KeyError):
                print("Standard CSV failed, trying MT5 tab-separated format...")
                df = pd.read_csv(
                    csv_filepath, sep='\t', header=None,
                    names=['date', 'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
                )
                df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M:%S')
                df.set_index('datetime', inplace=True)
                df.drop(['date', 'time', 'spread', 'real_volume'], axis=1, inplace=True)
                print(f"✅ Data loaded successfully from MT5 format. {len(df)} bars.")
                return df
        except Exception as e:
            print(f"❌ ERROR: Failed to load or parse data file. Error: {e}")
            return None

    def stream_bars(self):
        for i in range(len(self.df)):
            self.current_index = i
            yield self.df.iloc[i]

    def get_historical_data(self, n_bars):
        if self.current_index < n_bars:
            return pd.DataFrame()
        start_index = self.current_index - n_bars + 1
        return self.df.iloc[start_index : self.current_index + 1].copy()

    def get_last_bar(self):
        return self.df.iloc[-1]
