"""Train your own CNN facial-emotion model on FER2013 and export it to ONNX.

The app already works with the pretrained FER+ model. Use this script if your project
needs you to train the CNN yourself (step 3 of the plan).

1. Get the dataset (needs a free Kaggle account):
       pip install kaggle
       (put kaggle.json from kaggle.com > Settings > API into %USERPROFILE%\\.kaggle\\)
       kaggle datasets download -d msambare/fer2013 -p data/fer2013 --unzip
   You should end up with data/fer2013/train/<emotion>/*.jpg and data/fer2013/test/<emotion>/*.jpg

2. Train. A GPU helps a lot, so Google Colab (Runtime > GPU) is a good place to run this:
       pip install torch torchvision onnx
       python scripts/train_emotion_cnn.py --data data/fer2013 --epochs 30

3. Use the new model in the app:
       set EMOTION_MODEL=models\\emotion_cnn.onnx   (Windows)
       export EMOTION_MODEL=models/emotion_cnn.onnx (Mac/Linux)
"""
import argparse
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

CLASSES = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]  # must match emotion.FER2013_LABELS


def block(cin, cout):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
        nn.MaxPool2d(2), nn.Dropout(0.25),
    )


class EmotionCNN(nn.Module):
    def __init__(self, n_classes=7):
        super().__init__()
        self.features = nn.Sequential(block(1, 32), block(32, 64), block(64, 128), block(128, 256))  # 48 -> 3
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(256 * 3 * 3, 256), nn.ReLU(inplace=True),
                                  nn.Dropout(0.5), nn.Linear(256, n_classes))

    def forward(self, x):
        return self.head(self.features(x))


def loaders(root: Path, batch: int):
    train_tf = transforms.Compose([
        transforms.Grayscale(), transforms.Resize((48, 48)),
        transforms.RandomHorizontalFlip(), transforms.RandomRotation(10),
        transforms.RandomResizedCrop(48, scale=(0.85, 1.0)), transforms.ToTensor(),
    ])
    test_tf = transforms.Compose([transforms.Grayscale(), transforms.Resize((48, 48)), transforms.ToTensor()])
    train = datasets.ImageFolder(root / "train", train_tf)
    test = datasets.ImageFolder(root / "test", test_tf)
    # ImageFolder sorts the class folders alphabetically, which gives the same order as CLASSES
    assert train.classes == sorted(CLASSES), f"unexpected class folders: {train.classes}"
    return (DataLoader(train, batch, shuffle=True, num_workers=2),
            DataLoader(test, batch, num_workers=2))


def evaluate(model, loader, device):
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y in loader:
            pred = model(x.to(device)).argmax(1).cpu()
            correct += (pred == y).sum().item()
            total += len(y)
    return correct / total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/fer2013"))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--out", type=Path, default=Path("models/emotion_cnn.onnx"))
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", device)
    train_dl, test_dl = loaders(args.data, args.batch)
    model = EmotionCNN().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=args.epochs * len(train_dl))
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.1)

    best = 0.0
    for epoch in range(args.epochs):
        model.train()
        running = 0.0
        for x, y in train_dl:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            sched.step()
            running += loss.item() * len(y)
        acc = evaluate(model, test_dl, device)
        print(f"epoch {epoch + 1}/{args.epochs}  loss {running / len(train_dl.dataset):.4f}  test acc {acc:.4f}")
        if acc > best:
            best = acc
            torch.save(model.state_dict(), args.out.with_suffix(".pt"))

    model.load_state_dict(torch.load(args.out.with_suffix(".pt"), map_location=device))
    model.eval().cpu()
    args.out.parent.mkdir(exist_ok=True)
    torch.onnx.export(model, torch.zeros(1, 1, 48, 48), str(args.out), input_names=["input"], output_names=["logits"])
    print(f"best test accuracy {best:.4f}; exported {args.out}")


if __name__ == "__main__":
    main()
