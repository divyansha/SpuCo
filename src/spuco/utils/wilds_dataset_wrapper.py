from torch.utils.data import Dataset 
from wilds.datasets.wilds_dataset import WILDSDataset 
from tqdm import tqdm 
from typing import Dict, List, Tuple

class WILDSDatasetWrapper(Dataset):
    """
    Wrapper class that wraps WILDSDataset into a Dataset to be compatible with SpuCo.
    """
    def __init__(
        self,
        dataset: WILDSDataset,
        metadata_spurious_label: str,
        verbose=False
    ):
        """
        Wraps  WILDS Dataset into a Dataset object. 

        :param dataset: The source WILDS dataset
        :type dataset: WILDDataset
        :param metadata_spurious_label: String name of property in metadata_map corresponding to spurious target
        :type metadata_spurious_label: str 
        :param verbose: Show logs
        :type verbose: bool
        """
        
        self.dataset = dataset
        self._num_classes = dataset.n_classes 

        # Get index in meta data array corresponding to spurious target 
        spurious_target_idx = dataset.metadata_fields.index(metadata_spurious_label)

        # Get spurious labels
        self._spurious = dataset.metadata_array[:, spurious_target_idx].long().tolist()

        # Create group partition using labels and spurious labels
        self._group_partition = {}
        for i, group_label in tqdm(
            enumerate(zip(dataset.y_array.long().tolist(), self._spurious)),
            desc="Partitioning data indices into groups",
            disable=not verbose,
            total=len(self.dataset)
        ):
            if group_label not in self._group_partition:
                self._group_partition[group_label] = []
            self._group_partition[group_label].append(i)
        
        # Set group weights based on group sizes
        self._group_weights = {}
        for group_label in self._group_partition.keys():
            self._group_weights[group_label] = len(self._group_partition[group_label]) / len(self.dataset)

    @property
    def group_partition(self) -> Dict[Tuple[int, int], List[int]]:
        """
        Dictionary partitioning indices into groups
        """
        return self._group_partition 
    
    @property
    def group_weights(self) -> Dict[Tuple[int, int], float]:
        """
        Dictionary containing the fractional weights of each group
        """
        return self._group_weights
    
    @property
    def spurious(self) -> List[int]:
        """
        List containing spurious labels for each example
        """
        return self._spurious

    @property
    def num_classes(self) -> int:
        """
        Number of classes
        """
        return self._num_classes

    def __getitem__(self, index):
        """
        Retrieves an item from the dataset.

        :param index: The index of the item.
        :type index: int
        :return: The item at the given index.
        """
        source_tuple = self.dataset.__getitem__(index)
        return (source_tuple[0], source_tuple[1])
    
    def __len__(self):
        """
        Returns the length of the dataset.

        :return: The length of the dataset.
        :rtype: int
        """
        return len(self.dataset)
