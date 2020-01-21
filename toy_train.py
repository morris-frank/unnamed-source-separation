from nsynth.config import make_config
from nsynth.training import train
from toy.data import ToyDataSingle, ToyDataSequential
from toy.optim import vqvae_loss, multivae_loss
from toy.vae import ConditionalWavenetVQVAE, WavenetMultiVAE


def main(args):
    args.epochs = 50000
    args.n_batch = 20
    μ = 100
    crop = 3 * 2 ** 10

    device = f'cuda:{args.gpu[0]}' if args.gpu else 'cpu'

    if args.vae:
        ns = 4
        steps = 5
        model = WavenetMultiVAE(n=ns, in_channels=1, out_channels=μ + 1,
                                latent_width=32, encoder_width=64,
                                decoder_width=32)
        loss_function = multivae_loss(ns, μ=μ + 1, β=1.1)
        traindata = ToyDataSequential(
            f'{args.datadir}/toy_train_long_*.npy', μ=μ, crop=crop,
            nbatch=args.n_batch, steps=steps).loader(args.n_batch)
        testdata = ToyDataSequential(
            f'{args.datadir}/toy_test_long_*.npy', μ=μ, crop=crop,
            nbatch=args.n_batch, steps=steps).loader(args.n_batch)
    else:
        ns = 8
        model = ConditionalWavenetVQVAE(n_sources=ns, K=ns, D=512, n_blocks=3,
                                        n_layers=10, encoder_width=64,
                                        decoder_width=32, in_channels=1,
                                        out_channels=μ + 1, device=device)
        loss_function = vqvae_loss()
        traindata = ToyDataSingle(f'{args.datadir}/toy_train_large.npy',
                                  crop=crop, μ=μ).loader(args.n_batch)
        testdata = ToyDataSingle(f'{args.datadir}/toy_test_large.npy',
                                 crop=crop, μ=μ).loader(args.n_batch)

    train(model=model,
          loss_function=loss_function,
          gpu=args.gpu,
          trainset=traindata,
          testset=testdata,
          paths={'save': './models_toy/', 'log': './log_toy/'},
          iterpoints={'print': args.it_print, 'save': args.it_save,
                      'test': args.it_test},
          n_it=args.epochs,
          use_board=args.board,
          use_manual_scheduler=args.original_lr_scheduler,
          save_suffix=f'det_{ns}'
          )


if __name__ == '__main__':
    main(make_config('train').parse_args())
