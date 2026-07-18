import os
import torch
from torch.utils.data import Dataset, DataLoader
from PIL import Image
import torchvision.transforms as T
from models.ssd import get_model

# -------- Dataset --------
class EyeGazeDataset(Dataset):
    def __init__(self, img_dir, label_dir):
        self.samples = []
        self.label_dir = label_dir

        #  Collect ALL labels into a dictionary
        self.label_map = {}
        for file in os.listdir(label_dir):
            if file.endswith(".txt"):
                name = os.path.splitext(file)[0]
                self.label_map[name] = os.path.join(label_dir, file)

        print(f"Total labels found: {len(self.label_map)}")

        #  Collect images and match labels FLEXIBLY
        for root, _, files in os.walk(img_dir):
            for file in files:
                if file.lower().endswith(".jpg"):
                    img_path = os.path.join(root, file)

                    file_name = os.path.splitext(file)[0]

                    # Try direct match
                    if file_name in self.label_map:
                        self.samples.append((img_path, self.label_map[file_name]))
                    else:
                        # Try removing "frame_" if present
                        alt_name = file_name.replace("frame_", "")
                        if alt_name in self.label_map:
                            self.samples.append((img_path, self.label_map[alt_name]))

        print(f" Total matched samples: {len(self.samples)}")

        self.transforms = T.Compose([
            T.Resize((300, 300)),
            T.ToTensor()
        ])

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label_path = self.samples[idx]

        image = Image.open(img_path).convert("RGB")
        image = self.transforms(image)
        
        with open(label_path, "r") as f:
            values = list(map(float, f.readline().split()))
            x, y = values[0], values[1]

        # bounding box
        box_size = 20
        x1 = max(0, x - box_size)
        y1 = max(0, y - box_size)
        x2 = min(300, x + box_size)
        y2 = min(300, y + box_size)

        target = {
            "boxes": torch.tensor([[x1, y1, x2, y2]], dtype=torch.float32),
            "labels": torch.tensor([1], dtype=torch.int64)
        }

        return image, target


# -------- MAIN --------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

dataset = EyeGazeDataset(
    "dataset/images",
    "dataset/labels"
)

if len(dataset) == 0:
    raise ValueError(" Still 0 samples → naming mismatch remains")

dataloader = DataLoader(
    dataset,
    batch_size=4,
    shuffle=True,
    collate_fn=lambda x: tuple(zip(*x))
)

model = get_model().to(device)

optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)

# -------- TRAIN --------
num_epochs = 5

for epoch in range(num_epochs):
    model.train()
    total_loss = 0

    for images, targets in dataloader:
        images = [img.to(device) for img in images]
        targets = [{k: v.to(device) for k, v in t.items()} for t in targets]

        loss_dict = model(images, targets)
        loss = sum(loss_dict.values())

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

print(f" Epoch {epoch+1}, Loss: {total_loss:.4f}")
