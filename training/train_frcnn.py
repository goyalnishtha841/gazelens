import os
import time
import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from models.frcnn import get_model

torch.backends.cudnn.benchmark = True


# ── Dataset ────────────────────────────────────────────────────────────────────

class GazeDataset(Dataset):

    def __init__(self, images_dir, labels_dir):

        self.images_dir = images_dir
        self.labels_dir = labels_dir

        self.transforms = transforms.ToTensor()

        self.samples = []

        for img_file in sorted(os.listdir(images_dir)):

            if not img_file.endswith(".jpg"):
                continue

            label_file = img_file.replace(".jpg", ".txt")

            if os.path.exists(
                os.path.join(labels_dir, label_file)
            ):
                self.samples.append(img_file)

        print(f"Dataset: {len(self.samples)} samples found")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):

        img_file = self.samples[idx]

        img_path = os.path.join(
            self.images_dir,
            img_file
        )

        label_path = os.path.join(
            self.labels_dir,
            img_file.replace(".jpg", ".txt")
        )

        img = Image.open(img_path).convert("RGB")

        W, H = img.size

        img_tensor = self.transforms(img)

        with open(label_path, "r") as f:
            cls, xc, yc, bw, bh = map(
                float,
                f.readline().split()
            )

        xc *= W
        yc *= H
        bw *= W
        bh *= H

        x1 = xc - bw / 2
        y1 = yc - bh / 2
        x2 = xc + bw / 2
        y2 = yc + bh / 2

        target = {
            "boxes": torch.tensor(
                [[x1, y1, x2, y2]],
                dtype=torch.float32
            ),
            "labels": torch.tensor(
                [1],
                dtype=torch.int64
            )
        }

        return img_tensor, target


# ── Collate (handles variable-size targets) ────────────────────────────────────

def collate_fn(batch):
    return tuple(zip(*batch))


# ── Training Loop ──────────────────────────────────────────────────────────────

def train():

    IMAGES_DIR = "dataset/images"
    LABELS_DIR = "dataset/labels"

    OUTPUT_DIR = "runs/frcnn"

    NUM_EPOCHS = 10
    BATCH_SIZE = 4
    LR = 0.005

    DEVICE = torch.device(
        "cuda" if torch.cuda.is_available()
        else "cpu"
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Using device: {DEVICE}")

    dataset = GazeDataset(
        IMAGES_DIR,
        LABELS_DIR
    )

    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        collate_fn=collate_fn,
        num_workers=8,
        pin_memory=True,
        persistent_workers=True
    )

    model = get_model().to(DEVICE)

    params = [
        p for p in model.parameters()
        if p.requires_grad
    ]

    optimizer = torch.optim.SGD(
        params,
        lr=LR,
        momentum=0.9,
        weight_decay=0.0005
    )

    scheduler = torch.optim.lr_scheduler.StepLR(
        optimizer,
        step_size=3,
        gamma=0.1
    )

    scaler = torch.cuda.amp.GradScaler(
        enabled=torch.cuda.is_available()
    )

    for epoch in range(NUM_EPOCHS):

        model.train()

        total_loss = 0

        start_time = time.time()

        for batch_idx, (images, targets) in enumerate(loader):

            images = [
                img.to(
                    DEVICE,
                    non_blocking=True
                )
                for img in images
            ]

            targets = [
                {
                    k: v.to(
                        DEVICE,
                        non_blocking=True
                    )
                    for k, v in t.items()
                }
                for t in targets
            ]

            optimizer.zero_grad()

            with torch.cuda.amp.autocast(
                enabled=torch.cuda.is_available()
            ):
                loss_dict = model(
                    images,
                    targets
                )

                losses = sum(
                    loss
                    for loss in loss_dict.values()
                )

            scaler.scale(losses).backward()
            scaler.step(optimizer)
            scaler.update()

            total_loss += losses.item()

            if (batch_idx + 1) % 100 == 0:

                print(
                    f"  Epoch [{epoch+1}/{NUM_EPOCHS}] "
                    f"Batch [{batch_idx+1}/{len(loader)}] "
                    f"Loss: {losses.item():.4f}"
                )

        scheduler.step()

        avg_loss = total_loss / len(loader)

        elapsed = time.time() - start_time

        print(
            f"\nEpoch [{epoch+1}/{NUM_EPOCHS}] "
            f"Avg Loss: {avg_loss:.4f} "
            f"Time: {elapsed:.1f}s\n"
        )

        ckpt_path = os.path.join(
            OUTPUT_DIR,
            f"frcnn_epoch{epoch+1}.pth"
        )

        torch.save(
            {
                "epoch": epoch + 1,
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "loss": avg_loss
            },
            ckpt_path
        )

        print(f"Saved checkpoint → {ckpt_path}")

    final_path = os.path.join(
        OUTPUT_DIR,
        "frcnn_final.pth"
    )

    torch.save(
        model.state_dict(),
        final_path
    )

    print(f"\nTraining complete. Final model → {final_path}")


if __name__ == "__main__":
    train()