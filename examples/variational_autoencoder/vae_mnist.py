import torch
import torch.nn as nn

import math
import os
import sys

sys.path.append('..')

from zhusuan.framework.bn import BayesianNet
from zhusuan.variational.elbo import ELBO

from examples.utils import load_mnist_realval, save_img


class Generator(BayesianNet):
    def __init__(self, x_dim, z_dim, batch_size):
        super().__init__()
        self.x_dim = x_dim
        self.z_dim = z_dim
        self.batch_size = batch_size
        self.sequential = nn.Sequential(
            nn.Linear(z_dim, 500),
            nn.ReLU(),
            nn.Linear(500, 500),
            nn.ReLU(),
            nn.Linear(500, x_dim),
            nn.Sigmoid()
        )

    def forward(self, observed):
        self.observe(observed)
        mean = torch.zeros([self.batch_size, self.z_dim])
        std = torch.ones([self.batch_size, self.z_dim])

        z = self.normal(
            name='z',
            mean=mean,
            std=std,
            reparameterize=False,
            reduce_mean_dims=[0],
            reduce_sum_dims=[1])
        x_probs = self.sequential(z)
        self.cache['x_mean'] = x_probs
        sample_x = self.bernoulli(
            name='x',
            probs=x_probs,
            reduce_mean_dims=[0],
            reduce_sum_dims=[1])
        return self


class Variational(BayesianNet):
    def __init__(self, x_dim, z_dim, batch_size):
        super().__init__()
        self.x_dim = x_dim
        self.z_dim = z_dim
        self.batch_size = batch_size

        self.sq = nn.Sequential(
            nn.Linear(x_dim, 500),
            nn.ReLU(),
            nn.Linear(500, 500),
            nn.ReLU()
        )

        self.fc3 = nn.Linear(500, z_dim)
        self.fc4 = nn.Linear(500, z_dim)

        self.dist = None

    def forward(self, observed):
        self.observe(observed)
        x = self.observed['x']
        z_logits = self.sq(x)
        z_mean = self.fc3(z_logits)
        z_std = torch.exp(self.fc4(z_logits))

        z = self.normal(
            name='z',
            mean=z_mean,
            std=z_std,
            reparameterize=True,
            reduce_mean_dims=[0],
            reduce_sum_dims=[1])
        return self


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    epoch_size = 10
    batch_size = 64

    z_dim = 40
    x_dim = 28 * 28 * 1

    lr = 0.001

    generator = Generator(x_dim, z_dim, batch_size)
    variational = Variational(x_dim, z_dim, batch_size)
    model = ELBO(generator, variational).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr)

    x_train, t_train, x_valid, t_valid, x_test, t_test = load_mnist_realval()

    x_train = torch.as_tensor(x_train).to(device)
    x_test = torch.as_tensor(x_test).to(device)

    len_ = x_train.shape[0]
    num_batches = math.ceil(len_ / batch_size)

    for epoch in range(epoch_size):
        for step in range(num_batches):
            x = x_train[step * batch_size:min((step + 1) * batch_size, len_)]
            x = torch.reshape(x, [-1, x_dim])
            if x.shape[0] != batch_size:
                break
            loss = model({'x': x})
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            if (step + 1) % 100 == 0:
                print("Epoch[{}/{}], Step [{}/{}], Loss: {:.4f}".format(epoch + 1, epoch_size, step + 1, num_batches,
                                                                        loss))
                # float(loss.clone().detach().numpy())))

    batch_x = x_test[0:64]
    variational({'x': batch_x})
    z = variational.z.sample()
    cache = generator({'z': z}).cache
    sample = cache['x_mean'].cpu().detach().numpy()

    cache = generator({}).cache
    sample_gen = cache['x_mean'].cpu().detach().numpy()

    result_fold = './result'
    if not os.path.exists(result_fold):
        os.mkdir(result_fold)

    batch_x = batch_x.cpu().detach().numpy()

    save_img(batch_x, os.path.join(result_fold, 'origin_x_.png'))
    save_img(sample, os.path.join(result_fold, 'reconstruct_x_.png'))
    save_img(sample_gen, os.path.join(result_fold, 'sample_x_.png'))


if __name__ == '__main__':
    main()
