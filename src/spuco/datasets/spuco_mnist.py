from enum import Enum
import itertools
from typing import List, Optional, Callable
import matplotlib.cm as cm
import numpy as np

import torch 
import torchvision
import torchvision.transforms as T

from spuco.datasets import BaseSpuCoDataset, SourceData, SpuriousFeatureDifficulty 

class ColourMap(Enum):
    HSV = "hsv"
    
class SpuCoMNIST(BaseSpuCoDataset):
    """
    A dataset consisting of images from the MNIST dataset
    with added spurious features to create a spurious MNIST dataset.
    """

    def __init__(
        self,
        root: str,
        spurious_feature_difficulty: SpuriousFeatureDifficulty,
        classes: List[List[int]],
        spurious_correlation_strength: float = -1.,
        color_map: ColourMap = ColourMap.HSV,
        train: bool = True,
        transform: Optional[Callable] = None
    ):
        """
        Initializes SpuCoMNIST dataset
        
        :param root: str
            Root directory of dataset.
        :param spurious_feature_difficulty: SpuriousFeatureDifficulty
            Difficulty level for adding spurious features.
        :param classes: List[List[int]]
            A list of lists of integer labels. 
            Each list contains a set of labels that belong to the same disentangled class.
        :param spurious_correlation_strength: float
            Strength of correlation for spurious features. Must be between 0 and 1.
        :param color_map: ColourMap
            Colormap for the disentangled classes.
        :param train: bool, default True
            If True, creates a train dataset. Otherwise, creates a test dataset.
        :param transform: Optional[Callable], default None
            A function/transform that takes in a sample and returns a transformed version.
        """
        super().__init__(
            root=root, 
            spurious_correlation_strength=spurious_correlation_strength,
            spurious_feature_difficulty=spurious_feature_difficulty,
            train=train,
            transform=transform
        )

        self.classes = classes
        self.colors = self.init_colors(color_map)

    def validate_data(self):
        """
        Validates that the generated dataset has been loaded correctly.
        """
        pass 

    def load_data(self) -> SourceData:
        """
        Loads the MNIST dataset and generates the spurious correlation dataset.

        :return: The spurious correlation dataset.
        :rtype: SourceData
        """
        self.mnist = torchvision.datasets.MNIST(
            root=self.root, 
            train=self.train, 
            download=self.download,
            transform=T.Compose([
                T.ToTensor(),
                T.Lambda(lambda x: torch.cat([x, x, x], dim=0))  # convert grayscale to RGB
            ])
        )
        self.data = SourceData(self.mnist)
        
        # Validate Classes
        assert SpuCoMNIST.validate_classes(self.classes), "Classes should be disjoint and only contain elements 0<= label <= 9"

        # Get New Labels
        kept = []
        for i, label in enumerate(self.data.labels):
            for class_idx, latent_class in enumerate(self.classes):
                if label in latent_class:
                    self.data.labels[i] = class_idx
                    kept.append(i)
        
        self.data.X = [self.data.X[i] for i in kept]
        self.data.labels = [self.data.labels[i] for i in kept]
        
        # Partition indices by new labels
        self.partition = {}
        for i, label in enumerate(self.data.labels):
            if label not in self.partition:
                self.partition[label] = []
            self.partition[label].append(i)

        # Train: Add spurious correlation iteratively for each class
        self.spurious = [-1] * len(self.data.X)
        if self.train:
            assert self.spurious_correlation_strength >= 0., "spurious correlation strength must be specified for train=True"
            spurious_distribution = torch.distributions.Bernoulli(probs=torch.tensor(self.spurious_correlation_strength))
            for label in self.partition.keys():
                spurious_or_not = spurious_distribution.sample((len(self.partition[label]),))
                other_labels = [x for x in range(len(self.classes)) if x != label]
                background_label = torch.tensor([label if spurious_or_not[i] else other_labels[i % len(other_labels)] for i in range(len(self.partition[label]))])
                background_label = background_label[torch.randperm(len(background_label))]
                for i, idx in enumerate(self.partition[label]):
                    self.spurious[idx] = background_label[i].item()
                    background = SpuCoMNIST.create_background(self.spurious_feature_difficulty, self.colors[self.spurious[idx]])
                    self.data.X[idx] = (background * (self.data.X[idx] == 0)) + self.data.X[idx]
        # Test: Create spurious balanced test set
        else:
            for label in self.partition.keys():
                background_label = torch.tensor([i % len(self.classes) for i in range(len(self.partition[label]))])
                background_label = background_label[torch.randperm(len(background_label))]
                for i, idx in enumerate(self.partition[label]):
                    self.spurious[idx] = background_label[i].item()
                    background = SpuCoMNIST.create_background(self.spurious_feature_difficulty, self.colors[self.spurious[idx]])
                    self.data.X[idx] = (background * (self.data.X[idx] == 0)) + self.data.X[idx]    

        return self.data

    def init_colors(self, color_map: ColourMap) -> List[List[float]]:
        """
        Initializes the color values for the spurious features.

        :param color_map: The color map to use for the spurious features. Should be a value from the `ColourMap`
            enum class.
        :type color_map: ColourMap
        
        :return: The color values for the spurious features.
        :rtype: List[List[float]]
        """
        color_map = cm.get_cmap(color_map.value)
        cmap_vals = np.arange(0, 1, step=1 / len(self.classes))
        colors = []
        for i in range(len(self.classes)):
            rgb = color_map(cmap_vals[i])[:3]
            rgb = [np.float(x) for x in np.array(rgb)]
            colors.append(rgb)
        # Append black as no-spurious background
        colors.append([0., 0., 0.])
        return colors
    
    @staticmethod
    def validate_classes(classes: List[List[int]]) -> bool:
        """
        Validates that the classes provided to the `SpuCoMNIST` dataset are disjoint and only contain integers
        between 0 and 9.

        :param classes: The classes to be included in the dataset, where each element is a list of integers
            representing the digits to be included in a single class.
        :type classes: List[List[int]]

        :return: Whether the classes are valid.
        :rtype: bool
        """
        sets = [set(latent_class) for latent_class in classes]

        for i in range(len(sets)):
            if any([x < 0 or x > 9 for x in sets[i]]):
                return False
            for j in range(i + 1, len(sets)):
                if sets[i].intersection(sets[j]):
                    return False
        return True

    @staticmethod
    def create_background(spurious_feature_difficulty: SpuriousFeatureDifficulty, hex_code: str) -> torch.Tensor:
        """
        Generates a tensor representing a background image with a specified spurious feature difficulty and hex code color.

        :param spurious_feature_difficulty: The difficulty level of the spurious feature to add to the background image.
        :type spurious_feature_difficulty: SpuriousFeatureDifficulty

        :param hex_code: The hex code of the color to use for the background image.
        :type hex_code: str

        :return: A tensor representing the generated background image.
        :rtype: torch.Tensor
        """
        background = SpuCoMNIST.rgb_to_mnist_background(hex_code)
        if spurious_feature_difficulty == SpuriousFeatureDifficulty.MAGNITUDE_EASY:
            return background
        elif spurious_feature_difficulty == SpuriousFeatureDifficulty.MAGNITUDE_MEDIUM:
            unmask_points = torch.tensor(list(itertools.product(range(4), range(4))))
            mask = SpuCoMNIST.compute_mask(unmask_points)
        elif spurious_feature_difficulty == SpuriousFeatureDifficulty.MAGNITUDE_HARD:
            unmask_points = torch.tensor(list(itertools.product(range(2), range(2))))
            mask = SpuCoMNIST.compute_mask(unmask_points)
        elif spurious_feature_difficulty == SpuriousFeatureDifficulty.VARIANCE_EASY:
            unmask_points = torch.tensor(list(itertools.product(range(7), range(7))))
            mask = SpuCoMNIST.compute_mask(unmask_points)
        elif spurious_feature_difficulty == SpuriousFeatureDifficulty.VARIANCE_MEDIUM:
            all_points = torch.tensor(list(itertools.product(range(14), range(14))))
            unmask_points = all_points[torch.randperm(len(all_points))[:49]]
            mask = SpuCoMNIST.compute_mask(unmask_points)
        elif spurious_feature_difficulty == SpuriousFeatureDifficulty.VARIANCE_HARD:
            all_points = torch.tensor(list(itertools.product(range(28), range(28))))
            unmask_points = all_points[torch.randperm(len(all_points))[:49]]
            mask = SpuCoMNIST.compute_mask(unmask_points)
        return background * mask
    
    @staticmethod
    def compute_mask(unmask_points: torch.Tensor) -> torch.Tensor:
        rows = torch.tensor([point[0] for point in unmask_points])
        cols = torch.tensor([point[1] for point in unmask_points])
        mask = torch.zeros((3,28,28))
        mask[:, rows, cols] = 1.
        return mask
    
    @staticmethod
    def rgb_to_mnist_background(rgb: List[float]) -> torch.Tensor:
        return torch.tensor(rgb).unsqueeze(1).unsqueeze(2).repeat(1, 28, 28)  