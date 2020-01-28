import math
import random
from glob import glob
from typing import Tuple

import numpy as np
import torch
from torch.utils import data

from ..data import Dataset
from ..functional import encode_μ_law


def _prepare_toy_audio_data(mix: np.ndarray, sources: np.ndarray,
                            μ: int, crop: int, offset: int = 0):
    mix = torch.tensor(mix, dtype=torch.float32)
    mix = encode_μ_law(mix, μ=μ - 1) / math.ceil(μ / 2)

    sources = torch.tensor(sources, dtype=torch.float32)
    # TODO is this + correct why not / ???????
    sources = (encode_μ_law(sources, μ=μ - 1) + math.ceil(
        μ / 2)).long()

    mix = mix[offset:offset + crop]
    sources = sources[:, offset:offset + crop]
    return mix.unsqueeze(0), sources


class ToyData(Dataset):
    """
    A Dataset that loads that loads the toy data. Mix + all sources
    cropped.
    """

    def __init__(self, filepath: str, μ: int, crop: int):
        self.data = np.load(filepath, allow_pickle=True)
        self.μ, self.crop = μ, crop

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        item = self.data[idx]
        p = random.randint(0, item['mix'].numel() - self.crop)
        mix, sources = _prepare_toy_audio_data(item['mix'], item['sources'],
                                               self.μ, self.crop, p)
        return mix, sources


class ToyDataSingle(ToyData):
    def __init__(self, *args, **kwargs):
        super(ToyDataSingle, self).__init__(*args, **kwargs)

    def __getitem__(self, item: int) \
            -> Tuple[Tuple[torch.Tensor, int], torch.Tensor]:
        mix, sources = super(ToyDataSingle, self).__getitem__(item)
        t = random.randint(0, sources.shape[0] - 1)
        source = sources[None, t, :]
        return (mix, t), source


class ToyDataSequential(Dataset):
    def __init__(self, filepath: str, μ: int, crop: int,
                 batch_size: int, steps: int = 5, stride: int = None):
        self.μ, self.crop, self.steps = μ, crop, steps
        self.ifile, self.data = None, None
        self.batch_size = batch_size
        self.files = sorted(glob(filepath))
        self.load_file(0)
        if not stride:
            self.stride = crop // 2

    def load_file(self, i):
        self.ifile = i
        self.data = np.load(self.files[i], allow_pickle=True)

    def __len__(self) -> int:
        # the minus 1 stays unexplained
        return len(self.files) * len(self.data) * self.steps \
               - (self.steps * self.batch_size)

    def __getitem__(self, idx: int) \
            -> Tuple[Tuple[torch.Tensor, int], torch.Tensor]:
        i_batch = idx // (self.batch_size * self.steps)
        i_in_batch = idx % self.batch_size
        i_sample = i_batch * self.batch_size + i_in_batch

        # Index of file where sample is
        i_file = i_sample // len(self.data)
        # Index of sample inside this file
        i_sample_in_file = i_sample % len(self.data)

        # If we are currently in the wrong file, load the next one
        if i_file != self.ifile:
            self.load_file(i_file)
        item = self.data[i_sample_in_file]

        offset = idx // self.batch_size % self.steps
        offset *= self.stride

        mix, sources = _prepare_toy_audio_data(item['mix'], item['sources'],
                                               self.μ, self.crop, offset)
        return (mix, offset), sources

    def loader(self, batch_size: int) -> data.DataLoader:
        return data.DataLoader(self, batch_size=batch_size, num_workers=0,
                               shuffle=False, drop_last=True)