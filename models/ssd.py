import torchvision

def get_model():
    # num_classes=2 (background + pupil) -- without it this builds the stock
    # COCO 91-class head, which ssd_final.pth (trained for 2 classes, like
    # frcnn.py's FastRCNNPredictor(in_features, 2) does for FRCNN) cannot
    # load into: state_dict shapes are [12, ...]/[8, ...] per anchor layer
    # (2 classes x 6 or 4 anchors) vs. the untouched default's [546, ...]/
    # [364, ...] (91 x 6 or 4). Passing num_classes here builds the head at
    # the right shape from the start, the same role FRCNN's explicit
    # box_predictor swap plays.
    return torchvision.models.detection.ssd300_vgg16(num_classes=2)