# File: core/data_handler.py

import pandas as pd
import os

class DataHandler:
    """
    مسئولیت خواندن، تمیز کردن و ارائه داده‌های تاریخی قیمت را بر عهده دارد.
    """
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.data = self._load_data()
        self.total_bars = len(self.data)

        if self.total_bars > 0:
            print(f"✅ DataHandler Initialized. Loaded {self.total_bars} bars.")
        else:
            raise ValueError("Data could not be loaded or the file is empty.")

    def _load_data(self) -> pd.DataFrame:
        """داده‌ها را از فایل خوانده و فرمت‌بندی می‌کند."""
        if not os.path.exists(self.data_path):
            print(f"❌ ERROR: Historical data file not found at: {self.data_path}")
            return pd.DataFrame()

        try:
            df = pd.read_csv(
                self.data_path,
                sep='\t',
                header=None,
                names=['date', 'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            )
            df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M:%S')
            df.set_index('datetime', inplace=True)
            df.drop(['date', 'time', 'spread', 'real_volume'], axis=1, inplace=True)
            return df
        except Exception as e:
            print(f"❌ ERROR: Failed to load or parse data file. Error: {e}")
            return pd.DataFrame()

    def get_bar(self, index: int):
        """یک کندل خاص را بر اساس ایندکس آن برمی‌گرداند."""
        if 0 <= index < self.total_bars:
            return self.data.iloc[index]
        return None

    def get_historical_data(self, current_index: int, n_bars: int) -> pd.DataFrame:
        """آخرین n کندل را تا نقطه فعلی بک‌تست برمی‌گرداند."""
        if current_index < n_bars:
            return self.data.iloc[:current_index + 1].copy()
        
        start_index = current_index - n_bars + 1
        return self.data.iloc[start_index : current_index + 1].copy()
