#!/usr/bin/env python
import os
import subprocess
from argparse import ArgumentParser
from datetime import datetime

from colorama import Fore

from train import EXPERIMENTS


def main(args):
    if args.file not in ("make", "train"):
        raise ValueError("Invalid file given")
    if args.file == "train" and args.experiment not in EXPERIMENTS:
        raise ValueError("Invalid experiment given.")

    if args.cpu:
        p = "normal"
    else:
        p = "gpu_short" if args.short else "gpu_shared"

    t = "0:35:00" if args.short else f"{args.hours}:00:00"
    if args.short:
        args.batch_size = 2

    name = args.experiment
    if args.k:
        name += "_" + args.k

    c = {
        "job-name": name,
        "time": t,
        "mem": "16000M",
        "partition": p,
        "output": f"./log/{datetime.today():%b%d-%H%M}_%x_{p}.out",
    }
    if not args.cpu:
        c["gres"] = f"gpu:{args.ngpu}"

    f = f"#!/usr/bin/env bash\n\n"
    f += "\n".join(f"#SBATCH --{k}={v}" for k, v in c.items()) + "\n"
    f += (
        '\nexport PATH="/home/frankm/.local/bin:$PATH"\n'
        "export LD_LIBRARY_PATH="
        "/hpc/eb/Debian/cuDNN/7.4.2-CUDA-10.0.130/lib64:$LD_LIBRARY_PATH\n"
        "export LC_ALL=en_US.utf8\n"
        'export LANG="$LC_ALL"\n\n'
    )
    f += "cd /home/frankm/thesis\n"

    f += (
        f"srun /home/frankm/.pyenv/shims/python3.7 {args.file}.py " f"{args.experiment}"
    )

    if args.file == "train":
        f += f" --batch_size={args.batch_size} -wandb --gpu {' '.join(map(str, range(args.ngpu)))}"
        if args.lr is not None:
            f += f" -lr {args.lr}"
        if args.noise is not None:
            f += f" -noise {args.noise}"

    if args.weights is not None:
        f += f" --weights=\"{args.weights}\""

    if args.k is not None:
        f += f" -k {args.k}"

    if args.debug:
        f += " -debug"

    if args.musdb:
        f += " -musdb"

    fn = "_temp.job"
    with open(fn, "w") as fp:
        fp.write(f + "\n")
    os.makedirs("./log/", exist_ok=True)
    print(Fore.YELLOW + f"Written job file ./{fn}")
    if not args.test:
        rc = subprocess.call(["sbatch", fn])
        if rc == 0:
            os.remove(fn)
        exit(rc)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("experiment", type=str)
    parser.add_argument("-t", type=str, default='5', dest="hours")
    parser.add_argument("-f", type=str, default="train", dest="file")
    parser.add_argument("-k", type=str, required=False)
    parser.add_argument("--batch_size", type=int)
    parser.add_argument("-short", action="store_true")
    parser.add_argument("-debug", action="store_true")
    parser.add_argument("-musdb", action="store_true")
    parser.add_argument("-test", action="store_true", help="Just print the file")
    parser.add_argument("--weights")
    parser.add_argument("-lr")
    parser.add_argument("-cpu", action="store_true")
    parser.add_argument("-ngpu", default=1, type=int)
    parser.add_argument("-noise")
    main(parser.parse_args())
