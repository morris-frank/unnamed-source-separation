from typing import Tuple

import torch
from torch import distributions as dist
from torch import nn
from torch.nn import functional as F

from .decoder import WavenetDecoder
from .encoder import TemporalEncoder
from .functional import shift1d
from .utils import clean_init_args
from .modules import AutoEncoder


class WavenetVAE(AutoEncoder):
    """
    The complete WaveNetAutoEncoder model.
    """

    def __init__(self, in_channels: int, out_channels: int, latent_width: int,
                 encoder_width: int, decoder_width: int, n_blocks: int = 3,
                 n_layers: int = 10):
        """
        :param in_channels: Number of input in_channels.
        :param out_channels:
        :param latent_width: Number of dims in the latent bottleneck.
        :param encoder_width: Width of the hidden layers in the encoder (Non-
            causal Temporal encoder).
        :param decoder_width: Width of the hidden layers in the decoder
            (WaveNet).
        :param n_blocks: number of blocks in encoder and decoder
        :param n_layers: number of layers in encoder and decoder
        """
        super(WavenetVAE, self).__init__()
        self.params = clean_init_args(locals().copy())

        self.latent_width = latent_width
        self.encoder = TemporalEncoder(
            in_channels=in_channels, out_channels=2 * latent_width,
            n_blocks=n_blocks, n_layers=n_layers, width=encoder_width
        )
        self.decoder = WavenetDecoder(
            in_channels=in_channels, out_channels=out_channels,
            n_blocks=n_blocks, n_layers=n_layers,
            residual_width=2 * decoder_width, skip_width=decoder_width,
            conditional_dims=[(latent_width, False)]
        )

    def forward(self, x: torch.Tensor) \
            -> Tuple[torch.Tensor, dist.Normal, torch.Tensor]:
        embedding = self.encoder(x)
        q_loc = embedding[:, :self.latent_width, :]
        q_scale = F.softplus(embedding[:, self.latent_width:, :]) + 1e-7

        q = dist.Normal(q_loc, q_scale)
        x_q = q.rsample()
        x_q_log_prob = q.log_prob(x_q)

        x = shift1d(x, -1)
        logits = self.decoder(x, [x_q])
        return logits, x_q, x_q_log_prob

    @staticmethod
    def loss_function(model: nn.Module, x: torch.Tensor, y: torch.Tensor,
                      device: str, progress: float) \
            -> Tuple[torch.Tensor, torch.Tensor]:
        del progress
        logits, x_q, x_q_log_prob = model(x)

        ce_x = F.cross_entropy(logits, y.to(device))

        zx_p_loc = torch.zeros(x_q.size()).to(device)
        zx_p_scale = torch.ones(x_q.size()).to(device)
        pzx = dist.Normal(zx_p_loc, zx_p_scale)
        kl_zx = torch.sum(pzx.log_prob(x_q) - x_q_log_prob)

        loss = ce_x - kl_zx
        return loss, logits
