import torch
from torch import nn

from .modules import BlockWiseConv1d
from .utils import encode_μ_law


class TemporalEncoder(nn.Module):
    """
    The Non-Causal Temporal Encoder as described in NSynth [http://arxiv.org/abs/1704.01279].
    """

    def __init__(self,
                 n_channels: int,
                 n_layers: int = 3,
                 n_stages: int = 10,
                 hidden_dims: int = 128,
                 kernel_size: int = 3,
                 bottleneck_dims: int = 16,
                 hop_length: int = 512,
                 μ_encode: bool = True,
                 use_bias: bool = True):
        """
        The Non-Causal Temporal Encoder as described in NSynth [http://arxiv.org/abs/1704.01279].

        Args:
            n_channels: Number of input channels
            n_layers: Number of layers in each stage in the encoder
            n_stages: Number of stages
            hidden_dims: Size of the hidden channels in all layers
            kernel_size: KS for all 1D-convolutions
            bottleneck_dims: Final number of features
            hop_length: Final bottleneck pooling
            μ_encode: Whether to μ-law encode inputs before the encoder
            use_bias: Whether to use bias in all the convolutions.
        """
        super(TemporalEncoder, self).__init__()
        self.μ_encode = μ_encode

        self.encoder = []
        self.encoder.append(
            BlockWiseConv1d(in_channels=n_channels,
                            out_channels=hidden_dims,
                            kernel_size=kernel_size,
                            causal=False,
                            block_size=1,
                            bias=use_bias)
        )
        for idx in range(n_stages * n_layers):
            dilation = 2 ** (idx % n_stages)
            self.encoder.extend([
                nn.ReLU(),
                BlockWiseConv1d(in_channels=hidden_dims,
                                out_channels=hidden_dims,
                                kernel_size=kernel_size,
                                causal=False,
                                block_size=dilation,
                                bias=use_bias),
                nn.ReLU(),
                BlockWiseConv1d(in_channels=hidden_dims,
                                out_channels=hidden_dims,
                                kernel_size=1,
                                causal=True,
                                block_size=1,
                                bias=use_bias)
            ])

        # Bottleneck
        self.encoder.append(
            nn.Conv1d(in_channels=hidden_dims,
                      out_channels=bottleneck_dims,
                      kernel_size=1,
                      bias=use_bias)
        )
        self.encoder.append(
            nn.AvgPool1d(kernel_size=hop_length)
        )
        self.encoder = nn.ModuleList(self.encoder)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.μ_encode:
            x = encode_μ_law(x) / 128.
        return self.encoder(x)
