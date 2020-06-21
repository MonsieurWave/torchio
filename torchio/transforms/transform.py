import numbers
import warnings
from typing import Union
from copy import deepcopy
from abc import ABC, abstractmethod

import torch
import numpy as np
import SimpleITK as sitk

from .. import TypeData, INTENSITY, DATA
from ..data.image import Image
from ..data.subject import Subject
from ..data.dataset import ImagesDataset
from ..utils import nib_to_sitk, sitk_to_nib
from .interpolation import Interpolation


class Transform(ABC):
    """Abstract class for all TorchIO transforms.

    All classes used to transform a sample from an
    :py:class:`~torchio.ImagesDataset` should subclass it.
    All subclasses should overwrite
    :py:meth:`torchio.tranforms.Transform.apply_transform`,
    which takes a sample, applies some transformation and returns the result.

    Args:
        p: Probability that this transform will be applied.
    """
    def __init__(self, p: float = 1, is_tensor = False):
        self.is_tensor = is_tensor
        self.probability = self.parse_probability(p)

    def __call__(self, data: Union[Subject, torch.Tensor]):
        """Transform a sample and return the result.

        Args:
            data: Instance of :py:class:`~torchio.Subject`, or 4D
                :py:class:`torch.Tensor` or NumPy array with dimensions
                :math:`(C, D, H, W)`, where :math:`C` is the number of channels
                and :math:`D, H, W` are the spatial dimensions. If the input is
                a tensor, the affine matrix is an identity and a tensor will be
                also returned.
        """
        if isinstance(data, (np.ndarray, torch.Tensor)):
            is_array = isinstance(data, np.ndarray)
            is_tensor = True
            sample = self.parse_tensor(data)
        else:
            is_tensor = is_array = False
            sample = data
        self.parse_sample(sample)
        if torch.rand(1).item() > self.probability:
            return data
        sample = deepcopy(sample)

        with np.errstate(all='raise'):
            transformed = self.apply_transform(sample)

        if is_tensor:
            num_channels = len(data)
            images = [
                transformed[f'channel_{i}'][DATA]
                for i in range(num_channels)
            ]
            transformed = torch.cat(images)
        if is_array:
            transformed = transformed.numpy()
        return transformed

    @abstractmethod
    def apply_transform(self, sample: Subject):
        raise NotImplementedError

    @staticmethod
    def parse_probability(probability: float) -> float:
        is_number = isinstance(probability, numbers.Number)
        if not (is_number and 0 <= probability <= 1):
            message = (
                'Probability must be a number in [0, 1],'
                f' not {probability}'
            )
            raise ValueError(message)
        return probability

    @staticmethod
    def parse_sample(sample: Subject) -> None:
        if not isinstance(sample, Subject) or not sample.is_sample:
            message = (
                'Input to a transform must be a PyTorch tensor or an instance'
                ' of torchio.Subject generated by a torchio.ImagesDataset,'
                f' not "{type(sample)}"'
            )
            raise RuntimeError(message)

    def parse_tensor(self, data: TypeData) -> Subject:
        if isinstance(data, np.ndarray):
            tensor = torch.from_numpy(data)
        else:
            tensor = data
        tensor = tensor.float()  # does nothing if already float
        num_dimensions = tensor.dim()
        if num_dimensions != 4:
            message = (
                'The input tensor must have 4 dimensions (channels, i, j, k),'
                f' but has {num_dimensions}: {tensor.shape}'
            )
            raise RuntimeError(message)
        return self._get_subject_from_tensor(tensor)

    @staticmethod
    def parse_interpolation(interpolation: str) -> Interpolation:
        if isinstance(interpolation, Interpolation):
            message = (
                'Interpolation of type torchio.Interpolation'
                ' is deprecated, please use a string instead'
            )
            warnings.warn(message, FutureWarning)
        elif isinstance(interpolation, str):
            interpolation = interpolation.lower()
            supported_values = [key.name.lower() for key in Interpolation]
            if interpolation in supported_values:
                interpolation = getattr(Interpolation, interpolation.upper())
            else:
                message = (
                    f'Interpolation "{interpolation}" is not among'
                    f' the supported values: {supported_values}'
                )
                raise AttributeError(message)
        else:
            message = (
                'image_interpolation must be a string,'
                f' not {type(interpolation)}'
            )
            raise TypeError(message)
        return interpolation

    @staticmethod
    def _get_subject_from_tensor(tensor: torch.Tensor) -> Subject:
        subject_dict = {}
        for channel_index, channel_tensor in enumerate(tensor):
            name = f'channel_{channel_index}'
            image = Image(tensor=channel_tensor, type=INTENSITY)
            subject_dict[name] = image
        subject = Subject(subject_dict)
        dataset = ImagesDataset([subject])
        sample = dataset[0]
        return sample

    @staticmethod
    def nib_to_sitk(data: TypeData, affine: TypeData):
        return nib_to_sitk(data, affine)

    @staticmethod
    def sitk_to_nib(image: sitk.Image):
        return sitk_to_nib(image)

    @property
    def name(self):
        return self.__class__.__name__
