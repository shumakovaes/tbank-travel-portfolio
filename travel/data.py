from pathlib import Path
import hashlib
import pandas as pd

SOURCE_COMMIT = 'd69b9db256cee03e6983d8b78e5b82d50b127401'
SOURCE_URL = f'https://raw.githubusercontent.com/Kor4yz/T-bank_analysis_hotels_and_air_travel/{SOURCE_COMMIT}/data/dataset_travel.csv'
SOURCE_SHA256 = 'a8739c64927a7fc4a0398adac55ba8c033ffe7cd67ff42cbf7533bdf8a50c211'
REQUIRED = ['client_rk', 'order_rk', 'order_type_cd', 'order_status_cd',
            'created_dttm', 'book_start_dttm', 'nominal_price_rub_amt']
OPTIONAL = ['book_end_dttm', 'promo_code_discount_amt', 'hotel_city', 'avia_arr_city']


def numeric(series):
    return pd.to_numeric(series.astype('string').str.replace(r'[\s\u00a0]', '', regex=True)
                         .str.replace(',', '.', regex=False), errors='coerce')


def prepare(raw):
    """Заказы определяются по типу AIR/HOT. Клиентские строки учитываются отдельно.

    Повторяющиеся ID заказов отклоняются: без истории изменений нельзя выбрать
    достоверную версию. Неизвестные статусы и пропуски не превращаются в отказы.
    """
    missing = set(REQUIRED) - set(raw.columns)
    if missing:
        raise ValueError(f'Отсутствуют обязательные столбцы: {sorted(missing)}')
    raw = raw.copy()
    for c in OPTIONAL:
        if c not in raw:
            raw[c] = pd.NA
    order_mask = raw.order_type_cd.isin(['AIR', 'HOT'])
    quality = {'source_rows': len(raw), 'source_clients': int(raw.client_rk.nunique()),
               'non_order_rows': int((~order_mask).sum()),
               'non_order_clients': int(raw.loc[~order_mask, 'client_rk'].nunique()),
               'unknown_type_rows': int((raw.order_type_cd.notna() & ~order_mask).sum())}
    orders = raw.loc[order_mask, REQUIRED + OPTIONAL].copy()
    if orders.empty:
        raise ValueError('Нет заказов AIR/HOT')
    if orders[['order_rk', 'client_rk']].isna().any().any():
        raise ValueError('У заказа отсутствует ID заказа или клиента')
    if orders.order_rk.duplicated().any():
        raise ValueError('Повторяющиеся order_rk: необходимо проверить гранулярность')
    for c in ['created_dttm', 'book_start_dttm', 'book_end_dttm']:
        orders[c] = pd.to_datetime(orders[c], format='mixed', errors='coerce')
    if orders.created_dttm.isna().any():
        raise ValueError('Заказы с отсутствующей или некорректной датой создания')
    for c in ['nominal_price_rub_amt', 'promo_code_discount_amt']:
        orders[c] = numeric(orders[c])
    orders['is_success'] = orders.order_status_cd.eq('SUC').fillna(False)
    orders['status_known'] = orders.order_status_cd.notna()
    orders['valid_amount'] = orders.nominal_price_rub_amt.notna() & orders.nominal_price_rub_amt.ge(0)
    orders['month'] = orders.created_dttm.dt.to_period('M')
    orders['lead_days'] = (orders.book_start_dttm.dt.normalize() - orders.created_dttm.dt.normalize()).dt.days
    orders['stay_nights'] = (orders.book_end_dttm.dt.normalize() - orders.book_start_dttm.dt.normalize()).dt.days
    orders.loc[orders.order_type_cd.ne('HOT'), 'stay_nights'] = float('nan')
    quality.update({'orders': len(orders), 'order_clients': int(orders.client_rk.nunique()),
                    'missing_status_orders': int((~orders.status_known).sum()),
                    'invalid_amount_orders': int((~orders.valid_amount).sum()),
                    'missing_lead_orders': int(orders.lead_days.isna().sum()),
                    'negative_lead_orders': int(orders.lead_days.lt(0).sum()),
                    'period_start': orders.created_dttm.min().isoformat(),
                    'period_end': orders.created_dttm.max().isoformat()})
    return orders.reset_index(drop=True), quality


def load_orders(path):
    path = Path(path)
    raw = pd.read_csv(path, sep=';', dtype='string', low_memory=False)
    orders, quality = prepare(raw)
    quality['source_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    quality['matches_reference'] = quality['source_sha256'] == SOURCE_SHA256
    return orders, quality
