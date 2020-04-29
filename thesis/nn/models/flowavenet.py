from math import log, pi

import torch
from torch import nn
from torch.nn import functional as F

from . import BaseModel
from ..modules import STFTUpsample
from ..wavenet import Wavenet
from ...dist import norm_log_prob
from ...functional import (
    permute_L2C,
    flip,
    permute_C2L,
    chunk,
    interleave,
)
from ...utils import clean_init_args


class ActNorm(nn.Module):
    def __init__(self, in_channel):
        super().__init__()

        self.loc = nn.Parameter(torch.zeros(1, in_channel, 1), requires_grad=True)
        self.scale = nn.Parameter(torch.ones(1, in_channel, 1), requires_grad=True)

    def forward(self, x):
        B, _, T = x.size()

        log_abs = self.scale.abs().log()

        logdet = torch.sum(log_abs) * B * T

        return self.scale * (x + self.loc), logdet

    def reverse(self, output):
        return output / self.scale - self.loc


class AffineCoupling(nn.Module):
    def __init__(self, in_channel, width=256, num_layer=6, groups=1, cin_channel=None):
        super().__init__()

        self.groups = groups
        if cin_channel is not None:
            cin_channel = cin_channel // 2 * groups

        self.net = Wavenet(
            in_channels=in_channel // 2 * groups,
            out_channels=in_channel * groups,
            n_blocks=1,
            n_layers=num_layer,
            residual_channels=width * groups,
            gate_channels=width * groups,
            skip_channels=width * groups,
            kernel_size=3,
            cin_channels=cin_channel,
            groups=groups,
            causal=False,
            zero_final=True,
            bias=False,
        )

    def forward(self, x, c=None):
        in_a, in_b = chunk(x, groups=self.groups)

        if c is not None:
            c, _ = chunk(c, groups=self.groups)

        log_s, t = chunk(self.net(in_a, c), groups=self.groups)

        out_b = (in_b - t) * torch.exp(-log_s)
        logdet = torch.sum(-log_s)

        return interleave((in_a, out_b), groups=self.groups), logdet

    def reverse(self, output, c=None):
        out_a, out_b = chunk(output, groups=self.groups)

        if c is not None:
            c, _ = chunk(c, groups=self.groups)

        log_s, t = chunk(self.net(out_a, c), groups=self.groups)
        in_b = out_b * torch.exp(log_s) + t

        return interleave((out_a, in_b), groups=self.groups)


class Flow(nn.Module):
    def __init__(
        self, in_channel, width, num_layer, groups=1, cin_channel=None,
    ):
        super().__init__()
        self.groups = groups

        self.actnorm = ActNorm(in_channel * groups)
        self.coupling = AffineCoupling(
            in_channel,
            width=width,
            num_layer=num_layer,
            groups=groups,
            cin_channel=cin_channel,
        )

    def forward(self, x, c=None):
        out, logdet = self.actnorm(x)
        out, logdet_c = self.coupling(out, c)

        out = flip(out, groups=self.groups)
        if c is not None:
            c = flip(c, groups=self.groups)

        if logdet_c is not None:
            logdet += logdet_c

        return out, c, logdet

    def reverse(self, out, c=None):
        out = flip(out, groups=self.groups)

        if c is not None:
            c = flip(c, groups=self.groups)

        x = self.coupling.reverse(out, c)
        x = self.actnorm.reverse(x)
        return x, c


