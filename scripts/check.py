from models.ssd import get_model

model = get_model()

print(type(model.head))
print(type(model.head.classification_head))
print(model.anchor_generator.num_anchors_per_location())