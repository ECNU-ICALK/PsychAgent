from torch.utils.data import Dataset

from agent_system.environments.env_package.therapy.patient.client import \
    ClientProfile


class ClientProfileDataset(Dataset):
    def __init__(self, profiles: list[ClientProfile]):
        self.profiles = profiles

    def __len__(self):
        return len(self.profiles)

    def __getitem__(self, idx):
        profile = self.profiles[idx]
        return {
            "name": profile.name,
            "age": profile.age,
            "gender": profile.gender,
            "job": profile.job,
            "problem": profile.problem,
            "personality": profile.personality,
            "goals": profile.goals,
        }
        
def collate_fn(batch):
    return {
        "name": [item["name"] for item in batch],
        "age": [item["age"] for item in batch],
        "gender": [item["gender"] for item in batch],
        "job": [item["job"] for item in batch],
        "problem": [item["problem"] for item in batch],
        "personality": [item["personality"] for item in batch],
        "goals": [item["goals"] for item in batch],
    }