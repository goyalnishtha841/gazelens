import torchvision

def get_model():
    return torchvision.models.detection.ssd300_vgg16(pretrained=True)