import os

IMG_W = 640   # adjust if needed
IMG_H = 480

def process_labels(base_path):
    for subject in os.listdir(base_path):
        subject_path = os.path.join(base_path, subject)

        if not os.path.isdir(subject_path):
            continue

        for file in os.listdir(subject_path):
            if file.endswith(".txt"):
                txt_path = os.path.join(subject_path, file)

                video_name = f"{subject}_{file.replace('.txt','')}"

                with open(txt_path, "r") as f:
                    lines = f.readlines()

                for i, line in enumerate(lines):
                    x, y = map(float, line.split())

                    xc = x / IMG_W
                    yc = y / IMG_H
                    w = 20 / IMG_W
                    h = 20 / IMG_H

                    label_name = f"{video_name}_{i}.txt"

                    with open(f"dataset/labels/{label_name}", "w") as out:
                        out.write(f"0 {xc} {yc} {w} {h}")

                print(f"Labeled {video_name}")