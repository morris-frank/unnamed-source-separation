import torch
from torch import nn

from .functions import VectorQuantizationStraightThrough, VectorQuantization


class VQEmbedding(nn.Module):
    def __init__(self, K, D):
        super(VQEmbedding, self).__init__()
        self.embedding = nn.Embedding(K, D)
        self.embedding.weight.data.uniform_(-1. / K, 1. / K)

    def forward(self, z_e_x):
        z_e_x_ = z_e_x.permute(0, 2, 1).contiguous()
        latents = VectorQuantization.apply(z_e_x_, self.embedding.weight)
        return latents

    def straight_through(self, z_e_x):
        z_e_x_ = z_e_x.permute(0, 2, 1).contiguous()
        z_q_x_, indices = VectorQuantizationStraightThrough.apply(
            z_e_x_, self.embedding.weight.detach())
        z_q_x = z_q_x_.permute(0, 2, 1).contiguous()

        z_q_x_bar_flatten = torch.index_select(self.embedding.weight,
                                               dim=0, index=indices)
        z_q_x_bar_ = z_q_x_bar_flatten.view_as(z_e_x_)
        z_q_x_bar = z_q_x_bar_.permute(0, 2, 1).contiguous()

        return z_q_x, z_q_x_bar
