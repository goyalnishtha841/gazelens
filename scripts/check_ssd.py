from models.ssd import get_model

model = get_model()

print(model.head.classification_head)