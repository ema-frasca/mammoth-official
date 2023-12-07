# Copyright 2022-present, Lorenzo Bonicelli, Pietro Buzzega, Matteo Boschini, Angelo Porrello, Simone Calderara.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from argparse import Namespace
from typing import Tuple

import numpy as np
import torch.nn as nn
import torch.optim
from torch.utils.data import DataLoader, Dataset

from utils.conf import create_seeded_dataloader


class ContinualDataset:
    """
    A base class for defining continual learning datasets.

    Attributes:
        NAME (str): the name of the dataset
        SETTING (str): the setting of the dataset
        N_CLASSES_PER_TASK (int): the number of classes per task
        N_TASKS (int): the number of tasks
        N_CLASSES (int): the number of classes
        SIZE (Tuple[int]): the size of the dataset
        train_loader (DataLoader): the training loader
        test_loaders (List[DataLoader]): the test loaders
        i (int): the current task
        args (Namespace): the arguments which contains the hyperparameters
    """

    NAME: str
    SETTING: str
    N_CLASSES_PER_TASK: int
    N_TASKS: int
    N_CLASSES: int
    SIZE: Tuple[int]

    def __init__(self, args: Namespace) -> None:
        """
        Initializes the train and test lists of dataloaders.
        :param args: the arguments which contains the hyperparameters
        """
        self.train_loader = None
        self.test_loaders = []
        self.i = 0
        self.args = args
        self.N_CLASSES = self.N_CLASSES if hasattr(self, 'N_CLASSES') else \
            (self.N_CLASSES_PER_TASK * self.N_TASKS) if isinstance(self.N_CLASSES_PER_TASK, int) else sum(self.N_CLASSES_PER_TASK)

        if self.args.permute_classes:
            if not hasattr(self.args, 'class_order'):  # set only once
                if self.args.seed is not None:
                    np.random.seed(self.args.seed)
                if isinstance(self.N_CLASSES_PER_TASK, int):
                    self.args.class_order = np.random.permutation(self.N_CLASSES_PER_TASK * self.N_TASKS)
                else:
                    self.args.class_order = np.random.permutation(sum(self.N_CLASSES_PER_TASK))

        if args.joint:
            self.N_CLASSES_PER_TASK = self.N_CLASSES
            self.N_TASKS = 1

        if not all((self.NAME, self.SETTING, self.N_CLASSES_PER_TASK, self.N_TASKS, self.SIZE, self.N_CLASSES)):
            raise NotImplementedError('The dataset must be initialized with all the required fields.')

    def get_data_loaders(self) -> Tuple[DataLoader, DataLoader]:
        """Creates and returns the training and test loaders for the current task.
        The current training loader and all test loaders are stored in self.
        :return: the current training and test loaders
        """
        raise NotImplementedError

    @staticmethod
    def get_backbone() -> nn.Module:
        """Returns the backbone to be used for the current dataset."""
        raise NotImplementedError

    @staticmethod
    def get_transform() -> nn.Module:
        """Returns the transform to be used for the current dataset."""
        raise NotImplementedError

    @staticmethod
    def get_loss() -> nn.Module:
        """Returns the loss to be used for the current dataset."""
        raise NotImplementedError

    @staticmethod
    def get_normalization_transform() -> nn.Module:
        """Returns the transform used for normalizing the current dataset."""
        raise NotImplementedError

    @staticmethod
    def get_denormalization_transform() -> nn.Module:
        """Returns the transform used for denormalizing the current dataset."""
        raise NotImplementedError

    @staticmethod
    def get_scheduler(model, args: Namespace) -> torch.optim.lr_scheduler._LRScheduler:
        """Returns the scheduler to be used for the current dataset."""
        return None

    @staticmethod
    def get_epochs():
        """Returns the number of epochs to be used for the current dataset."""
        raise NotImplementedError

    @staticmethod
    def get_batch_size():
        """Returns the batch size to be used for the current dataset."""
        raise NotImplementedError

    @classmethod
    def get_minibatch_size(cls):
        """Returns the minibatch size to be used for the current dataset."""
        return cls.get_batch_size()


def _get_mask_unlabeled(train_dataset, setting: ContinualDataset):
    if setting.args.label_perc == 1:
        return np.zeros(train_dataset.targets.shape[0]).astype('bool')
    else:
        lpc = int(setting.args.label_perc * (train_dataset.targets.shape[0] // setting.N_CLASSES_PER_TASK))
        ind = np.indices(train_dataset.targets.shape)[0]
        mask = []
        for i_label, _ in enumerate(np.unique(train_dataset.targets)):
            partial_targets = train_dataset.targets[train_dataset.targets == i_label]
            current_mask = np.random.choice(partial_targets.shape[0], max(
                partial_targets.shape[0] - lpc, 0), replace=False)

            mask = np.append(mask, ind[train_dataset.targets == i_label][current_mask])

        return mask.astype(np.int32)


def _prepare_data_loaders(train_dataset, test_dataset, setting: ContinualDataset):
    if isinstance(train_dataset.targets, list) or not train_dataset.targets.dtype is torch.long:
        train_dataset.targets = torch.tensor(train_dataset.targets, dtype=torch.long)
    if isinstance(test_dataset.targets, list) or not test_dataset.targets.dtype is torch.long:
        test_dataset.targets = torch.tensor(test_dataset.targets, dtype=torch.long)

    setting.unlabeled_mask = _get_mask_unlabeled(train_dataset, setting)

    if setting.unlabeled_mask.sum() != 0:
        train_dataset.targets[setting.unlabeled_mask] = -1  # -1 is the unlabeled class

    return train_dataset, test_dataset


def store_masked_loaders(train_dataset: Dataset, test_dataset: Dataset,
                         setting: ContinualDataset) -> Tuple[DataLoader, DataLoader]:
    """
    Divides the dataset into tasks.

    Attributes:
        train_dataset (Dataset): the training dataset
        test_dataset (Dataset): the test dataset
        setting (ContinualDataset): the setting of the dataset

    Returns:
        the training and test loaders
    """
    if setting.args.permute_classes:
        train_dataset.targets = setting.args.class_order[np.array(train_dataset.targets)]
        test_dataset.targets = setting.args.class_order[np.array(test_dataset.targets)]

    train_mask = np.logical_and(np.array(train_dataset.targets) >= setting.i,
                                np.array(train_dataset.targets) < setting.i + setting.N_CLASSES_PER_TASK)
    test_mask = np.logical_and(np.array(test_dataset.targets) >= setting.i,
                               np.array(test_dataset.targets) < setting.i + setting.N_CLASSES_PER_TASK)

    train_dataset.data = train_dataset.data[train_mask]
    test_dataset.data = test_dataset.data[test_mask]

    train_dataset.targets = np.array(train_dataset.targets)[train_mask]
    test_dataset.targets = np.array(test_dataset.targets)[test_mask]

    train_dataset, test_dataset = _prepare_data_loaders(train_dataset, test_dataset, setting)

    train_loader = create_seeded_dataloader(setting.args, train_dataset,
                                            batch_size=setting.args.batch_size, shuffle=True)
    test_loader = create_seeded_dataloader(setting.args, test_dataset,
                                           batch_size=setting.args.batch_size, shuffle=False)
    setting.test_loaders.append(test_loader)
    setting.train_loader = train_loader

    setting.i += setting.N_CLASSES_PER_TASK
    return train_loader, test_loader