class Block(nn.Module):
    def __init__(
        self,
        in_channel,
        n_flow,
        n_layer,
        width,
        split=False,
        cin_channel=None,
        groups=1,
    ):
        super().__init__()

        self.groups = groups
        self.split = split
        squeeze_dim = in_channel * 2
        if cin_channel is not None:
            cin_channel = cin_channel * 2

        self.flows = nn.ModuleList()
        for i in range(n_flow):
            self.flows.append(
                Flow(
                    squeeze_dim,
                    width=width,
                    num_layer=n_layer,
                    cin_channel=cin_channel,
                    groups=groups,
                )
            )

        if cin_channel is not None:
            cin_channel *= groups

        if self.split:
            self.prior = Wavenet(
                in_channels=squeeze_dim // 2 * groups,
                out_channels=squeeze_dim * groups,
                n_blocks=1,
                n_layers=2,
                residual_channels=width * groups,
                gate_channels=width * groups,
                skip_channels=width * groups,
                kernel_size=3,
                cin_channels=cin_channel,
                causal=False,
                zero_final=True,
                bias=False,
                groups=groups,
            )

    def forward(self, x, c=None):
        x = permute_L2C(x)

        if c is not None:
            c = permute_L2C(c)

        logdet, log_p = 0, 0
        for k, flow in enumerate(self.flows):
            x, c, _logdet = flow(x, c)
            logdet = logdet + _logdet

        if self.split:
            x, z = chunk(x, groups=self.groups)
            # WaveNet prior
            μ, σ = chunk(self.prior(x, c), groups=self.groups)
            N, _, L = μ.shape
            log_p = norm_log_prob(z, μ, σ).view(N, self.groups, -1, L).sum(2)

        return x, c, logdet, log_p

    def reverse(self, output, c=None, eps=None):
        if self.split:
            μ, σ = chunk(self.prior(output, c), groups=self.groups)
            z_new = μ + σ.exp() * eps

            x = interleave((output, z_new), groups=self.groups)
        else:
            x = output

        for i, flow in enumerate(self.flows[::-1]):
            x, c = flow.reverse(x, c)

        unsqueezed_x = permute_C2L(x)
        if c is not None:
            c = permute_C2L(c)

        return unsqueezed_x, c


class Flowavenet(BaseModel):
    def __init__(
        self,
        in_channel,
        n_block,
        n_flow,
        n_layer,
        width,
        block_per_split,
        cin_channel=None,
        groups=1,
        **kwargs,
    ):
        super(Flowavenet, self).__init__(**kwargs)
        self.params = clean_init_args(locals().copy())
        self.groups = groups
        self.block_per_split, self.n_block = block_per_split, n_block

        if cin_channel is not None:
            self.c_up = STFTUpsample([16, 16])

        self.blocks = nn.ModuleList()
        for i in range(self.n_block):
            split = (i < self.n_block - 1) and (i + 1) % self.block_per_split == 0

            self.blocks.append(
                Block(
                    in_channel,
                    n_flow,
                    n_layer,
                    split=split,
                    width=width,
                    cin_channel=cin_channel,
                    groups=groups,
                )
            )
            if cin_channel is not None:
                cin_channel *= 2
            if not split:
                in_channel *= 2

    def forward(self, x, c=None):
        N, _, L = x.size()
        logdet, log_p_sum = 0, 0
        out = x

        if c is not None:
            c = self.c_up(c, L)

        for k, block in enumerate(self.blocks):
            out, c, logdet_new, logp_new = block(out, c)
            logdet = logdet + logdet_new
            if isinstance(logp_new, torch.Tensor):
                logp_new = F.interpolate(logp_new, size=L)
            log_p_sum = logp_new + log_p_sum

        log_p_out = -0.5 * (log(2.0 * pi) + out.pow(2))
        log_p_out = log_p_out.view(N, self.groups, -1, L).sum(2)
        log_p_out = F.interpolate(log_p_out, size=L)
        log_p = log_p_sum + log_p_out
        logdet = logdet / (N * L)
        return log_p, logdet

    def reverse(self, z, c=None):
        if c is not None:
            L, LC = z.shape[-1], c.shape[-1]
            if L != LC:
                c = self.c_up(c, L)

        z_list = []
        x = z
        for i in range(self.n_block):
            x = permute_L2C(x)
            if c is not None:
                c = permute_L2C(c)
            if not ((i + 1) % self.block_per_split or i == self.n_block - 1):
                x, z = chunk(x, groups=self.groups)
                z_list.append(z)

        for i, block in enumerate(self.blocks[::-1]):
            index = self.n_block - i
            if not (index % self.block_per_split or index == self.n_block):
                x, c = block.reverse(x, c, z_list[index // self.block_per_split - 1])
            else:
                x, c = block.reverse(x, c)
        return x

    def test(self, s, m):
        C = s.shape[1]
        if m.dim() > 3:
            m = m.flatten(1, 2)
        log_p, logdet = self.forward(m)

        self.ℒ.logdet = -torch.mean(logdet)
        ℒ = self.ℒ.logdet

        log_p = -log_p.mean(-1).mean(0)
        for c in range(C):
            setattr(self.ℒ, f"log_p/{c}", log_p[c])
            ℒ += getattr(self.ℒ, f"log_p/{c}")
        return ℒ
