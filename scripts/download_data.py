"""Скачать фиксированную версию публичной выборки и проверить SHA-256."""
from pathlib import Path
import hashlib
import sys
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from travel.data import SOURCE_URL, SOURCE_SHA256


def main():
    path=ROOT/'data/raw/dataset_travel.csv'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=SOURCE_SHA256:
            raise ValueError('Существующий CSV отличается от эталона; файл не перезаписан')
        print('Данные уже скачаны, SHA-256 совпадает.')
        return
    temp=path.with_suffix('.download')
    try:
        with urllib.request.urlopen(SOURCE_URL,timeout=120) as response, temp.open('wb') as target:
            while chunk:=response.read(1024*1024):
                target.write(chunk)
        if hashlib.sha256(temp.read_bytes()).hexdigest()!=SOURCE_SHA256:
            raise ValueError('SHA-256 не совпадает: загрузка отклонена')
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    print(f'Скачано {path.stat().st_size:,} байт. SHA-256 совпадает.')


if __name__=='__main__':
    main()
