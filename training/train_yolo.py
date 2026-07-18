from ultralytics import YOLO
import torch
import os

def train():
    DATA_CONFIG = "configs/lpw.yaml"
    MODEL_WEIGHTS = "yolov8n.pt"

    EPOCHS = 50
    IMG_SIZE = 640

    DEVICE = 0 if torch.cuda.is_available() else "cpu"

    os.makedirs("runs/yolo", exist_ok=True)

    model = YOLO(MODEL_WEIGHTS)

    model.train(
        data=DATA_CONFIG,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        device=DEVICE,
        project="runs",
        name="yolo",
        pretrained=True,
        save=True,
        verbose=True
    )

    model.save("runs/yolo/yolo_final.pt")

if __name__ == "__main__":
    train()
  


