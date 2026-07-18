import torchvision

def get_model():
    model = torchvision.models.detection.fasterrcnn_resnet50_fpn(
        pretrained=True
    )

    in_features = model.roi_heads.box_predictor.cls_score.in_features

    model.roi_heads.box_predictor = (
        torchvision.models.detection.faster_rcnn.FastRCNNPredictor(
            in_features,
            2
        )
    )

    return model