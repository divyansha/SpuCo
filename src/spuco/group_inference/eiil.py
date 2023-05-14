import torch 
from torch import nn, optim
from tqdm import tqdm
from spuco.group_inference import BaseGroupInference

class EIIL(BaseGroupInference):
    def __init__(
        self, 
        logits: torch.Tensor, 
        labels: torch.Tensor,
        num_steps: int, 
        lr: float,
        device: torch.device = torch.device("cpu"),
        verbose: bool = False

    ):
        self.logits = logits 
        self.labels = labels
        self.num_steps = num_steps
        self.lr = lr
        self.device = device
        self.verbose = verbose

    def infer_groups(self):
        """Learn soft environment assignment."""

        # Initialize
        scale = torch.tensor(1.).to(self.device).requires_grad_()
        train_criterion = nn.CrossEntropyLoss(reduction='none')
        loss = train_criterion(self.logits.to(self.device) * scale, self.labels.long().to(self.device))
        env_w = torch.randn(len(self.logits)).to(self.device).requires_grad_()
        optimizer = optim.Adam([env_w], lr=self.lr)

        # Train assignment
        for i in tqdm(range(self.num_steps), disable=not self.verbose):
            # penalty for env a
            lossa = (loss.squeeze() * env_w.sigmoid()).mean()
            grada = torch.autograd.grad(lossa, [scale], create_graph=True)[0]
            penaltya = torch.sum(grada**2)
            # penalty for env b
            lossb = (loss.squeeze() * (1-env_w.sigmoid())).mean()
            gradb = torch.autograd.grad(lossb, [scale], create_graph=True)[0]
            penaltyb = torch.sum(gradb**2)
            # negate
            npenalty = - torch.stack([penaltya, penaltyb]).mean()
            optimizer.zero_grad()
            npenalty.backward(retain_graph=True)
            optimizer.step()

        # Sigmoid to get env assignment
        group_labels = env_w.sigmoid() > .5
        group_labels = group_labels.int().detach().cpu().numpy()
        group_labels[self.labels==1] += 2
        
        # Partition using group labels to get group partition 
        group_partition = {}
        for i in range(len(group_labels)):
            if group_labels[i] not in group_partition:
                group_partition[group_labels[i]] = []
            group_partition[group_labels[i]].append(i)

        return group_partition