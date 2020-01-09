from typing import Tuple

import torch
from torch import nn
from torch.nn import functional as F

from .decoder import WaveNetDecoder
from .encoder import TemporalEncoder
from .functional import shift1d
from .modules import AutoEncoder


class WavenetAE(AutoEncoder):
    """
    The complete WaveNetAutoEncoder model.
    """

    def __init__(self, bottleneck_dims: int, encoder_width: int,
                 decoder_width: int, n_layers: int = 10, n_blocks: int = 3,
                 quantization_channels: int = 256,
                 channels: int = 1, gen: bool = False):
        """
        :param bottleneck_dims: Number of dims in the latent bottleneck.
        :param encoder_width: Width of the hidden layers in the encoder (Non-
            causal Temporal encoder).
        :param decoder_width: Width of the hidden layers in the decoder
            (WaveNet).
        :param n_layers: number of layers in each block of encoder and decoder
        :param n_blocks: number of blocks for both
        :param quantization_channels:
        :param channels: Number of input channels.
        :param gen: Is this generation ?
        """
        super(WavenetAE, self).__init__()
        self.encoder = TemporalEncoder(in_channels=channels,
                                       out_channels=bottleneck_dims,
                                       n_blocks=n_blocks, n_layers=n_layers,
                                       width=encoder_width)
        self.decoder = WaveNetDecoder(bottleneck_dims=bottleneck_dims,
                                      channels=channels, width=decoder_width,
                                      n_layers=n_layers, n_blocks=n_blocks,
                                      quantization_channels=quantization_channels,
                                      gen=gen)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        embedding = self.encoder(x)
        x = shift1d(x, -1)
        logits = self.decoder(x, embedding)
        return logits

    @staticmethod
    def loss_function(model: nn.Module, x: torch.Tensor, y: torch.Tensor,
                      device: str, progress: float)\
            -> Tuple[torch.Tensor, torch.Tensor]:
        del progress
        logits = model(x)
        loss = F.cross_entropy(logits, y.to(device))
        return loss, logits
