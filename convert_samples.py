from glob import glob
from os import path

import soundfile as sf
import torch


def fname(fp):
    return path.splitext(fp)[0]


def main():
    sdir = './samples'
    sr = 16000

    pts = set(map(fname, glob(f'{sdir}/*pt')))
    # wavs = set(map(fname, glob(f'{sdir}/*wav')))

    for name in pts:
        d = torch.load(f'{name}.pt')
        raw = d['generation']
        sf.write(f'{name}.wav', raw, sr, subtype='PCM_24')
        print(f'Converted {name}')


if __name__ == '__main__':
    main()
