#!/usr/bin/env python
from argparse import ArgumentParser
from os import makedirs
from os.path import abspath

import numpy as np
import torch
from colorama import Fore
from tqdm import tqdm, trange

from thesis.data.toy import ToyDataSourceK, ToyDataMixes
from thesis.utils import get_newest_file
from thesis.io import load_model
from thesis.plot import toy
import matplotlib as mpl
import matplotlib.pyplot as plt

mpl.use('agg')


def make_cross_likelihood_plot(data):
    fp = "./figures/cross_likelihood.npy"
    K = 4

    weights = [
        "Mar03-2158_Flowavenet_sin_049999.pt",
        "Mar04-2242_Flowavenet_square_049999.pt",
        "Mar03-2158_Flowavenet_saw_049999.pt",
        "Mar03-2158_Flowavenet_triangle_049999.pt",
    ]

    results = None
    for n in trange(len(weights)):
        model = torch.load(f"./checkpoints/{weights[n]}")["model"].to("cuda")
        model.eval()
        for k in trange(K, leave=False):
            test_set = ToyDataSourceK(path=f"{data}/test/", k=k, mel=True)
            if results is None:
                results = np.zeros((K, K, len(test_set), 2))
            for i, (sig, mel) in enumerate(tqdm(test_set, leave=False)):
                sig = sig.unsqueeze(0).to("cuda")
                mel = mel.unsqueeze(0).to("cuda")
                results[n, k, i, :] = model.forward(sig, mel)
            np.save(fp, results)


def make_separation_examples(data):
    weights = "Mar11-1028_UMixer_supervised_010120.pt"
    makedirs(f"./figures/{weights}/", exist_ok=True)
    model = load_model(f"./checkpoints/{weights}", "cuda").to("cuda")
    dset = ToyDataMixes(path=f"{data}/test/", mel=True, sources=True)
    for i, ((mix, mel), sources) in enumerate(tqdm(dset)):
        mix = mix.unsqueeze(0).to("cuda")
        mel = mel.unsqueeze(0).to("cuda")
        ŝ = model.umix(mix, mel)[0]
        fig = toy.plot_reconstruction(sources, ŝ, mix)
        plt.savefig(f"./figures/{weights}/separate_{i}.png", dpi=200)
        plt.close()


def main(args):
    if args.weights is None:
        args.weights = get_newest_file("./checkpoints")
        print(
            f"{Fore.YELLOW}Weights not given. Using instead: {Fore.GREEN}{args.weights}{Fore.RESET}"
        )

    makedirs("./figures", exist_ok=True)

    if args.command == "cross-likelihood":
        make_cross_likelihood_plot(args.data)
    elif args.command == "separate":
        make_separation_examples(args.data)
    else:
        raise ValueError("Invalid Command given")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("command", type=str, help="show ∨ something")
    parser.add_argument("--weights", type=abspath)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--data", type=abspath, default="/home/morris/var/data/toy")
    main(parser.parse_args())
